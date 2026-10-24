"""The overview at the top of the case page (round 6 PR EV7, docs/workflow.md 6.37.2).

Who the case is about, who came instead, who decided (each ward side of a cross-ward move
on its own line) and why the case stopped, read from the rows the workflow already writes:
the events, APPROVAL_WARD_DECISION, and the audit rows of the case. Read-only.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Actor,
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    CandidateItem,
    Role,
    Staff,
    StaffingEvent,
    Ward,
)
from app.domain.enums import ActorType, AuditAction
from app.schemas.case import (
    CaseOverview,
    OverviewDecision,
    OverviewEvent,
    OverviewOutcome,
    OverviewPerson,
    OverviewReplacement,
)

_FILLS = {
    AuditAction.ASSIGNMENT_CREATED: "APPROVED",
    AuditAction.ASSIGNMENT_TRANSFERRED: "TRANSFERRED",
    AuditAction.MANUAL_ASSIGNMENT_CREATED: "MANUAL",
}


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


def build(db: Session, case_id: int) -> CaseOverview:
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

    staff_ids = {event.staff_id for event in events if event.staff_id is not None}
    staff_ids |= {int(row.payload["staff_id"]) for row in audits if "staff_id" in row.payload}
    staff_ids |= {decision.approver_id for decision, _, _ in ward_decisions}
    staff_ids |= {candidate for _, candidate, _ in ward_decisions}
    people = _People(db, staff_ids, {row.actor_id for row in audits})

    replacements = [
        OverviewReplacement(
            staff=_required(people.person(int(row.payload["staff_id"]))),
            how=_FILLS[row.action],
            at=row.created_at,
        )
        for row in audits
        if row.action in _FILLS and "staff_id" in row.payload
    ]

    decisions: list[tuple[datetime, OverviewDecision]] = [
        (
            decision.decided_at,
            OverviewDecision(
                kind="APPROVED" if decision.is_approved else "REJECTED",
                by=_required(people.person(decision.approver_id)),
                ward_name=ward_name,
                side=decision.side,
                candidate=people.person(candidate),
                reason=decision.reason,
                at=decision.decided_at,
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
            )
            for event in events
        ],
        replacements=replacements,
        decisions=[decision for _, decision in decisions],
        outcome=_outcome(audits, people),
    )


def _from_audit(row: AuditLog, people: _People) -> OverviewDecision | None:
    """The decisions that are not one ward side's: an automatic approval, a request that
    timed out, a manual assignment and a close. A person's approval is a ward decision."""
    payload: dict[str, Any] = row.payload
    candidate = people.person(payload.get("staff_id"))
    if row.action == AuditAction.APPROVAL_APPROVED and payload.get("approval_mode") == "AUTO":
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
    """The latest stop of the case: a later close replaces the handoff before it."""
    for row in reversed(audits):
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
