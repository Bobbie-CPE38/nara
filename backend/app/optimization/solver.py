"""Round 2 Solver: choose the first wave and rank the plan (round 2 contract, section 4).

Input: the gap of a case and the candidates that passed the Hard Rules, each
with their Soft Constraint values. Output: who is in the first wave, which
targets each of them fills, the rank of every candidate, and a status.

  1. Wave targets: ceil(gap * 11 / 10) for headcount, each short role and each
     short skill. A target the candidates cannot reach is lowered to the number
     of candidates that match it, so a small pool still gives the widest wave.
  2. First wave: the group that covers every target with the lowest
     plan_penalty. Ties: fewer people, then the lexicographically smallest
     sorted tuple of staff IDs. This is the round 1 rule, unchanged.
  3. fill_targets() inside that group says which targets each member fills.
  4. rank: the first wave in ranking_key order, then everyone else in
     ranking_key order. plan_penalty decides who is in the group. ranking_key
     only orders people, so the two can disagree about who looks better.

The group comes from a CP-SAT model with one 0/1 variable per candidate and three
stages, each fixed before the next starts: (1) minimize the penalty, scaled to
integers exactly, (2) minimize the number of people, (3) the lowest staff IDs: in
staff ID order, blocks of _BLOCK candidates, each block one round that maximizes
the sum of x * 2^(place in the block, counted from the end). That sum is larger
for the set that has the earliest ID at the first place where two sets differ, so
one round gives the same choice as deciding the candidates one by one. Every
round shares one time budget (time_limit_seconds, read from policy by the caller). Status:
OPTIMAL when every round was proved; FEASIBLE when time ran out or a round ended
unproved after a plan was kept, and that plan is returned; UNKNOWN when time ran
out before any plan; INFEASIBLE when there are no candidates; MODEL_INVALID when
the model is rejected or CP-SAT calls it infeasible although the candidates
satisfy it.

No database access, clock reads, or writes.
"""

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from time import monotonic as _monotonic

from ortools.sat.python import cp_model

from app.domain.constraints.penalties import SoftWeights, candidate_penalty, plan_penalty
from app.domain.constraints.soft_metrics import SoftMetrics, ranking_key
from app.domain.enums import SolverStatus
from app.domain.staffing.wave_targets import TargetCredit, fill_targets, wave_target
from app.domain.workflow.case_status import GapFiller

# The largest sum of scaled costs the model accepts: CP-SAT works in 64-bit integers
_MAX_SCALED_TOTAL = 2**60
# Candidates decided by one stage 3 round. The weights 2^0 to 2^(_BLOCK - 1) add up
# to less than 2^_BLOCK, far below the 64-bit limit
_BLOCK = 40


class SolverScalingOverflowError(RuntimeError):
    """The costs cannot be scaled to integers CP-SAT accepts, and rounding is not allowed."""


class SolverModelInvalidError(RuntimeError):
    """The model was rejected, or CP-SAT called it infeasible. Raised by the caller."""


@dataclass(frozen=True)
class SolverCandidate:
    """A candidate that passed the Hard Rules and can fill at least one open gap."""

    filler: GapFiller
    metrics: SoftMetrics

    def __post_init__(self) -> None:
        if self.filler.staff_id != self.metrics.staff_id:
            raise ValueError("filler and metrics belong to different staff")


@dataclass(frozen=True)
class SolverResult:
    """What the plan stores.

    ranked_staff_ids: every candidate, rank 1 first. Empty without a plan.
    first_wave: staff ID -> the targets that person fills, in the order chosen.
    objective_score: plan_penalty of the first wave. None without a plan.
    status: OPTIMAL or FEASIBLE come with a plan, the others without one.
    """

    ranked_staff_ids: tuple[int, ...]
    first_wave: Mapping[int, tuple[TargetCredit, ...]]
    objective_score: Fraction | None
    status: SolverStatus


