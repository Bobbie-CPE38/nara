"""
Candidate plans for a case (docs/workflow.md sections 6.4 and 8; round 1 contract section 8.3).

create_plan() is the round 1 Solver:
  1. Pool: every staff member whose home ward is the ward of the case's shift.
     Round 1 has no cross-ward candidates, so everyone is SAME_WARD.
  2. Drop who cannot be offered the shift, each with one reason code. The first
     that applies is kept:
       * the first failed Hard Rule, in the order of HardRuleCode
         (hard_rule_service, the checker Safety uses too);
       * nothing to fill: the case is short of a role or a skill only and the
         person has none of them (SKILL_MISMATCH when a skill is short, else
         ROLE_MISMATCH);
       * the offer cap (availability_service.staff_at_offer_limit): OFFER_LIMIT_REACHED.
  3. Capture a working-time snapshot of everyone left (working_time_service).
  4. optimization.solver.solve(): the cheapest group that covers the wave targets
     is the first wave, and rank lists that group first.
  5. Store the plan with every candidate left, not only the first wave, and the
     CANDIDATE_ITEM_TARGET rows of the first wave.

Rules:
  * Never commits and writes no audit row. The `optimize` handler logs
    SOLVER_EXECUTED (and MANUAL_HANDOFF) in the same round.
  * Each call adds a new plan. Readers take the plan with the highest id of the
    case (seam 1), so a repeated round never mixes candidates.
  * Ranks run 1..n without gaps.
  * Nobody left still stores a plan: INFEASIBLE, without items (Q12). The handler
    then stops the case at MANUAL_HANDOFF (T6).
  * The offer checks only see committed offers (and this session's own). So that
    two cases planned at the same moment count a shared candidate one after the
    other, the STAFF rows of the pool are locked before the rules run and stay
    locked until the round commits its offers.
  * Lock order: STAFF rows always come last, after the case row the orchestrator
    holds (and after event intake's shift and roster locks), in ID order.
"""

import time
from collections.abc import Iterable
from decimal import Decimal
from fractions import Fraction
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidateItemTarget,
    CandidatePlan,
    Shift,
    SoftConstraintPolicy,
    Staff,
    StaffingCase,
)
from app.domain.constraints.codes import OFFER_LIMIT_REACHED, HardRuleCode
from app.domain.constraints.context import local_day, projected_consecutive_shifts, week_start
from app.domain.constraints.penalties import SoftWeights, candidate_penalty
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import (
    CandidateSource,
    SolverStatus,
)
from app.domain.staffing.wave_targets import TargetCredit, wave_target
from app.domain.workflow.case_status import GapFiller
from app.optimization.solver import SolverCandidate, solve
from app.services import (
    availability_service,
    gap_service,
    hard_rule_service,
    policy_service,
    working_time_service,
)
from app.services.gap_service import CaseGap
from app.services.hard_rule_service import CandidateCheck

SOLVER_VERSION = "weighted-v1"


class SkippedCandidate(NamedTuple):
    """Someone of the pool the Solver left out, with the code of the reason."""

    staff_id: int
    reason: str


class PlanResult(NamedTuple):
    plan: CandidatePlan
    # In rank order. Empty when the plan is INFEASIBLE
    items: list[CandidateItem]
    # In staff ID order
    skipped: list[SkippedCandidate]


