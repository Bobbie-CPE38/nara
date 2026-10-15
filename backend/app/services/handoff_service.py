"""The manual exits of MANUAL_HANDOFF (docs/workflow.md, section 6.12).

A head nurse of the shift's ward takes a stopped case forward by hand: assign
people until the gap is closed (T8), or close the case without a replacement
(T9). The window-close step also closes a stopped case when a successor case
opens for the same shift (T9).

Every write here runs in one transaction that this module commits, except
`close_superseded()`, which joins the transaction of the window-close step.
Status changes go through `orchestrator.leave_handoff()`.
"""

import logging
from collections.abc import Collection
from typing import NamedTuple

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, MAX_APPROVAL_REASON_LENGTH, SUPERVISOR_ROLE
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    ManualAssignment,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingGap,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    OutreachStatus,
    RosterStatus,
    StaffStatus,
)
from app.domain.errors import CaseNotFoundError
from app.domain.staffing.ward_authority import can_decide, manages_ward
from app.schemas.handoff import HandoffCandidate, HandoffCase
from app.services import (
    actor_service,
    audit_service,
    case_facts_service,
    hard_rule_service,
    offer_conflict_service,
    outreach_service,
)
from app.workflow import orchestrator

logger = logging.getLogger(__name__)

# Same limit and rules as the reason of a rejected approval (R2-Q20)
MAX_REASON_LENGTH = MAX_APPROVAL_REASON_LENGTH
SUPERSEDED_REASON = "A new case opened for this shift"
_LIVE_OFFER_STATUSES = (OutreachStatus.SENT, OutreachStatus.ACCEPTED)
_ON_ROSTER_STATUSES = (RosterStatus.ASSIGNED, RosterStatus.COMPLETED)


class AssignmentOutcome(NamedTuple):
    """What a committed manual assignment produced, as plain values.

    Read before the post-commit notifications, so the answer never needs the
    session again: a failed notification rolls its own transaction back.
    """

    manual_assignment_id: int
    assignment_id: int
    staff_id: int
    case_id: int
    case_status: CaseStatus
    cancelled_outreach_ids: list[int]


class HandoffForbiddenError(PermissionError):
    """The caller is not a head nurse of the ward the shift belongs to."""


class HandoffCaseStateError(ValueError):
    """The case is not at MANUAL_HANDOFF, so it has no manual exit."""


class StaffNotSelectableError(ValueError):
    """The chosen person is not an active staff member of the shift's ward."""


class HardRulesFailedError(ValueError):
    """The chosen person fails a Hard Rule. No reason overrides that (R2-Q14)."""

    def __init__(self, staff_id: int, failed_rules: list[str]) -> None:
        super().__init__(f"Staff {staff_id} cannot take this shift: {', '.join(failed_rules)}")
        self.failed_rules = failed_rules


class ConflictingOffersError(ValueError):
    """The assignment would cancel the person's offers on other cases; confirm first."""

    def __init__(self, staff_id: int, case_ids: list[int]) -> None:
        cases = ", ".join(str(case_id) for case_id in case_ids)
        super().__init__(
            f"Staff {staff_id} has an offer on case {cases} that this shift rules out. "
            "Confirm to cancel it"
        )
        self.case_ids = case_ids


class InvalidHandoffReasonError(ValueError):
    """Closing needs a nonblank reason; every reason must fit the length limit."""


class HandoffLockRetryError(ValueError):
    """Concurrent offer changes prevented acquiring a stable lock set; retry."""


def list_cases(
    db: Session, *, role_id: int, home_ward_id: int, statuses: Collection[CaseStatus]
) -> list[HandoffCase]:
    """Cases of the caller's ward in the given statuses, oldest first. Read-only.

    Head Nurses see their own ward; Supervisors see all wards immediately.
    """
    supervisor = _require_manager_role(db, role_id) == SUPERVISOR_ROLE
    with db.no_autoflush:
        rows = db.execute(
            select(StaffingCase, Shift.ward_id)
            .join(Shift, Shift.id == StaffingCase.shift_id)
            .where(
                StaffingCase.status.in_(list(statuses)),
                true() if supervisor else Shift.ward_id == home_ward_id,
            )
            .order_by(StaffingCase.id)
        ).all()
        case_ids = [case.id for case, _ in rows]
        # Batched for the polling page: two queries, not two per case
        assigned = case_facts_service.assigned_staff_ids_by_case(db, case_ids)
        latest_gap = (
            select(func.max(StaffingGap.id))
            .where(StaffingGap.case_id.in_(case_ids))
            .group_by(StaffingGap.case_id)
        )
        headcount_gaps: dict[int, int] = {
            gap_case_id: headcount_gap
            for gap_case_id, headcount_gap in db.execute(
                select(StaffingGap.case_id, StaffingGap.headcount_gap).where(
                    StaffingGap.id.in_(latest_gap)
                )
            )
        }
        result = [
            HandoffCase(
                id=case.id,
                status=case.status,
                shift_id=case.shift_id,
                ward_id=ward_id,
                required_replacement_time=case.required_replacement_time,
                created_at=case.created_at,
                headcount_gap=headcount_gaps.get(case.id),
                assigned_count=len(assigned[case.id]),
                can_manage=case.status is CaseStatus.MANUAL_HANDOFF,
            )
            for case, ward_id in rows
        ]
        return result


