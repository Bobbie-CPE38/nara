"""Round 1 Solver: choose the first wave and rank the plan (round 1 contract, section 8.3).

Input: the gap of a case and the candidates that passed the Hard Rules, each
with their Soft Constraint values. Output: who is in the first wave, which
targets each of them fills, and the rank of every candidate.

  1. Wave targets: ceil(gap * 11 / 10) for headcount, each short role and each
     short skill. A target the candidates cannot reach is lowered to the number
     of candidates that match it, so a small pool still gives the widest wave.
  2. First wave: the group that covers every target with the lowest
     plan_penalty. Ties: fewer people, then the lower staff IDs.
  3. fill_targets() inside that group says which targets each member fills.
  4. rank: the first wave in ranking_key order, then everyone else in
     ranking_key order. plan_penalty decides who is in the group. ranking_key
     only orders people, so the two can disagree about who looks better.

The search tries groups exhaustively and stops a branch once it cannot beat the
best group. That is enough for one ward (tens of candidates, targets of a few
people). Round 2 replaces it with OR-Tools.

No database access, clock reads, or writes.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from app.domain.constraints.penalties import SoftWeights, candidate_penalty, plan_penalty
from app.domain.constraints.soft_metrics import SoftMetrics, ranking_key
from app.domain.staffing.wave_targets import TargetCredit, fill_targets, wave_target
from app.domain.workflow.case_status import GapFiller, gap_closed


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

    ranked_staff_ids: every candidate, rank 1 first.
    first_wave: staff ID -> the targets that person fills, in the order chosen.
    objective_score: plan_penalty of the first wave. None without candidates.
    """

    ranked_staff_ids: tuple[int, ...]
    first_wave: Mapping[int, tuple[TargetCredit, ...]]
    objective_score: Fraction | None


def solve(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    candidates: Sequence[SolverCandidate],
    weights: SoftWeights,
) -> SolverResult:
    """Choose the first wave and rank every candidate."""
    if not candidates:
        return SolverResult(ranked_staff_ids=(), first_wave={}, objective_score=None)
    by_id = {candidate.filler.staff_id: candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("A candidate is listed twice")

    def order(candidate: SolverCandidate) -> tuple[int, Fraction, int, Fraction, int]:
        return ranking_key(candidate.metrics, weights.source_order)

    group = _cheapest_covering_group(
        candidates,
        headcount_gap=headcount_gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        weights=weights,
    )
    first_wave = fill_targets(
        headcount_gap=headcount_gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        candidates=[candidate.filler for candidate in sorted(group, key=order)],
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
    )


def _cheapest_covering_group(
    candidates: Sequence[SolverCandidate],
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    weights: SoftWeights,
) -> tuple[SolverCandidate, ...]:
    # A target nobody can reach is lowered to what the candidates can give
    role_holders = Counter(candidate.filler.role_id for candidate in candidates)
    skill_holders = Counter(
        skill_id for candidate in candidates for skill_id in candidate.filler.skill_ids
    )
    headcount = min(wave_target(headcount_gap), len(candidates))
    roles = {
        role_id: min(wave_target(gap), role_holders[role_id]) for role_id, gap in role_gaps.items()
    }
    skills = {
        skill_id: min(wave_target(gap), skill_holders[skill_id])
        for skill_id, gap in skill_gaps.items()
    }

    costs = {
        candidate.filler.staff_id: candidate_penalty(candidate.metrics, weights)
        for candidate in candidates
    }
    # Cheap people first, so a good group is found early and prunes the rest
    ordered = sorted(
        candidates,
        key=lambda candidate: (costs[candidate.filler.staff_id], candidate.filler.staff_id),
    )
    # (penalty, people, staff IDs) of the best group so far: smaller is better
    best: tuple[Fraction, int, tuple[int, ...]] | None = None
    best_group: tuple[SolverCandidate, ...] = ()

    def search(index: int, chosen: list[SolverCandidate], cost: Fraction) -> None:
        nonlocal best, best_group
        covered = gap_closed(
            headcount_gap=headcount,
            role_gaps=roles,
            skill_gaps=skills,
            fillers=(candidate.filler for candidate in chosen),
        )
        if covered:
            score = (
                cost,
                len(chosen),
                tuple(sorted(candidate.filler.staff_id for candidate in chosen)),
            )
            if best is None or score < best:
                best, best_group = score, tuple(chosen)
            # One more person never makes a covering group cheaper
            return
        if index == len(ordered):
            return
        if best is not None and (cost > best[0] or (cost == best[0] and len(chosen) >= best[1])):
            return
        candidate = ordered[index]
        chosen.append(candidate)
        search(index + 1, chosen, cost + costs[candidate.filler.staff_id])
        chosen.pop()
        search(index + 1, chosen, cost)

    search(0, [], Fraction(0))
    return best_group
