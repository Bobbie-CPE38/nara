"""
Candidate plans for a case (docs/workflow.md sections 6.4 and 8; round 1 contract section 8.3).

create_plan() is the Solver step (OR-Tools since round 2 PR B):
  1. Pool (section 6.19): every staff member whose home ward is the ward of the
     case's shift (SAME_WARD), plus staff of other active wards who hold no
     committed roster duty overlapping the shift (FLOAT_POOL when their home ward
     is_float_pool, else CROSS_WARD). Someone on another ward's overlapping shift
     is pooled only when moving them is a whole-shift transfer (PR C2): see
     _movable_rows().
  2. Drop who cannot be offered the shift, each with one reason code. The first
     that applies is kept:
       * the first failed Hard Rule, in the order of HardRuleCode
         (hard_rule_service, the checker Safety uses too);
       * GAP_TIME_MISMATCH (round 4 PR T4, not a Hard Rule): short time slices
         exist and the person's cover window overlaps none of them;
       * nothing to fill: in every short slice the window overlaps, the person
         matches no missing headcount, role or skill (SKILL_MISMATCH when one of
         those slices is short of a skill, else ROLE_MISMATCH). For a whole-shift
         window this is the check on the summary counts;
       * the offer cap (availability_service.staff_at_offer_limit): OFFER_LIMIT_REACHED.
     _covers() gives the cover window (and source assignment) of a candidate who
     would take only part of the shift or be moved out of another shift. PR C2
     gives a movable person the whole shift and their source assignment; PR C3
     fills the partial windows. The hard rules, the solver windows, the item
     columns and the snapshot all read it.
  3. Capture a working-time snapshot of everyone left (working_time_service).
  4. optimization.solver.solve() with the time limit of the soft policy and the
     short time slices of the gap (intervals=): the cheapest group that covers the
     wave targets of every slice is the first wave, and rank lists that group
     first. When no group can cover every target (candidates from one source shift
     exclude each other), the first wave is the group that leaves the fewest
     uncovered person-seconds and the plan is partial. The status is the one the
     solver reports (OPTIMAL, or FEASIBLE when time ran out with a plan in hand).
     MODEL_INVALID raises SolverModelInvalidError and nothing is written.
  5. Store the plan with every candidate left, not only the first wave, and the
     CANDIDATE_ITEM_TARGET rows of the first wave. The snapshot keeps the weights and
     the exact "n/d" values of each candidate (section 6.15), the short slices
     ("intervals"), "partial_plan", and for each first-wave candidate the credits
     with their time windows ("credits"; the table has no time columns). The
     readers of the snapshot ignore keys they do not know.

Rules:
  * The duty filter of the pool is a read before the staff lock. A duty committed
    in between is caught by the Hard Rules after the lock (SHIFT_CONFLICT), which
    judge cross-ward staff exactly as in-ward staff.
  * Never commits and writes no audit row. The `optimize` handler logs
    SOLVER_EXECUTED (and MANUAL_HANDOFF) in the same round.
  * Each call adds a new plan. Readers take the plan with the highest id of the
    case (seam 1), so a repeated round never mixes candidates.
  * Ranks run 1..n without gaps.
  * Nobody left still stores a plan: INFEASIBLE, without items (Q12). The handler
    then stops the case at MANUAL_HANDOFF (T6).
  * The solver out of time with no plan stores UNKNOWN, without items. The handler
    stops the case at MANUAL_HANDOFF with reason SOLVER_TIMEOUT.
  * The offer checks only see committed offers (and this session's own). So that
    two cases planned at the same moment count a shared candidate one after the
    other, the STAFF rows of the pool are locked before the rules run and stay
    locked until the round commits its offers.
  * Lock order: STAFF rows always come last, after the case row the orchestrator
    holds (and after event intake's shift and roster locks), in ID order.
"""

