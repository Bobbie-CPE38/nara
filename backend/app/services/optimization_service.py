"""
Candidate plans for a case (docs/workflow.md, sections 6.4 and 8).

The walking skeleton has no solver yet: every case gets the same Golden Case
candidates (section 10.3). The real solver replaces `create_stub_plan` later.

Rules:
  * Never commits and writes no audit row. The `optimize` handler logs
    SOLVER_EXECUTED in the same round.
  * Each call adds a new plan. Readers take the plan with the highest id for
    the case (seam 1), so a repeated round never mixes candidates.
"""

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidatePlan, StaffingCase
from app.domain.enums import CandidateSource, SolverStatus
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


def create_stub_plan(db: Session, case: StaffingCase) -> tuple[CandidatePlan, list[CandidateItem]]:
    """Add a FEASIBLE plan with the Golden Case candidates for the case's shift; flush only."""
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
        for rank, (staff_id, source) in enumerate(GOLDEN_CANDIDATES, start=1)
    ]
    db.add_all(items)
    db.flush()
    return plan, items
