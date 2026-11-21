"""The overview at the top of the case page (round 6 PR EV7, docs/workflow.md 6.37.2).

Who the case is about, who came instead, who decided (each ward side of a cross-ward move
on its own line) and why the case stopped, read from the rows the workflow already writes:
the events, APPROVAL_WARD_DECISION, and the audit rows of the case. Read-only.

Round 6 PR EV8 (6.38.6) adds what the replacement summary of the case page needs: the shift,
every approval request bound to its candidate (where they come from, and each ward's side
with who decided it or who it waits for), and the offers still waiting for an answer.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE
from app.db.models import (
    Actor,
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    Ward,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    ActorType,
    ApprovalMode,
    ApprovalSide,
    ApproverCapacity,
    AuditAction,
    CaseStatus,
    OutreachStatus,
    RosterStatus,
    StaffStatus,
)
from app.schemas.case import (
    CaseOverview,
    OverviewAutoBasis,
    OverviewDecision,
    OverviewEvent,
    OverviewMove,
    OverviewOutcome,
    OverviewPerson,
    OverviewReplacement,
    OverviewRequest,
    OverviewShift,
    OverviewSide,
)
from app.services import policy_service

_FILLS = {
    AuditAction.ASSIGNMENT_CREATED: "APPROVED",
    AuditAction.ASSIGNMENT_TRANSFERRED: "TRANSFERRED",
    AuditAction.MANUAL_ASSIGNMENT_CREATED: "MANUAL",
}
# The statuses of a case that stopped: only these show why. A stop row of a case that went
# on afterwards (staffed by hand, or a workflow that recovered) is history, not the outcome
_STOPPED = {CaseStatus.MANUAL_HANDOFF, CaseStatus.UNRESOLVED, CaseStatus.FAILED}
# A stop row before one of these is over: the case went on and was staffed after it
_RESOLUTIONS = {*_FILLS, AuditAction.CASE_RESOLVED}

RequestStatus = Literal["PENDING", "APPROVED", "REJECTED", "TIMED_OUT", "CANCELLED"]
SideStatus = Literal["PENDING", "APPROVED", "REJECTED", "AUTO_APPROVED", "TIMED_OUT", "NOT_NEEDED"]


def _staff_id(payload: dict[str, Any]) -> int | None:
    """payload.staff_id when it is a usable ID: an old or hand-written row may hold null or
    text, and the case page must still open."""
    value = payload.get("staff_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


class _People:
    """Names, roles and home wards of staff and actors, read once per overview."""

    def __init__(self, db: Session, staff_ids: set[int], actor_ids: set[int]) -> None:
        self.actors = {
            actor.id: actor for actor in db.scalars(select(Actor).where(Actor.id.in_(actor_ids)))
        }
        staff_ids |= {actor.staff_id for actor in self.actors.values() if actor.staff_id}
        self.staff = {
            row.id: row
            for row in db.execute(
                select(Staff.id, Staff.first_name, Staff.last_name, Role.name.label("role"))
                .add_columns(Ward.name.label("ward"))
                .join(Role, Role.id == Staff.role_id)
                .join(Ward, Ward.id == Staff.home_ward_id)
                .where(Staff.id.in_(staff_ids))
            )
        }

    def person(self, staff_id: int | None) -> OverviewPerson | None:
        if staff_id is None:
            return None
        row = self.staff.get(staff_id)
        if row is None:
            return OverviewPerson(staff_id=staff_id, name=str(staff_id), role=None, ward_name=None)
        return OverviewPerson(
            staff_id=staff_id,
            name=f"{row.first_name} {row.last_name}",
            role=row.role,
            ward_name=row.ward,
        )

    def actor(self, actor_id: int) -> OverviewPerson:
        actor = self.actors.get(actor_id)
        if actor is not None and actor.actor_type == ActorType.USER and actor.staff_id:
            found = self.person(actor.staff_id)
            assert found is not None
            return found
        name = actor.name if actor is not None else "system"
        return OverviewPerson(staff_id=None, name=name, role=None, ward_name=None)


@dataclass(frozen=True)
class _RequestRow:
    """An approval request with its candidate, the destination ward and the move, if any."""

    request: ApprovalRequest
    staff_id: int
    proposed_shift_id: int
    destination_ward_id: int
    destination_ward: str
    source_ward_id: int | None
    move: OverviewMove | None


def _request_rows(db: Session, case_id: int) -> list[_RequestRow]:
    source_row = aliased(RosterAssignment)
    source_shift = aliased(Shift)
    source_ward = aliased(Ward)
    rows = db.execute(
        select(
            ApprovalRequest,
            CandidateItem.staff_id,
            CandidateItem.proposed_shift_id,
            Shift.ward_id,
            Ward.name,
            source_shift.id,
            source_shift.ward_id,
            source_ward.name,
            source_shift.start_at,
            source_shift.end_at,
        )
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(Shift, Shift.id == CandidateItem.proposed_shift_id)
        .join(Ward, Ward.id == Shift.ward_id)
        .outerjoin(source_row, source_row.id == CandidateItem.source_assignment_id)
        .outerjoin(source_shift, source_shift.id == source_row.shift_id)
        .outerjoin(source_ward, source_ward.id == source_shift.ward_id)
        .where(ApprovalRequest.case_id == case_id)
        .order_by(ApprovalRequest.id)
    ).all()
    result = []
    for (
        request,
        staff_id,
        shift_id,
        ward_id,
        ward_name,
        source_id,
        source_ward_id,
        source_name,
        source_start,
        source_end,
    ) in rows:
        move = None
        if source_id is not None:
            move = OverviewMove(
                shift_id=source_id,
                ward_name=source_name,
                start_at=source_start,
                end_at=source_end,
            )
        result.append(
            _RequestRow(
                request=request,
                staff_id=staff_id,
                proposed_shift_id=shift_id,
                destination_ward_id=ward_id,
                destination_ward=ward_name,
                source_ward_id=source_ward_id,
                move=move,
            )
        )
    return result


def _head_nurses(db: Session, ward_ids: set[int]) -> dict[int, list[int]]:
    """The active head nurses of each ward: who a pending side of that ward waits for."""
    heads: dict[int, list[int]] = {}
    if not ward_ids:
        return heads
    for staff_id, ward_id in db.execute(
        select(Staff.id, Staff.home_ward_id)
        .join(Role, Role.id == Staff.role_id)
        .where(
            Staff.home_ward_id.in_(ward_ids),
            Role.name == HEAD_NURSE_ROLE,
            Staff.status == StaffStatus.ACTIVE,
        )
        .order_by(Staff.id)
    ):
        heads.setdefault(ward_id, []).append(staff_id)
    return heads


def _shift(db: Session, case_id: int) -> OverviewShift | None:
    row = db.execute(
        select(Shift, Ward.name)
        .join(Ward, Ward.id == Shift.ward_id)
        .join(StaffingCase, StaffingCase.shift_id == Shift.id)
        .where(StaffingCase.id == case_id)
    ).first()
    if row is None:
        return None
    shift, ward_name = row
    return OverviewShift(
        shift_id=shift.id,
        ward_id=shift.ward_id,
        ward_name=ward_name,
        shift_type=shift.shift_type,
        start_at=shift.start_at,
        end_at=shift.end_at,
    )


def _open_offers(db: Session, case_id: int) -> int:
    """Offers of the case still waiting for an answer: the current step while nobody came."""
    return db.execute(
        select(func.count()).where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.status == OutreachStatus.SENT,
            CandidateOutreach.expires_at > clock.now(),
        )
    ).scalar_one()


def _event_reason(payload: dict[str, Any]) -> str | None:
    """NO_SHOW for the check-in job's event (6.24), the words of an ASSIGNMENT_CANCELLED."""
    reason = payload.get("reason")
    return reason if isinstance(reason, str) else None