def list_candidates(
    db: Session, *, case_id: int, role_id: int, home_ward_id: int
) -> list[HandoffCandidate]:
    """Every active staff member of the shift's ward with what blocks them. Read-only.

    Not limited to the plan of the case (R2-Q13). The rules are read without
    locks, so the list is a hint: `assign()` checks again under its locks.
    """
    case = db.get(StaffingCase, case_id)
    if case is None:
        raise CaseNotFoundError(f"No case {case_id}")
    shift = _shift(db, case.shift_id)
    _require_authority(db, role_id=role_id, home_ward_id=home_ward_id, shift=shift)
    with db.no_autoflush:
        staff = list(
            db.execute(
                select(Staff, Role.name)
                .join(Role, Role.id == Staff.role_id)
                .where(Staff.home_ward_id == shift.ward_id, Staff.status == StaffStatus.ACTIVE)
                .order_by(Staff.id)
            ).all()
        )
        staff_ids = [person.id for person, _ in staff]
        checks = hard_rule_service.check_staff(db, shift=shift, staff_ids=staff_ids)
        other_cases: dict[int, list[int]] = {staff_id: [] for staff_id in staff_ids}
        now = clock.now()
        for staff_id, other_case_id, status, expires_at in db.execute(
            select(
                CandidateItem.staff_id,
                CandidateOutreach.case_id,
                CandidateOutreach.status,
                CandidateOutreach.expires_at,
            )
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateItem.staff_id.in_(staff_ids),
                CandidateOutreach.case_id != case_id,
                CandidateOutreach.status.in_(_LIVE_OFFER_STATUSES),
                StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            )
            .order_by(CandidateOutreach.case_id)
        ):
            overdue = status is OutreachStatus.SENT and (expires_at is None or expires_at <= now)
            if not overdue and other_case_id not in other_cases[staff_id]:
                other_cases[staff_id].append(other_case_id)
        return [
            HandoffCandidate(
                staff_id=person.id,
                first_name=person.first_name,
                last_name=person.last_name,
                role_id=person.role_id,
                role_name=role_name,
                blocking_rules=[rule.value for rule in checks[person.id].result.failed_rules],
                other_case_ids=other_cases[person.id],
            )
            for person, role_name in staff
        ]