import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any, NamedTuple

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidateItemTarget,
    CandidatePlan,
    RosterAssignment,
    Shift,
    SoftConstraintPolicy,
    Staff,
    StaffingCase,
    Ward,
)
from app.domain.constraints.codes import GAP_TIME_MISMATCH, OFFER_LIMIT_REACHED, HardRuleCode
from app.domain.constraints.context import local_day, projected_consecutive_shifts, week_start
from app.domain.constraints.penalties import SoftWeights
from app.domain.constraints.score_breakdown import display_number, exact_fields, weights_snapshot
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import (
    COMMITTED_ROSTER_STATUSES,
    CandidateSource,
    RosterStatus,
    SolverStatus,
)
from app.domain.staffing.wave_targets import TargetCredit, is_short, wave_target
from app.domain.workflow.case_status import GapFiller, IntervalGap
from app.optimization.solver import SolverCandidate, SolverModelInvalidError, solve
from app.services import (
    availability_service,
    gap_service,
    hard_rule_service,
    policy_service,
    roster_time_service,
    working_time_service,
)
from app.services.gap_service import CaseGap
from app.services.hard_rule_service import FULL_SHIFT, CandidateCheck, Cover

SOLVER_VERSION = "cp-sat-v1"


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

    sources = _pool(db, shift)
    pool = sorted(sources)
    # Wait for any round that is planning the same people to commit (see Rules)
    hard_rule_service.lock_staff(db, pool)
    covers = _covers(db, shift, pool)
    checks = hard_rule_service.check_staff(db, shift=shift, staff_ids=pool, covers=covers)
    at_limit = set(availability_service.staff_at_offer_limit(db, pool))
    short = [interval for interval in case_gap.intervals if is_short(interval)]

    eligible: list[int] = []
    skipped: list[SkippedCandidate] = []
    for staff_id in pool:
        reason = _skip_reason(
            checks[staff_id], short, _cover(covers, staff_id), at_limit=staff_id in at_limit
        )
        if reason is None:
            eligible.append(staff_id)
        else:
            skipped.append(SkippedCandidate(staff_id=staff_id, reason=reason))

    # One reference time for every candidate of this round
    captured_at = clock.now()
    captured = working_time_service.capture(db, eligible, captured_at=captured_at)
    source_shifts = _source_shifts(db, covers, eligible)
    candidates = [
        SolverCandidate(
            filler=GapFiller(
                staff_id=staff_id,
                role_id=checks[staff_id].context.role_id,
                skill_ids=checks[staff_id].context.skill_ids,
                start_at=_cover(covers, staff_id).start_at,
                end_at=_cover(covers, staff_id).end_at,
            ),
            metrics=SoftMetrics(
                staff_id=staff_id,
                source=sources[staff_id],
                hours_this_week=captured[staff_id].values.hours_this_week,
                projected_consecutive_shifts=projected_consecutive_shifts(checks[staff_id].context),
                overtime_hours=captured[staff_id].values.overtime_hours,
            ),
            source_shift_id=source_shifts.get(staff_id),
        )
        for staff_id in eligible
    ]
    result = solve(
        headcount_gap=case_gap.headcount_gap,
        role_gaps=case_gap.role_gaps,
        skill_gaps=case_gap.skill_gaps,
        candidates=candidates,
        weights=weights,
        time_limit_seconds=soft_policy.solver_time_limit_seconds,
        intervals=short,
    )
    if result.status is SolverStatus.MODEL_INVALID:
        raise SolverModelInvalidError(f"Case {case.id}: the solver model is invalid")
    by_staff = {candidate.filler.staff_id: candidate for candidate in candidates}
    ranked = [by_staff[staff_id] for staff_id in result.ranked_staff_ids]
    score = result.objective_score

    plan = CandidatePlan(
        case_id=case.id,
        solver_status=result.status,
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
            "intervals": [_interval_snapshot(interval) for interval in short],
            "partial_plan": result.partial,
            "weights": weights_snapshot(weights),
            "candidates": [
                _candidate_snapshot(
                    candidate,
                    weights,
                    _cover(covers, candidate.filler.staff_id),
                    result.first_wave.get(candidate.filler.staff_id),
                )
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
            cover_start_at=_cover(covers, candidate.metrics.staff_id).start_at,
            cover_end_at=_cover(covers, candidate.metrics.staff_id).end_at,
            source_assignment_id=_cover(covers, candidate.metrics.staff_id).source_assignment_id,
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
    stay immutable after first contact. Uncontacted Solver members selected
    for a later wave have their provisional rows replaced by wave_service.
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


def _pool(db: Session, shift: Shift) -> dict[int, CandidateSource]:
    """Staff ID to source, in ID order, of everyone the Solver may consider (section 6.19).

    The ward of the shift keeps all its people, so a same-ward person with a
    conflict still reaches the Hard Rules and is skipped with a code. Other active
    wards lend only people with no committed duty overlapping [start, end) by its
    effective times, in any ward, or whose only such duty is movable (_movable_rows).
    Staff status is left to the Hard Rules.
    """
    movable = _movable_rows(db, shift)
    overlapping_duty = (
        select(RosterAssignment.id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(
            RosterAssignment.staff_id == Staff.id,
            RosterAssignment.status.in_(list(COMMITTED_ROSTER_STATUSES)),
            roster_time_service.start_at() < shift.end_at,
            roster_time_service.end_at() > shift.start_at,
        )
    )
    rows = db.execute(
        select(Staff.id, Staff.home_ward_id, Ward.is_float_pool)
        .join(Ward, Ward.id == Staff.home_ward_id)
        .where(
            or_(
                Staff.home_ward_id == shift.ward_id,
                Ward.is_active & (~exists(overlapping_duty) | Staff.id.in_(list(movable))),
            )
        )
        .order_by(Staff.id)
    )
    sources: dict[int, CandidateSource] = {}
    for staff_id, home_ward_id, is_float_pool in rows:
        if home_ward_id == shift.ward_id:
            sources[staff_id] = CandidateSource.SAME_WARD
        elif is_float_pool:
            sources[staff_id] = CandidateSource.FLOAT_POOL
        else:
            sources[staff_id] = CandidateSource.CROSS_WARD
    return sources


def _movable_rows(db: Session, shift: Shift) -> dict[int, int]:
    """Staff ID to the source assignment ID, for people who can be moved onto `shift`.

    Round 4 PR C2 moves a whole shift only (workflow.md 6.19). A person is movable
    when their only committed row overlapping the shift (effective times,
    half-open) is an ASSIGNED row, with no actual times other than the shift's
    own, on a shift that
      * is active, in another active ward,
      * has exactly the start and end of `shift`,
      * has not started (until PR C3 handles a move mid-shift).
    """
    source_ward = aliased(Ward)
    rows = db.execute(
        select(
            RosterAssignment.staff_id,
            RosterAssignment.id,
            RosterAssignment.status,
            Shift.ward_id,
            Shift.is_active,
            source_ward.is_active,
            Shift.start_at,
            Shift.end_at,
            RosterAssignment.actual_start_at,
            RosterAssignment.actual_end_at,
        )
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .join(source_ward, source_ward.id == Shift.ward_id)
        .where(
            RosterAssignment.status.in_(list(COMMITTED_ROSTER_STATUSES)),
            roster_time_service.start_at() < shift.end_at,
            roster_time_service.end_at() > shift.start_at,
        )
        .order_by(RosterAssignment.id)
    ).all()
    held: dict[int, list[Any]] = {}
    for row in rows:
        held.setdefault(row[0], []).append(row)
    now = clock.now()
    movable: dict[int, int] = {}
    for staff_id, staff_rows in held.items():
        if len(staff_rows) != 1:
            continue
        (
            _,
            row_id,
            status,
            ward_id,
            shift_active,
            ward_active,
            start_at,
            end_at,
            actual_start,
            actual_end,
        ) = staff_rows[0]
        if (
            status is RosterStatus.ASSIGNED
            and ward_id != shift.ward_id
            and shift_active
            and ward_active
            and start_at == shift.start_at
            and end_at == shift.end_at
            and actual_start in (None, start_at)
            and actual_end in (None, end_at)
            and start_at > now
        ):
            movable[staff_id] = row_id
    return movable


def _covers(db: Session, shift: Shift, pool: Sequence[int]) -> dict[int, Cover]:
    """Staff ID to cover, for people who take only part of the shift or are moved.

    A movable pool member covers the whole shift and leaves their source
    assignment (PR C2, _movable_rows): a same-ward person on another ward's
    equal-time shift is moved too. Partial windows come with PR C3; tests
    monkeypatch this.
    """
    movable = _movable_rows(db, shift)
    return {
        staff_id: Cover(None, None, movable[staff_id]) for staff_id in pool if staff_id in movable
    }


def _cover(covers: Mapping[int, Cover], staff_id: int) -> Cover:
    return covers.get(staff_id, FULL_SHIFT)


def _source_shifts(
    db: Session, covers: Mapping[int, Cover], staff_ids: Iterable[int]
) -> dict[int, int]:
    """Staff ID to the shift they are moved out of, for covers with a source assignment."""
    sources = {
        staff_id: assignment_id
        for staff_id in staff_ids
        if (assignment_id := _cover(covers, staff_id).source_assignment_id) is not None
    }
    if not sources:
        return {}
    shift_of = {
        assignment_id: shift_id
        for assignment_id, shift_id in db.execute(
            select(RosterAssignment.id, RosterAssignment.shift_id).where(
                RosterAssignment.id.in_(set(sources.values()))
            )
        )
    }
    return {
        staff_id: shift_of[assignment_id]
        for staff_id, assignment_id in sources.items()
        if assignment_id in shift_of
    }


def _overlaps(cover: Cover, interval: IntervalGap) -> bool:
    """True when the cover window shares time with the slice (half-open; no bound = open)."""
    return (cover.start_at is None or cover.start_at < interval.end_at) and (
        cover.end_at is None or cover.end_at > interval.start_at
    )


def _skip_reason(
    check: CandidateCheck, short: Sequence[IntervalGap], cover: Cover, *, at_limit: bool
) -> str | None:
    """The code of the first reason to leave the person out, or None.

    `short` is the short time slices of the gap. For a whole-shift cover the slice
    checks equal the old check on the summary counts.
    """
    if check.result.failed_rules:
        return check.result.failed_rules[0].value
    reached = [interval for interval in short if _overlaps(cover, interval)]
    if short and not reached:
        return GAP_TIME_MISMATCH
    context = check.context
    fills_something = any(
        interval.headcount_gap > 0
        or context.role_id in interval.role_gaps
        or any(skill_id in interval.skill_gaps for skill_id in context.skill_ids)
        for interval in reached
    )
    if not fills_something:
        missing = (
            HardRuleCode.SKILL_MISMATCH
            if any(interval.skill_gaps for interval in reached)
            else HardRuleCode.ROLE_MISMATCH
        )
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
    return _gap_snapshot(case_gap.headcount_gap, case_gap.role_gaps, case_gap.skill_gaps)


def _gap_snapshot(
    headcount_gap: int, role_gaps: Mapping[int, int], skill_gaps: Mapping[int, int]
) -> dict[str, Any]:
    return {
        "headcount": {"gap": headcount_gap, "target": wave_target(headcount_gap)},
        "roles": [
            {"role_id": role_id, "gap": gap, "target": wave_target(gap)}
            for role_id, gap in sorted(role_gaps.items())
        ],
        "skills": [
            {"skill_id": skill_id, "gap": gap, "target": wave_target(gap)}
            for skill_id, gap in sorted(skill_gaps.items())
        ],
    }


def _interval_snapshot(interval: IntervalGap) -> dict[str, Any]:
    """One short time slice: its window and its targets, in the shape of "targets"."""
    return {
        "start_at": interval.start_at.isoformat(),
        "end_at": interval.end_at.isoformat(),
        **_gap_snapshot(interval.headcount_gap, interval.role_gaps, interval.skill_gaps),
    }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _candidate_snapshot(
    candidate: SolverCandidate,
    weights: SoftWeights,
    cover: Cover,
    credits: Iterable[TargetCredit] | None,
) -> dict[str, Any]:
    """One candidate of the snapshot: display numbers plus the exact "n/d" text (section 6.15).

    `credits` is None for someone outside the first wave; otherwise their credits
    with the time window each one counts in (null = the whole shift).
    """
    metrics = candidate.metrics
    exact = exact_fields(metrics, weights)
    entry: dict[str, Any] = {
        "staff_id": metrics.staff_id,
        "source": metrics.source.value,
        "hours_this_week": display_number(metrics.hours_this_week),
        "projected_consecutive_shifts": metrics.projected_consecutive_shifts,
        "overtime_hours": display_number(metrics.overtime_hours),
        "penalty": display_number(Fraction(exact["penalty_exact"])),
        "first_wave": credits is not None,
        # Datetimes as isoformat() like captured_at; null for the whole shift
        "cover_start_at": _iso(cover.start_at),
        "cover_end_at": _iso(cover.end_at),
        "source_assignment_id": cover.source_assignment_id,
        **exact,
    }
    if credits is not None:
        entry["credits"] = [
            {
                "target_type": credit.target_type.value,
                "selection_type": credit.selection_type.value,
                "role_id": credit.role_id,
                "skill_id": credit.skill_id,
                "start_at": _iso(credit.start_at),
                "end_at": _iso(credit.end_at),
            }
            for credit in credits
        ]
    return entry