def _patient_count(payload: dict[str, Any]) -> int | None:
    count = payload.get("patient_count")
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def build(db: Session, case_id: int) -> CaseOverview:
    case_status = db.scalar(select(StaffingCase.status).where(StaffingCase.id == case_id))
    events = db.scalars(
        select(StaffingEvent).where(StaffingEvent.case_id == case_id).order_by(StaffingEvent.id)
    ).all()
    audits = db.scalars(
        select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.id)
    ).all()
    ward_decisions = db.execute(
        select(ApprovalWardDecision, CandidateItem.staff_id, Ward.name)
        .join(ApprovalRequest, ApprovalRequest.id == ApprovalWardDecision.approval_request_id)
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(Ward, Ward.id == ApprovalWardDecision.ward_id)
        .where(ApprovalRequest.case_id == case_id)
        .order_by(ApprovalWardDecision.id)
    ).all()
    request_rows = _request_rows(db, case_id)
    heads = _head_nurses(
        db,
        {row.destination_ward_id for row in request_rows}
        | {row.source_ward_id for row in request_rows if row.source_ward_id is not None},
    )

    staff_ids = {event.staff_id for event in events if event.staff_id is not None}
    staff_ids |= {staff_id for row in audits if (staff_id := _staff_id(row.payload)) is not None}
    staff_ids |= {
        decision.approver_id
        for decision, _, _ in ward_decisions
        if decision.approver_id is not None
    }
    staff_ids |= {candidate for _, candidate, _ in ward_decisions}
    staff_ids |= {row.staff_id for row in request_rows}
    staff_ids |= {head for ward_heads in heads.values() for head in ward_heads}
    people = _People(db, staff_ids, {row.actor_id for row in audits})

    replacements = [
        OverviewReplacement(
            staff=_required(people.person(staff_id)),
            how=_FILLS[row.action],
            at=row.created_at,
        )
        for row in audits
        if row.action in _FILLS and (staff_id := _staff_id(row.payload)) is not None
    ]

    decisions: list[tuple[datetime, OverviewDecision]] = [
        (
            decision.decided_at,
            OverviewDecision(
                kind="AUTO_APPROVED"
                if decision.approval_mode == ApprovalMode.AUTO
                else "APPROVED"
                if decision.is_approved
                else "REJECTED",
                # The system decided an AUTO side: no person is named as its approver (6.39)
                by=_SYSTEM
                if decision.approver_id is None
                else _required(people.person(decision.approver_id)),
                ward_name=ward_name,
                side=decision.side,
                candidate=people.person(candidate),
                reason=decision.reason,
                at=decision.decided_at,
                auto=_auto_basis(decision),
            ),
        )
        for decision, candidate, ward_name in ward_decisions
    ]
    for row in audits:
        decision = _from_audit(row, people)
        if decision is not None:
            decisions.append((row.created_at, decision))
    decisions.sort(key=lambda pair: pair[0])

    return CaseOverview(
        events=[
            OverviewEvent(
                event_id=event.id,
                event_type=event.event_type,
                staff=people.person(event.staff_id),
                occurred_at=event.occurred_at,
                reason=_event_reason(event.payload),
                patient_count=_patient_count(event.payload),
            )
            for event in events
        ],
        replacements=replacements,
        decisions=[decision for _, decision in decisions],
        outcome=_outcome(audits, people) if case_status in _STOPPED else None,
        shift=_shift(db, case_id),
        requests=_requests(
            db,
            request_rows,
            [decision for decision, _, _ in ward_decisions],
            heads,
            people,
            stopped=case_status in AUTOMATION_STOPPED_STATUSES,
        ),
        open_offers=_open_offers(db, case_id),
    )