def assign(
    db: Session,
    *,
    case_id: int,
    staff_id: int,
    assigned_by: int,
    role_id: int,
    home_ward_id: int,
    actor_id: int,
    reason: str | None = None,
    confirm_conflicts: bool = False,
) -> AssignmentOutcome:
    """Put one person on the shift of a MANUAL_HANDOFF case, then commit.

    Locks Shift → the person's live offers → case → the person's STAFF row, the
    order of an approval decision (section 6.11), and rechecks everything after.
    The person must pass every Hard Rule against the roster as it is then: a
    failure raises and nothing is written, whatever the reason says (R2-Q14).

    Nobody answers and nobody approves (R2-Q15, R2-Q16): the roster row is
    created at once. When the people on the roster then close the gap of the
    case, it becomes RESOLVED in this transaction (T8).

    An offer the person holds on another case may clash with the new shift. Then
    `confirm_conflicts` must be true; the clashing offers are cancelled and their
    cases recomputed after the commit (R2-Q46). Confirming is not an override:
    the Hard Rules of this shift were already passed.

    Returns what was committed. The other cases are recomputed after the
    commit; a failure there is logged and left to the job's recovery sweep, and
    never turns the committed assignment into an error (as in PR T).
    """
    case, shift, offers = _lock_assignment(
        db, case_id=case_id, staff_id=staff_id, role_id=role_id, home_ward_id=home_ward_id
    )
    person = db.get(Staff, staff_id, populate_existing=True)
    if (
        person is None
        or person.status is not StaffStatus.ACTIVE
        or not manages_ward(home_ward_id=person.home_ward_id, ward_id=shift.ward_id)
    ):
        raise StaffNotSelectableError(
            f"Staff {staff_id} is not an active staff member of the shift's ward"
        )
    db.flush()
    failed = hard_rule_service.check_staff(db, shift=shift, staff_ids=[staff_id])[
        staff_id
    ].result.failed_rules
    if failed:
        raise HardRulesFailedError(staff_id, [rule.value for rule in failed])
    stored_reason = _note(reason)

    assignment = RosterAssignment(
        staff_id=staff_id,
        shift_id=shift.id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        candidate_source=CandidateSource.SAME_WARD,
    )
    db.add(assignment)
    db.flush()
    # Judged against the roster row just written, with the offers under lock
    clashing = offer_conflict_service.conflicting_offers(
        db, case_id=case.id, staff_id=staff_id, offers=offers
    )
    if clashing and not confirm_conflicts:
        db.rollback()
        raise ConflictingOffersError(staff_id, sorted({row.case_id for row in clashing}))

    manual = ManualAssignment(
        case_id=case.id,
        roster_assignment_id=assignment.id,
        assigned_by=assigned_by,
        reason=stored_reason,
    )
    db.add(manual)
    db.flush()
    cancelled = offer_conflict_service.cancel_conflicting_offers(
        db,
        case=case,
        assignment=assignment,
        offers=offers,
        actor_id=actor_id,
        source="MANUAL_ASSIGNMENT",
    )
    cancelled_ids = [row.id for row in cancelled]
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.MANUAL_ASSIGNMENT_CREATED,
        entity_type=EntityType.ROSTER_ASSIGNMENT,
        entity_id=assignment.id,
        payload={
            "assignment_id": assignment.id,
            "manual_assignment_id": manual.id,
            "staff_id": staff_id,
            "assignment_type": assignment.assignment_type.value,
            "reason": stored_reason,
            "cancelled_outreach_ids": cancelled_ids,
        },
    )
    if case_facts_service.load_case_facts(db, case).gap_closed_by_assigned:
        audit_service.log(
            db,
            case_id=case.id,
            actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
            action=AuditAction.CASE_RESOLVED,
            entity_type=EntityType.STAFFING_CASES,
            entity_id=case.id,
            payload={
                "assignment_ids": _assignment_ids(db, case),
                "cancelled_outreach_ids": [],
            },
        )
        case = orchestrator.leave_handoff(db, case.id, CaseStatus.RESOLVED)
    db.commit()
    outcome = AssignmentOutcome(
        manual_assignment_id=manual.id,
        assignment_id=assignment.id,
        staff_id=staff_id,
        case_id=case.id,
        case_status=case.status,
        cancelled_outreach_ids=cancelled_ids,
    )
    foreign_case_ids = {row.case_id for row in cancelled}
    # Their offers changed without an event of their own (section 5.3)
    try:
        outreach_service.recompute_affected_cases(
            db,
            staff_id=staff_id,
            own_case_id=case_id,
            additional_case_ids=foreign_case_ids,
        )
    except Exception:
        db.rollback()
        # The job's recovery sweep picks the waiting cases up on its next round
        logger.exception(
            "Manual assignment %s is committed; cases %s need a recompute retry",
            outcome.manual_assignment_id,
            sorted(foreign_case_ids),
        )
    return outcome


def close(
    db: Session,
    *,
    case_id: int,
    role_id: int,
    home_ward_id: int,
    actor_id: int,
    reason: str | None,
) -> StaffingCase:
    """Close a MANUAL_HANDOFF case without a replacement (T9), then commit.

    Needs a nonblank reason. Roster rows the head nurse already created for the
    case stay on the roster.
    """
    initial = db.get(StaffingCase, case_id)
    if initial is None:
        raise CaseNotFoundError(f"No case {case_id}")
    shift = _lock_shift(db, initial.shift_id)
    _require_authority(db, role_id=role_id, home_ward_id=home_ward_id, shift=shift)
    case = _lock_case(db, case_id)
    stored_reason = _note(reason)
    if not stored_reason:
        raise InvalidHandoffReasonError("Closing a case requires a nonblank reason")
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.CASE_CLOSED_UNRESOLVED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            "reason": stored_reason,
            "closed_by": db.scalar(select(Role.name).where(Role.id == role_id)),
        },
    )
    case = orchestrator.leave_handoff(db, case.id, CaseStatus.UNRESOLVED)
    db.commit()
    return case


