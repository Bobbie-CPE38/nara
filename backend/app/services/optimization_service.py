"""
Candidate plans for a case (docs/workflow.md, sections 6.4 and 8).

The walking skeleton has no solver yet: every case starts from the same Golden
Case candidates (section 10.3). The real solver replaces `create_stub_plan` later.

The stub drops a candidate who cannot take the case's shift at all:
  * not ACTIVE,
  * already has a committed roster row (COMMITTED_ROSTER_STATUSES) on that shift,
  * has STAFF_UNAVAILABILITY overlapping that shift (no end_at = from start_at on).
Clashes with other shifts are left to the real hard rules.

Rules:
  * Never commits and writes no audit row. The `optimize` handler logs
    SOLVER_EXECUTED in the same round.
  * Each call adds a new plan. Readers take the plan with the highest id for
    the case (seam 1), so a repeated round never mixes candidates.
  * Ranks run 1..n without gaps, so seam 2 always finds exactly one rank 1.
  * No candidate left raises NoCandidatesError before any row is written:
    section 5 has no transition for it yet, so the case becomes FAILED (D11).
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidatePlan,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffUnavailability,
)
from app.domain.enums import COMMITTED_ROSTER_STATUSES, CandidateSource, SolverStatus, StaffStatus
from app.services import policy_service

# Golden Case candidates in rank order, all from ICU (home ward 1). Outreach
# contacts rank 1, and the roster copies item.source (seam 8), so SAME_WARD
# is part of the contract, not a placeholder.
GOLDEN_CANDIDATES: tuple[tuple[int, CandidateSource], ...] = (
    (201, CandidateSource.SAME_WARD),
    (202, CandidateSource.SAME_WARD),
    (203, CandidateSource.SAME_WARD),
)
STUB_SOLVER_VERSION = "stub"


class NoCandidatesError(LookupError):
    """Every Golden Case candidate is inactive, on the shift already or unavailable."""


def create_stub_plan(db: Session, case: StaffingCase) -> tuple[CandidatePlan, list[CandidateItem]]:
    """Add a FEASIBLE plan with the available Golden Case candidates; flush only."""
    shift = db.get(Shift, case.shift_id)
    if shift is None:
        raise LookupError(f"No shift {case.shift_id}")
    available = _available_staff_ids(db, shift, [staff_id for staff_id, _ in GOLDEN_CANDIDATES])
    candidates = [
        (staff_id, source) for staff_id, source in GOLDEN_CANDIDATES if staff_id in available
    ]
    if not candidates:
        raise NoCandidatesError(f"No Golden Case candidate can take shift {shift.id}")

    hard_policy = policy_service.get_hard_constraint_policy(db)
    soft_policy = policy_service.get_soft_constraint_policy(db)

    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=clock.now(),
        execution_time_ms=0,
        objective_score=None,
        solver_version=STUB_SOLVER_VERSION,
        hard_constraint_policy_id=hard_policy.id,
        soft_constraint_policy_id=soft_policy.id,
        input_snapshot={},
    )
    db.add(plan)
    # The items need plan.id, and SessionLocal has autoflush off
    db.flush()

    items = [
        CandidateItem(
            plan_id=plan.id,
            staff_id=staff_id,
            rank=rank,
            source=source,
            proposed_shift_id=case.shift_id,
        )
        for rank, (staff_id, source) in enumerate(candidates, start=1)
    ]
    db.add_all(items)
    db.flush()
    return plan, items


def _available_staff_ids(db: Session, shift: Shift, staff_ids: list[int]) -> set[int]:
    """The subset of staff_ids who are ACTIVE, not on the shift and not unavailable for it."""
    active = set(
        db.scalars(
            select(Staff.id).where(Staff.id.in_(staff_ids), Staff.status == StaffStatus.ACTIVE)
        )
    )
    on_shift = set(
        db.scalars(
            select(RosterAssignment.staff_id).where(
                RosterAssignment.staff_id.in_(staff_ids),
                RosterAssignment.shift_id == shift.id,
                RosterAssignment.status.in_(list(COMMITTED_ROSTER_STATUSES)),
            )
        )
    )
    unavailable = set(
        db.scalars(
            select(StaffUnavailability.staff_id).where(
                StaffUnavailability.staff_id.in_(staff_ids),
                StaffUnavailability.start_at < shift.end_at,
                or_(
                    StaffUnavailability.end_at.is_(None),
                    StaffUnavailability.end_at > shift.start_at,
                ),
            )
        )
    )
    return active - on_shift - unavailable