_SYSTEM = OverviewPerson(staff_id=None, name=ActorName.SYSTEM.value, role=None, ward_name=None)


def _auto_basis(decision: ApprovalWardDecision | None) -> OverviewAutoBasis | None:
    """The queue that made an automatic side eligible (6.39)."""
    if decision is None or decision.approval_mode != ApprovalMode.AUTO:
        return None
    assert decision.queue_count is not None and decision.queue_cap is not None
    assert decision.queue_approver_count is not None
    return OverviewAutoBasis(
        basis="SUPERVISOR_QUEUE"
        if decision.decided_as == ApproverCapacity.SUPERVISOR
        else "HEAD_NURSE_QUEUE",
        queue_count=decision.queue_count,
        cap=float(decision.queue_cap),
        approver_count=decision.queue_approver_count,
    )


def _request_status(request: ApprovalRequest, *, stopped: bool) -> RequestStatus:
    if request.is_timed_out:
        return "TIMED_OUT"
    if not request.is_pending:
        return "APPROVED" if request.is_approved else "REJECTED"
    # Undecided on a stopped case: kept as history, but nobody may decide it now (6.12)
    return "CANCELLED" if stopped else "PENDING"


def _side_status(
    decision: ApprovalWardDecision | None, request: ApprovalRequest, status: RequestStatus
) -> SideStatus:
    if decision is not None:
        if decision.approval_mode == ApprovalMode.AUTO:
            return "AUTO_APPROVED"
        return "APPROVED" if decision.is_approved else "REJECTED"
    if status == "APPROVED" and request.approval_mode == ApprovalMode.AUTO:
        return "AUTO_APPROVED"
    if status in ("TIMED_OUT", "PENDING"):
        return status
    # The other ward said no, or the case stopped, before this ward decided
    return "NOT_NEEDED"