def create_plan(db: Session, case: StaffingCase) -> PlanResult:
    """Plan the candidates of the case's shift; flush only."""
    started = time.perf_counter()
    # The gap and the leave of this round may still be pending (autoflush is off)
    db.flush()
    shift = db.get(Shift, case.shift_id)
    if shift is None:
        raise LookupError(f"No shift {case.shift_id}")
    case_gap = gap_service.get_case_gap(db, case.id)
    hard_policy = policy_service.get_hard_constraint_policy(db)
    soft_policy = policy_service.get_soft_constraint_policy(db)
    weights = _weights(soft_policy)

    pool = sorted(db.scalars(select(Staff.id).where(Staff.home_ward_id == shift.ward_id)))
    # Wait for any round that is planning the same people to commit (see Rules)
    hard_rule_service.lock_staff(db, pool)
    checks = hard_rule_service.check_staff(db, shift=shift, staff_ids=pool)
    at_limit = set(availability_service.staff_at_offer_limit(db, pool))

    eligible: list[int] = []
    skipped: list[SkippedCandidate] = []
    for staff_id in pool:
        reason = _skip_reason(checks[staff_id], case_gap, at_limit=staff_id in at_limit)
        if reason is None:
            eligible.append(staff_id)
        else:
            skipped.append(SkippedCandidate(staff_id=staff_id, reason=reason))

    # One reference time for every candidate of this round
    captured_at = clock.now()
    captured = working_time_service.capture(db, eligible, captured_at=captured_at)
    candidates = [
        SolverCandidate(
            filler=GapFiller(
                staff_id=staff_id,
                role_id=checks[staff_id].context.role_id,
                skill_ids=checks[staff_id].context.skill_ids,
            ),
            metrics=SoftMetrics(
                staff_id=staff_id,
                source=CandidateSource.SAME_WARD,
                hours_this_week=captured[staff_id].values.hours_this_week,
                projected_consecutive_shifts=projected_consecutive_shifts(checks[staff_id].context),
                overtime_hours=captured[staff_id].values.overtime_hours,
            ),
        )
        for staff_id in eligible
    ]
    result = solve(
        headcount_gap=case_gap.headcount_gap,
        role_gaps=case_gap.role_gaps,
        skill_gaps=case_gap.skill_gaps,
        candidates=candidates,
        weights=weights,
    )
    by_staff = {candidate.filler.staff_id: candidate for candidate in candidates}
    ranked = [by_staff[staff_id] for staff_id in result.ranked_staff_ids]
    score = result.objective_score

    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE if ranked else SolverStatus.INFEASIBLE,
        generated_at=captured_at,
        execution_time_ms=int((time.perf_counter() - started) * 1000),
        objective_score=None if score is None else Decimal(score.numerator) / score.denominator,
        solver_version=SOLVER_VERSION,
        hard_constraint_policy_id=hard_policy.id,
        soft_constraint_policy_id=soft_policy.id,
        input_snapshot={
            "captured_at": captured_at.isoformat(),
            "timezone": "Asia/Bangkok",
            # Q14: a shift belongs to the day and the week it starts in
            "day": local_day(captured_at).isoformat(),
            "week_start": week_start(captured_at).isoformat(),
            "gap_id": case_gap.gap.id,
            "targets": _targets_snapshot(case_gap),
            "candidates": [
                {
                    "staff_id": candidate.metrics.staff_id,
                    "source": candidate.metrics.source.value,
                    "hours_this_week": _number(candidate.metrics.hours_this_week),
                    "projected_consecutive_shifts": candidate.metrics.projected_consecutive_shifts,
                    "overtime_hours": _number(candidate.metrics.overtime_hours),
                    "penalty": _number(candidate_penalty(candidate.metrics, weights)),
                    "first_wave": candidate.metrics.staff_id in result.first_wave,
                }
                for candidate in ranked
            ],
            "skipped": [{"staff_id": row.staff_id, "reason": row.reason} for row in skipped],
        },
    )
    db.add(plan)
    # The items need plan.id, and SessionLocal has autoflush off
    db.flush()

    items = [
        CandidateItem(
            plan_id=plan.id,
            staff_id=candidate.metrics.staff_id,
            rank=rank,
            source=candidate.metrics.source,
            proposed_shift_id=case.shift_id,
            working_time_snapshot_id=captured[candidate.metrics.staff_id].snapshot.id,
        )
        for rank, candidate in enumerate(ranked, start=1)
    ]
    db.add_all(items)
    db.flush()
    for item in items:
        if item.staff_id in result.first_wave:
            record_item_targets(db, item, result.first_wave[item.staff_id])
    return PlanResult(plan=plan, items=items, skipped=skipped)


def record_item_targets(db: Session, item: CandidateItem, credits: Iterable[TargetCredit]) -> None:
    """Store the targets a candidate was selected to fill; flush but never commit.

    Two writers: the Solver for the first wave, and contact_candidate for everyone
    it selects itself, before it sends the offer (workflow.md section 6.6). Rows
    are written once and never changed.
    """
    db.add_all(
        CandidateItemTarget(
            candidate_item_id=item.id,
            target_type=credit.target_type,
            role_id=credit.role_id,
            skill_id=credit.skill_id,
            selection_type=credit.selection_type,
        )
        for credit in credits
    )
    db.flush()


def _skip_reason(check: CandidateCheck, case_gap: CaseGap, *, at_limit: bool) -> str | None:
    """The code of the first reason to leave the person out, or None."""
    if check.result.failed_rules:
        return check.result.failed_rules[0].value
    context = check.context
    fills_something = (
        case_gap.headcount_gap > 0
        or context.role_id in case_gap.role_gaps
        or any(skill_id in case_gap.skill_gaps for skill_id in context.skill_ids)
    )
    if not fills_something:
        missing = HardRuleCode.SKILL_MISMATCH if case_gap.skill_gaps else HardRuleCode.ROLE_MISMATCH
        return missing.value
    if at_limit:
        return OFFER_LIMIT_REACHED
    return None


def _weights(policy: SoftConstraintPolicy) -> SoftWeights:
    return SoftWeights(
        candidate_count=Fraction(policy.candidate_count_weight),
        consecutive_shift=Fraction(policy.consecutive_shift_weight),
        workload_imbalance=Fraction(policy.workload_imbalance_weight),
        projected_overtime=Fraction(policy.projected_overtime_weight),
        roster_change=Fraction(policy.roster_change_weight),
        candidate_source=Fraction(policy.candidate_source_weight),
        source_order=tuple(CandidateSource(value) for value in policy.candidate_source_priority),
    )


def _targets_snapshot(case_gap: CaseGap) -> dict[str, Any]:
    """Lists ordered by ID: JSON would turn integer mapping keys into text."""
    return {
        "headcount": {
            "gap": case_gap.headcount_gap,
            "target": wave_target(case_gap.headcount_gap),
        },
        "roles": [
            {"role_id": role_id, "gap": gap, "target": wave_target(gap)}
            for role_id, gap in sorted(case_gap.role_gaps.items())
        ],
        "skills": [
            {"skill_id": skill_id, "gap": gap, "target": wave_target(gap)}
            for skill_id, gap in sorted(case_gap.skill_gaps.items())
        ],
    }


def _number(value: Fraction) -> int | float:
    """A JSON number: whole values stay integers."""
    return value.numerator if value.denominator == 1 else float(value)
