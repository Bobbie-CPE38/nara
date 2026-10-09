"""
Candidate plans for a case (docs/workflow.md, sections 6.4 and 8).

The walking skeleton has no solver yet: every case starts from the same Golden
Case candidates (section 10.3). The real solver replaces `create_stub_plan` later.

The stub drops a candidate who cannot take the case's shift at all, by the rules
in availability_service, which Safety uses too. It also drops a candidate who
already holds an open offer (rule 4): a SENT offer in any case, or an ACCEPTED
offer whose case is not in AUTOMATION_STOPPED_STATUSES. Seam 3 needs exactly one
SENT offer per responder across all cases, so a second offer would leave both
cases waiting forever. Rule 4 is the Solver's only: Safety checks the accepted
candidate, whose own ACCEPTED offer would block them.

Rules:
  * Never commits and writes no audit row. The `optimize` handler logs
    SOLVER_EXECUTED in the same round.
  * Each call adds a new plan. Readers take the plan with the highest id for
    the case (seam 1), so a repeated round never mixes candidates.
  * Ranks run 1..n without gaps, so seam 2 always finds exactly one rank 1.
  * No candidate left raises NoCandidatesError before any row is written:
    section 5 has no transition for it yet, so the case becomes FAILED (D11).
  * Rule 4 only sees committed offers (and this session's own). So that two
    cases planned at the same moment cannot both pick the same candidate, the
    candidates' STAFF rows are locked before the rules run, and stay locked
    until the round commits its offer at WAITING_RESPONSE. A second round that
    plans any of the same candidates waits for that commit, then sees the offer.
  * Lock order: STAFF rows always come last, after the case row the
    orchestrator holds (and after event intake's shift and roster locks).
    They are taken in id order, so two rounds never wait on each other in a
    cycle. FOR NO KEY UPDATE, like the orchestrator: inserts with a foreign key
    to STAFF hold KEY SHARE, which FOR UPDATE would block.
"""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Shift,
    Staff,
    StaffingCase,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    CandidateSource,
    OutreachStatus,
    SolverStatus,
)
from app.services import availability_service, policy_service

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
    """Every Golden Case candidate is unavailable for the shift or holds an open offer."""


def create_stub_plan(db: Session, case: StaffingCase) -> tuple[CandidatePlan, list[CandidateItem]]:
    """Add a FEASIBLE plan with the available Golden Case candidates; flush only."""
    shift = db.get(Shift, case.shift_id)
    if shift is None:
        raise LookupError(f"No shift {case.shift_id}")
    staff_ids = [staff_id for staff_id, _ in GOLDEN_CANDIDATES]
    # Wait for any round that is planning the same candidates to commit (see Rules)
    db.execute(
        select(Staff.id)
        .where(Staff.id.in_(staff_ids))
        .order_by(Staff.id)
        .with_for_update(key_share=True)
    )
    blocked = set(availability_service.unavailable_staff(db, shift, staff_ids))
    blocked |= _staff_with_open_offers(db, staff_ids)
    candidates = [
        (staff_id, source) for staff_id, source in GOLDEN_CANDIDATES if staff_id not in blocked
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


def _staff_with_open_offers(db: Session, staff_ids: list[int]) -> set[int]:
    """Rule 4: the staff IDs with a SENT offer, or an ACCEPTED one in a running case."""
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateItem.staff_id.in_(staff_ids),
                or_(
                    CandidateOutreach.status == OutreachStatus.SENT,
                    and_(
                        CandidateOutreach.status == OutreachStatus.ACCEPTED,
                        StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
                    ),
                ),
            )
        )
    )
