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

Round 4 PR T4 makes the Solver work per time slice. solve(intervals=...) takes
the short slices of the gap; each one is cut where a candidate starts or ends
inside it (elementary_slices), and a candidate holds a need only if present for
the whole piece. One need per (piece, target): sum(holders) >= target, with the
target lowered to the number of holders in that piece, so a piece nobody covers
costs nothing. Duplicate needs across pieces are dropped. The first wave comes
from fill_targets_by_slice(). intervals=None is the legacy single whole-shift
slice with the summary counts and gives exactly the same model as before (the
round 2 baseline must pass unchanged).

Candidates that share a source_shift_id are exclusive: sum(x) <= 1 (R4-Q25). With
that constraint "cover every target" can be impossible, so a stage 1 INFEASIBLE is
no longer a model bug there: the partial plan of R4-Q37/R4-Q39 runs instead, with
`partial` set on the result. A fresh model gets a shortage variable per need of the
actual gap (the 10% reserve of the wave target is not counted: a missing reserve place
must not outweigh a real shortage), and the rounds fix in turn the headcount, then
role, then skill shortage in person-seconds; the penalty, count and staff ID stages
follow with the shortages fixed. A group that covers nothing gives INFEASIBLE (no plan). Without any
exclusive constraint selecting everyone satisfies the model, so INFEASIBLE from
CP-SAT is still MODEL_INVALID.

No database access, clock reads, or writes.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from time import monotonic as _monotonic

from ortools.sat.python import cp_model

