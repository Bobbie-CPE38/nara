"""Row builders for tests of a case with several candidates (round 1).

Each helper writes the rows one step of the workflow would write, and flushes.
The seeded Golden Case supplies the people: 201 (RN, ICU + BLS), 202 (RN, BLS)
and 203 (RN, ICU) are free on the night shift.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    RosterAssignment,
    SafetyValidation,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import (
    ApprovalMode,
    AssignmentType,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    Channel,
    EventStatus,
    EventType,
    OutreachStatus,
    RosterStatus,
    SolverStatus,
)
from app.services import gap_service
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT = 1, 2
RN, ICU = 1, 1
CANDIDATES = (201, 202, 203)


def cancel_roster(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> None:
    row = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()
    row.status = RosterStatus.CANCELLED
    db.flush()


def leave(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> None:
    """What closing the merge window does for a leave: cancel the roster row and record the absence.

    Without the unavailability row the person is still a free RN of the ward and
    the Solver would offer them the shift they just left.
    """
    cancel_roster(db, staff_id, shift_id)
    shift = db.get(Shift, shift_id)
    assert shift is not None
    db.add(
        StaffUnavailability(
            staff_id=staff_id,
            start_at=shift.start_at,
            end_at=shift.end_at,
            reason=AvailabilityReason.UNPLANNED_LEAVE,
        )
    )
    db.flush()


def make_case(
    db: Session,
    status: CaseStatus = CaseStatus.WAITING_RESPONSE,
    *,
    shift_id: int = NIGHT_SHIFT,
) -> StaffingCase:
    """A case without a gap or a plan yet."""
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift_id,
        occurred_at=DEMO_NOW,
        staff_id=105,
        status=EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        shift_id=shift_id,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    event.case_id = case.id
    db.flush()
    return case


def record_gap(db: Session, case: StaffingCase) -> None:
    """Store the current gap of the case's shift as the gap of the case."""
    shift = db.get(Shift, case.shift_id)
    assert shift is not None
    gap_service.record_gap(db, case, gap_service.assess_shift(db, shift))


def make_plan(
    db: Session, case: StaffingCase, staff_ids: tuple[int, ...] = CANDIDATES
) -> dict[int, CandidateItem]:
    """A plan of the case with one item per candidate, keyed by staff ID."""
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="test",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    items = {
        staff_id: CandidateItem(
            plan_id=plan.id,
            staff_id=staff_id,
            rank=rank,
            source=CandidateSource.SAME_WARD,
            proposed_shift_id=case.shift_id,
        )
        for rank, staff_id in enumerate(staff_ids, start=1)
    }
    db.add_all(items.values())
    db.flush()
    return items


def short_case(
    db: Session,
    *leaving_staff: int,
    status: CaseStatus = CaseStatus.WAITING_RESPONSE,
) -> tuple[StaffingCase, dict[int, CandidateItem]]:
    """A night-shift case whose gap is what the given staff left behind, with a plan.

    105 leaves by default: one RN short, ICU still covered.
    """
    for staff_id in leaving_staff or (105,):
        cancel_roster(db, staff_id)
    case = make_case(db, status)
    record_gap(db, case)
    return case, make_plan(db, case)


def offer(
    db: Session,
    case: StaffingCase,
    item: CandidateItem,
    status: OutreachStatus = OutreachStatus.SENT,
) -> CandidateOutreach:
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        sent_at=DEMO_NOW,
        status=status,
    )
    db.add(outreach)
    db.flush()
    return outreach


def approval(
    db: Session,
    case: StaffingCase,
    item: CandidateItem,
    *,
    approved: bool | None = None,
) -> ApprovalRequest:
    """An approval request: pending by default, decided when `approved` is given."""
    head_nurse = db.scalars(select(Role.id).where(Role.name == "HEAD_NURSE")).one()
    request = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=head_nurse,
        approval_mode=ApprovalMode.MANUAL,
        is_pending=approved is None,
        is_approved=approved,
        approver_id=None if approved is None else 900,
        decided_at=None if approved is None else DEMO_NOW,
        requested_at=DEMO_NOW,
    )
    db.add(request)
    db.flush()
    return request


def replacement(db: Session, item: CandidateItem) -> RosterAssignment:
    """The roster row an approval creates for the candidate."""
    row = RosterAssignment(
        staff_id=item.staff_id,
        shift_id=item.proposed_shift_id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        candidate_source=item.source,
    )
    db.add(row)
    db.flush()
    return row


def assign(db: Session, case: StaffingCase, item: CandidateItem) -> None:
    """Approve the candidate and put them on the roster, as one approval does."""
    approval(db, case, item, approved=True)
    replacement(db, item)


def safety(
    db: Session, case: StaffingCase, item: CandidateItem, *, passed: bool
) -> SafetyValidation:
    """The Safety row written when the candidate accepted."""
    row = SafetyValidation(
        case_id=case.id,
        candidate_item_id=item.id,
        hard_constraint_policy_id=1,
        is_passed=passed,
        failure_reason=None if passed else "SHIFT_CONFLICT",
        validation_snapshot={},
        validated_at=DEMO_NOW,
    )
    db.add(row)
    db.flush()
    return row