def _requests(
    db: Session,
    rows: list[_RequestRow],
    decisions: list[ApprovalWardDecision],
    heads: dict[int, list[int]],
    people: _People,
    *,
    stopped: bool,
) -> list[OverviewRequest]:
    """Every approval request of the case with each ward side (6.21), bound to its candidate."""
    if not rows:
        return []
    by_side = {(decision.approval_request_id, decision.side): decision for decision in decisions}
    delay = timedelta(seconds=policy_service.get_approval_policy(db).supervisor_after_seconds)
    on_shift = set(
        db.execute(
            select(RosterAssignment.staff_id, RosterAssignment.shift_id).where(
                RosterAssignment.staff_id.in_({row.staff_id for row in rows}),
                RosterAssignment.shift_id.in_({row.proposed_shift_id for row in rows}),
                RosterAssignment.status.in_([RosterStatus.ASSIGNED, RosterStatus.COMPLETED]),
            )
        ).tuples()
    )
    result = []
    for row in rows:
        request = row.request
        status = _request_status(request, stopped=stopped)
        wards = [(ApprovalSide.DESTINATION, row.destination_ward_id, row.destination_ward)]
        if row.move is not None and row.source_ward_id is not None:
            wards.append((ApprovalSide.SOURCE, row.source_ward_id, row.move.ward_name))
        sides = []
        for side, ward_id, ward_name in wards:
            decision = by_side.get((request.id, side))
            side_status = _side_status(decision, request, status)
            waiting = side_status == "PENDING"
            sides.append(
                OverviewSide(
                    side=side,
                    ward_name=ward_name,
                    status=side_status,
                    by=None
                    if decision is None or decision.approver_id is None
                    else people.person(decision.approver_id),
                    decided_as=None if decision is None else decision.decided_as,
                    reason=None if decision is None else decision.reason,
                    at=None if decision is None else decision.decided_at,
                    waiting_for=[_required(people.person(head)) for head in heads.get(ward_id, [])]
                    if waiting
                    else [],
                    supervisor_from=request.requested_at + delay if waiting else None,
                    auto=_auto_basis(decision),
                )
            )
        result.append(
            OverviewRequest(
                approval_id=request.id,
                candidate=_required(people.person(row.staff_id)),
                destination_ward_name=row.destination_ward,
                moved_from=row.move,
                status=status,
                approval_mode=request.approval_mode,
                assigned=(row.staff_id, row.proposed_shift_id) in on_shift,
                requested_at=request.requested_at,
                sides=sides,
            )
        )
    return result


def _from_audit(row: AuditLog, people: _People) -> OverviewDecision | None:
    """The decisions that are not one ward side's: an automatic approval, a request that
    timed out, a manual assignment and a close. A person's approval is a ward decision."""
    payload: dict[str, Any] = row.payload
    candidate = people.person(_staff_id(payload))
    if row.action == AuditAction.APPROVAL_APPROVED and payload.get("approval_mode") == "AUTO":
        if "side" in payload:
            # Since 6.39 an automatic side has its own ward decision row, listed above
            return None
        kind = "AUTO_APPROVED"
    elif row.action == AuditAction.APPROVAL_TIMEOUT:
        kind = "APPROVAL_TIMEOUT"
    elif row.action == AuditAction.MANUAL_ASSIGNMENT_CREATED:
        kind = "MANUAL_ASSIGNMENT"
    elif row.action == AuditAction.CASE_CLOSED_UNRESOLVED:
        kind = "CLOSED_UNRESOLVED"
        candidate = None
    else:
        return None
    return OverviewDecision(
        kind=kind,
        by=people.actor(row.actor_id),
        ward_name=None,
        side=None,
        candidate=candidate,
        reason=payload.get("reason"),
        at=row.created_at,
    )


def _outcome(audits: Any, people: _People) -> OverviewOutcome | None:
    """The latest stop of the case: a later close replaces the handoff before it, and a
    later fill or resolution means the case went on, so there is no stop to show."""
    for row in reversed(audits):
        if row.action in _RESOLUTIONS:
            return None
        if row.action == AuditAction.CASE_CLOSED_UNRESOLVED:
            kind, reason = "CLOSED_UNRESOLVED", row.payload.get("reason")
        elif row.action == AuditAction.MANUAL_HANDOFF:
            kind, reason = "MANUAL_HANDOFF", row.payload.get("reason")
        elif row.action == AuditAction.WORKFLOW_FAILED:
            kind, reason = "FAILED", row.payload.get("error_type")
        else:
            continue
        return OverviewOutcome(
            kind=kind,
            reason=reason,
            by=people.actor(row.actor_id),
            at=row.created_at,
        )
    return None


def _required(person: OverviewPerson | None) -> OverviewPerson:
    assert person is not None
    return person