from app.domain.constraints.penalties import SoftWeights, candidate_penalty, plan_penalty
from app.domain.constraints.soft_metrics import SoftMetrics, ranking_key
from app.domain.enums import SolverStatus, TargetType
from app.domain.staffing.wave_targets import (
    TargetCredit,
    covers,
    elementary_slices,
    fill_targets_by_slice,
    wave_target,
)
from app.domain.workflow.case_status import GapFiller, IntervalGap

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
    # The roster shift the person is on now (a transfer). At most one candidate per
    # source shift can be in the group. None for everyone from a pool
    source_shift_id: int | None = None

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
    partial: the first wave came from the max-coverage stages: no group could
        cover every target.
    """

    ranked_staff_ids: tuple[int, ...]
    first_wave: Mapping[int, tuple[TargetCredit, ...]]
    objective_score: Fraction | None
    status: SolverStatus
    partial: bool = False


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
    partial: bool = False


@dataclass(frozen=True)
class _Need:
    """sum(x of holders) >= target for one target of one time piece.

    holders: indices into the candidates in staff ID order. seconds: the length of
    the piece, the weight of a shortage (1 for the legacy whole-shift slice).
    """

    kind: TargetType
    key: int | None
    holders: tuple[int, ...]
    target: int
    seconds: int


def solve(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    candidates: Sequence[SolverCandidate],
    weights: SoftWeights,
    time_limit_seconds: float,
    intervals: Sequence[IntervalGap] | None = None,
) -> SolverResult:
    """Choose the first wave and rank every candidate.

    intervals: the short time slices of the gap; None is the legacy single
    whole-shift slice described by the three summary arguments.
    """
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
        intervals=intervals,
    )
    if selection.group is None:
        return SolverResult((), {}, None, selection.status)
    group_fillers = [candidate.filler for candidate in sorted(selection.group, key=order)]
    first_wave = fill_targets_by_slice(
        slices=None if intervals is None else elementary_slices(intervals, group_fillers),
        candidates=group_fillers,
        headcount_gap=headcount_gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
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
        partial=selection.partial,
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


def _needs(
    people: Sequence[SolverCandidate],
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    intervals: Sequence[IntervalGap] | None,
    reserve: bool = True,
) -> list[_Need]:
    """The needs, merged: one per (kind, key, holders, target), seconds summed.

    Order: per piece, headcount, then roles, then skills, in the order of the gap
    dicts. A target nobody can reach is lowered to the number of holders.
    reserve=True asks for the wave target (the gap plus the 10% reserve); False asks
    for the actual gap only, which is what the partial plan measures (R4-Q39).
    """
    pieces: list[tuple[int, Mapping[int, int], Mapping[int, int], tuple[int, ...], int]]
    if intervals is None:
        pieces = [(headcount_gap, role_gaps, skill_gaps, tuple(range(len(people))), 1)]
    else:
        pieces = [
            (
                piece.headcount_gap,
                piece.role_gaps,
                piece.skill_gaps,
                tuple(
                    index
                    for index, candidate in enumerate(people)
                    if covers(candidate.filler, piece.start_at, piece.end_at)
                ),
                piece.seconds,
            )
            for piece in elementary_slices(intervals, [c.filler for c in people])
        ]
    merged: dict[tuple[TargetType, int | None, tuple[int, ...], int], int] = {}

    def add(
        kind: TargetType, key: int | None, holders: tuple[int, ...], gap: int, seconds: int
    ) -> None:
        target = min(wave_target(gap) if reserve else gap, len(holders))
        if target > 0:
            slot = (kind, key, holders, target)
            merged[slot] = merged.get(slot, 0) + seconds

    for head, roles, skills, covering, seconds in pieces:
        add(TargetType.HEADCOUNT, None, covering, head, seconds)
        for role_id, gap in roles.items():
            holders = tuple(i for i in covering if people[i].filler.role_id == role_id)
            add(TargetType.ROLE, role_id, holders, gap, seconds)
        for skill_id, gap in skills.items():
            holders = tuple(i for i in covering if skill_id in people[i].filler.skill_ids)
            add(TargetType.SKILL, skill_id, holders, gap, seconds)
    return [
        _Need(kind, key, holders, target, seconds)
        for (kind, key, holders, target), seconds in merged.items()
    ]


def _cheapest_covering_group(
    candidates: Sequence[SolverCandidate],
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    weights: SoftWeights,
    time_limit_seconds: float,
    intervals: Sequence[IntervalGap] | None = None,
) -> _Selection:
    deadline = _monotonic() + time_limit_seconds
    people = sorted(candidates, key=lambda candidate: candidate.filler.staff_id)

    def needs_of(*, reserve: bool) -> list[_Need]:
        return _needs(
            people,
            headcount_gap=headcount_gap,
            role_gaps=role_gaps,
            skill_gaps=skill_gaps,
            intervals=intervals,
            reserve=reserve,
        )

    needs = needs_of(reserve=True)
    # The partial plan counts what is actually missing: an unfilled reserve place must
    # not outweigh a real shortage (R4-Q39)
    gap_needs = needs_of(reserve=False)
    # Candidates on the same source shift: at most one of them
    by_shift: dict[int, list[int]] = {}
    for index, candidate in enumerate(people):
        if candidate.source_shift_id is not None:
            by_shift.setdefault(candidate.source_shift_id, []).append(index)
    exclusive = [group for _, group in sorted(by_shift.items()) if len(group) >= 2]
    costs = _scaled_costs([candidate_penalty(candidate.metrics, weights) for candidate in people])

    def new_model(
        wanted: Sequence[_Need], *, with_shortages: bool
    ) -> tuple[cp_model.CpModel, list[cp_model.IntVar], list[cp_model.IntVar]]:
        """The model, its x, and a shortage variable per need when asked."""
        built = cp_model.CpModel()
        xs = [built.new_bool_var(f"x{candidate.filler.staff_id}") for candidate in people]
        shortages: list[cp_model.IntVar] = []
        for need in wanted:
            reached = sum(xs[index] for index in need.holders)
            if with_shortages:
                shortage = built.new_int_var(0, need.target, f"s{len(shortages)}")
                shortages.append(shortage)
                built.add(reached + shortage >= need.target)
            else:
                built.add(reached >= need.target)
        for group in exclusive:
            built.add(sum(xs[index] for index in group) <= 1)
        return built, xs, shortages

    model, variables, _ = new_model(needs, with_shortages=False)
    cost_sum = cp_model.LinearExpr.weighted_sum(variables, costs)
    count_sum = cp_model.LinearExpr.sum(variables)
    # Checked with the stage 1 objective set: the scaled costs are the large numbers
    model.minimize(cost_sum)
    if model.validate():
        return _Selection(None, SolverStatus.MODEL_INVALID)

    # The last usable x, kept as a plain tuple apart from the solver
    kept: tuple[int, ...] = ()
    rounds = 0
    first_round_infeasible = False

    def group_of(values: tuple[int, ...]) -> tuple[SolverCandidate, ...]:
        return tuple(c for c, value in zip(people, values, strict=True) if value == 1)

    def run(objective: cp_model.LinearExprT, *, maximize: bool = False) -> _Selection | None:
        """One round: a selection means stop with it, None means go on."""
        nonlocal kept, rounds, first_round_infeasible
        rounds += 1
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
        # INFEASIBLE cannot happen when the model is right: the kept plan satisfies it.
        # Only an exclusive model may be infeasible in the very first round
        first_round_infeasible = rounds == 1 and outcome.status is SolverStatus.INFEASIBLE
        return _Selection(None, SolverStatus.MODEL_INVALID)

    def stages(cost_expr: cp_model.LinearExprT, count_expr: cp_model.LinearExprT) -> _Selection:
        # Stage 1: the lowest penalty. The value to fix comes from the integer costs
        stop = run(cost_expr)
        if stop is not None:
            return stop
        model.add(cost_expr == sum(cost * value for cost, value in zip(costs, kept, strict=True)))

        # Stage 2: the fewest people at that penalty
        stop = run(count_expr)
        if stop is not None:
            return stop
        size = sum(kept)
        model.add(count_expr == size)

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

    def shortage_of(need: _Need) -> int:
        return max(0, need.target - sum(kept[index] for index in need.holders))

    def partial_plan() -> _Selection:
        """No group covers every target: cover as much as possible (R4-Q37/R4-Q39).

        A fresh model where a need of the actual gap (no reserve) may fall short by a
        variable. Headcount, then role, then skill shortage in person-seconds, each fixed
        before the next; the ordinary stages then choose among the groups that are equally covered.
        """
        nonlocal model, variables, kept
        kept = ()
        model, variables, shortages = new_model(gap_needs, with_shortages=True)
        cost_expr = cp_model.LinearExpr.weighted_sum(variables, costs)
        count_expr = cp_model.LinearExpr.sum(variables)
        model.minimize(cost_expr)
        if model.validate():
            return _Selection(None, SolverStatus.MODEL_INVALID, partial=True)
        shortage_of_need = dict(zip(range(len(gap_needs)), shortages, strict=True))
        for kind in (TargetType.HEADCOUNT, TargetType.ROLE, TargetType.SKILL):
            of_kind = [index for index, need in enumerate(gap_needs) if need.kind is kind]
            if not of_kind:
                continue
            total = cp_model.LinearExpr.weighted_sum(
                [shortage_of_need[index] for index in of_kind],
                [gap_needs[index].seconds for index in of_kind],
            )
            stop = run(total)
            if stop is not None:
                return replace(stop, partial=True)
            model.add(
                total
                == sum(
                    gap_needs[index].seconds * shortage_of(gap_needs[index]) for index in of_kind
                )
            )
        if all(shortage_of(need) == need.target for need in gap_needs):
            # The best group covers nothing: there is no plan to offer
            return _Selection(None, SolverStatus.INFEASIBLE, partial=True)
        return replace(stages(cost_expr, count_expr), partial=True)

    selection = stages(cost_sum, count_sum)
    if first_round_infeasible and exclusive:
        return partial_plan()
    return selection