def close_superseded(db: Session, *, shift_id: int, successor_case_id: int) -> list[int]:
    """Close the MANUAL_HANDOFF cases a new case of the same shift replaces (T9); no commit.

    A stopped case counts as finished, so the next window of the shift opens a
    new case (Q49), and that case measures its gap on the whole roster: the gap
    of the old case is inside it. Leaving both open would have the automation
    and the head nurse fill the same hole (R2-Q19).

    Called by the window-close step, which holds the Shift lock and commits.
    Returns the closed case IDs.
    """
    case_ids = list(
        db.scalars(
            select(StaffingCase.id)
            .where(
                StaffingCase.shift_id == shift_id,
                StaffingCase.status == CaseStatus.MANUAL_HANDOFF,
                StaffingCase.id != successor_case_id,
            )
            .order_by(StaffingCase.id)
        )
    )
    actor_id = actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR)
    for case_id in case_ids:
        audit_service.log(
            db,
            case_id=case_id,
            actor_id=actor_id,
            action=AuditAction.CASE_CLOSED_UNRESOLVED,
            entity_type=EntityType.STAFFING_CASES,
            entity_id=case_id,
            payload={
                "reason": SUPERSEDED_REASON,
                "closed_by": "SUCCESSOR_CASE",
                "successor_case_id": successor_case_id,
            },
        )
        orchestrator.leave_handoff(db, case_id, CaseStatus.UNRESOLVED)
    return case_ids


def _lock_assignment(
    db: Session, *, case_id: int, staff_id: int, role_id: int, home_ward_id: int
) -> tuple[StaffingCase, Shift, list[CandidateOutreach]]:
    """Take the full lock set before any write; restart if an offer appeared meanwhile.

    The STAFF lock stops a new wave from sending to the person, but a wave may
    have committed between the offer query and that lock. Never lock those new
    offers after the case and STAFF: release and restart in the agreed order.
    """
    offer_query = (
        select(CandidateOutreach)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            CandidateItem.staff_id == staff_id,
            CandidateOutreach.status.in_(_LIVE_OFFER_STATUSES),
        )
    )
    for _ in range(5):
        initial = db.get(StaffingCase, case_id)
        if initial is None:
            raise CaseNotFoundError(f"No case {case_id}")
        shift = _lock_shift(db, initial.shift_id)
        _require_authority(db, role_id=role_id, home_ward_id=home_ward_id, shift=shift)
        offers = list(
            db.scalars(
                offer_query.order_by(CandidateOutreach.id)
                .with_for_update(key_share=True, of=CandidateOutreach)
                .execution_options(populate_existing=True)
            )
        )
        case = _lock_case(db, case_id)
        # Outside the plan too: the person need not be a candidate of the case
        hard_rule_service.lock_staff(db, [staff_id])
        current_ids = set(db.scalars(offer_query.with_only_columns(CandidateOutreach.id)))
        if current_ids <= {row.id for row in offers}:
            return case, shift, offers
        db.rollback()
    raise HandoffLockRetryError(
        "Could not lock a stable offer set after five attempts; retry the assignment"
    )


def _lock_shift(db: Session, shift_id: int) -> Shift:
    shift = db.scalar(select(Shift).where(Shift.id == shift_id).with_for_update(key_share=True))
    if shift is None:
        raise LookupError(f"No shift {shift_id}")
    return shift


def _lock_case(db: Session, case_id: int) -> StaffingCase:
    case = db.scalars(
        select(StaffingCase)
        .where(StaffingCase.id == case_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one()
    if case.status is not CaseStatus.MANUAL_HANDOFF:
        raise HandoffCaseStateError(
            f"Case {case_id} is {case.status.value}; only a MANUAL_HANDOFF case can be managed"
        )
    return case


def _shift(db: Session, shift_id: int) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise LookupError(f"No shift {shift_id}")
    return shift


def _require_manager_role(db: Session, role_id: int) -> str:
    role = db.scalar(select(Role.name).where(Role.id == role_id))
    if role not in {HEAD_NURSE_ROLE, SUPERVISOR_ROLE}:
        raise HandoffForbiddenError("Only a Head Nurse or Supervisor may manage handed-off cases")
    return role


def _require_authority(db: Session, *, role_id: int, home_ward_id: int, shift: Shift) -> None:
    """The shared approver rule; Supervisor can act on handoff immediately."""
    role = db.scalar(select(Role.name).where(Role.id == role_id))
    if not can_decide(role=role, home_ward_id=home_ward_id, ward_id=shift.ward_id, waited=True):
        raise HandoffForbiddenError("The staff member cannot manage this ward")


def _note(reason: str | None) -> str | None:
    """Trim the reason and enforce the length limit. Blank becomes None."""
    stored = None if reason is None else reason.strip()
    if stored is not None and len(stored) > MAX_REASON_LENGTH:
        raise InvalidHandoffReasonError(f"reason must be at most {MAX_REASON_LENGTH} characters")
    return stored or None


def _assignment_ids(db: Session, case: StaffingCase) -> list[int]:
    """Roster rows that close the gap of the case: approved earlier, or assigned by hand."""
    staff_ids = case_facts_service.assigned_staff_ids(db, case.id)
    return list(
        db.scalars(
            select(RosterAssignment.id)
            .where(
                RosterAssignment.shift_id == case.shift_id,
                RosterAssignment.staff_id.in_(staff_ids),
                RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
                RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
            )
            .order_by(RosterAssignment.id)
        )
    )