@dataclass(frozen=True)
class _Round:
    """One CP-SAT run. values: x in variable order, None unless OPTIMAL or FEASIBLE."""

    status: SolverStatus
    values: tuple[int, ...] | None


@dataclass(frozen=True)
class _Selection:
    """The chosen group, or None when there is no plan to return."""

    group: tuple[SolverCandidate, ...] | None
    status: SolverStatus


def solve(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    candidates: Sequence[SolverCandidate],
    weights: SoftWeights,
    time_limit_seconds: float,
) -> SolverResult:
    """Choose the first wave and rank every candidate."""
    if time_limit_seconds <= 0:
        raise ValueError("The time limit must be positive")
    if not candidates:
        return SolverResult((), {}, None, SolverStatus.INFEASIBLE)
    by_id = {candidate.filler.staff_id: candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("A candidate is listed twice")

    def order(candidate: SolverCandidate) -> tuple[int, Fraction, int, Fraction, int]:
        return ranking_key(candidate.metrics, weights.source_order)

    selection = _cheapest_covering_group(
        candidates,
        headcount_gap=headcount_gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        weights=weights,
        time_limit_seconds=time_limit_seconds,
    )
    if selection.group is None:
        return SolverResult((), {}, None, selection.status)
    first_wave = fill_targets(
        headcount_gap=headcount_gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        candidates=[candidate.filler for candidate in sorted(selection.group, key=order)],
    )
    wave = sorted((by_id[staff_id] for staff_id in first_wave), key=order)
    rest = sorted(
        (candidate for candidate in candidates if candidate.filler.staff_id not in first_wave),
        key=order,
    )
    return SolverResult(
        ranked_staff_ids=tuple(candidate.filler.staff_id for candidate in (*wave, *rest)),
        first_wave=first_wave,
        objective_score=plan_penalty((candidate.metrics for candidate in wave), weights),
        status=selection.status,
    )


def _scaled_costs(costs: Sequence[Fraction]) -> list[int]:
    """Integers in the same proportion as the costs: exact, no rounding."""
    scale = math.lcm(*(cost.denominator for cost in costs))
    values = [cost.numerator * (scale // cost.denominator) for cost in costs]
    divisor = math.gcd(*values) or 1
    values = [value // divisor for value in values]
    if sum(abs(value) for value in values) > _MAX_SCALED_TOTAL:
        raise SolverScalingOverflowError("The costs are too large to scale to integers")
    return values


def _run_cp_sat(
    model: cp_model.CpModel, variables: Sequence[cp_model.IntVar], seconds: float
) -> _Round:
    """The only place that runs OR-Tools, so tests can replace it."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    outcome = solver.solve(model)
    if outcome == cp_model.OPTIMAL:
        status = SolverStatus.OPTIMAL
    elif outcome == cp_model.FEASIBLE:
        status = SolverStatus.FEASIBLE
    elif outcome == cp_model.INFEASIBLE:
        return _Round(SolverStatus.INFEASIBLE, None)
    elif outcome == cp_model.UNKNOWN:
        return _Round(SolverStatus.UNKNOWN, None)
    else:
        return _Round(SolverStatus.MODEL_INVALID, None)
    return _Round(status, tuple(solver.value(variable) for variable in variables))


def _cheapest_covering_group(
    candidates: Sequence[SolverCandidate],
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    weights: SoftWeights,
    time_limit_seconds: float,
) -> _Selection:
    deadline = _monotonic() + time_limit_seconds
    people = sorted(candidates, key=lambda candidate: candidate.filler.staff_id)

    # A target nobody can reach is lowered to what the candidates can give
    role_holders = Counter(candidate.filler.role_id for candidate in people)
    skill_holders = Counter(
        skill_id for candidate in people for skill_id in candidate.filler.skill_ids
    )
    headcount = min(wave_target(headcount_gap), len(people))
    roles = {
        role_id: min(wave_target(gap), role_holders[role_id]) for role_id, gap in role_gaps.items()
    }
    skills = {
        skill_id: min(wave_target(gap), skill_holders[skill_id])
        for skill_id, gap in skill_gaps.items()
    }
    costs = _scaled_costs([candidate_penalty(candidate.metrics, weights) for candidate in people])

    model = cp_model.CpModel()
    variables = [model.new_bool_var(f"x{candidate.filler.staff_id}") for candidate in people]
    if headcount > 0:
        model.add(sum(variables) >= headcount)
    for role_id, role_target in roles.items():
        if role_target > 0:
            holders = [
                variable
                for variable, candidate in zip(variables, people, strict=True)
                if candidate.filler.role_id == role_id
            ]
            model.add(sum(holders) >= role_target)
    for skill_id, skill_target in skills.items():
        if skill_target > 0:
            holders = [
                variable
                for variable, candidate in zip(variables, people, strict=True)
                if skill_id in candidate.filler.skill_ids
            ]
            model.add(sum(holders) >= skill_target)
    cost_sum = cp_model.LinearExpr.weighted_sum(variables, costs)
    count_sum = cp_model.LinearExpr.sum(variables)
    # Checked with the stage 1 objective set: the scaled costs are the large numbers
    model.minimize(cost_sum)
    if model.validate():
        return _Selection(None, SolverStatus.MODEL_INVALID)

    # The last usable x, kept as a plain tuple apart from the solver
    kept: tuple[int, ...] = ()

    def group_of(values: tuple[int, ...]) -> tuple[SolverCandidate, ...]:
        return tuple(c for c, value in zip(people, values, strict=True) if value == 1)

    def run(objective: cp_model.LinearExprT, *, maximize: bool = False) -> _Selection | None:
        """One round: a selection means stop with it, None means go on."""
        nonlocal kept
        # minimize() and maximize() clear the previous objective first
        if maximize:
            model.maximize(objective)
        else:
            model.minimize(objective)
        remaining = deadline - _monotonic()
        outcome = (
            _Round(SolverStatus.UNKNOWN, None)
            if remaining <= 0
            else _run_cp_sat(model, variables, remaining)
        )
        if outcome.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
            if outcome.values is None:
                return _Selection(None, SolverStatus.MODEL_INVALID)
            kept = outcome.values
            if outcome.status is SolverStatus.FEASIBLE:
                return _Selection(group_of(kept), SolverStatus.FEASIBLE)
            return None
        if outcome.status is SolverStatus.UNKNOWN:
            # Only a timeout may fall back to the kept plan; never read this round's values
            if kept:
                return _Selection(group_of(kept), SolverStatus.FEASIBLE)
            return _Selection(None, SolverStatus.UNKNOWN)
        # INFEASIBLE cannot happen when the model is right: the kept plan satisfies it
        return _Selection(None, SolverStatus.MODEL_INVALID)

    # Stage 1: the lowest penalty. The value to fix comes from the integer costs
    stop = run(cost_sum)
    if stop is not None:
        return stop
    model.add(cost_sum == sum(cost * value for cost, value in zip(costs, kept, strict=True)))

    # Stage 2: the fewest people at that penalty
    stop = run(count_sum)
    if stop is not None:
        return stop
    size = sum(kept)
    model.add(count_sum == size)

    # Stage 3: the smallest staff IDs, a block of candidates in ID order per round
    chosen = 0
    for start in range(0, len(variables), _BLOCK):
        if chosen == size or size - chosen == len(variables) - start:
            break
        block = variables[start : start + _BLOCK]
        weights_of_block = [2 ** (len(block) - 1 - place) for place in range(len(block))]
        stop = run(cp_model.LinearExpr.weighted_sum(block, weights_of_block), maximize=True)
        if stop is not None:
            return stop
        for variable, value in zip(block, kept[start : start + _BLOCK], strict=True):
            model.add(variable == value)
        chosen += sum(kept[start : start + _BLOCK])
    return _Selection(group_of(kept), SolverStatus.OPTIMAL)
