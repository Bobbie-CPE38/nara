"""The round 1 search, kept as a comparator for tests only (round 2 contract, R2-Q6).

Copied from solver.py at staging 57fe961 when OR-Tools replaced it. No file under
app/ may import this module.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from fractions import Fraction

from app.domain.constraints.penalties import SoftWeights, candidate_penalty
from app.domain.staffing.wave_targets import wave_target
from app.optimization.solver import SolverCandidate

# (role target or None, short skills) of a candidate: what they count toward
_Kind = tuple[int | None, frozenset[int]]


def cheapest_covering_group(
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
    prices = [costs[candidate.filler.staff_id] for candidate in ordered]
    # spent[i] = cost of the first i of `ordered`. The list is in cost order, so
    # spent[i + n] - spent[i] is the least that n more people from i on can cost
    spent = [Fraction(0)]
    for price in prices:
        spent.append(spent[-1] + price)

    def kind(candidate: SolverCandidate) -> _Kind:
        filler = candidate.filler
        return (
            filler.role_id if filler.role_id in roles else None,
            frozenset(skill_id for skill_id in filler.skill_ids if skill_id in skills),
        )

    kinds = [kind(candidate) for candidate in ordered]

    def missing(chosen: Sequence[SolverCandidate]) -> int:
        """The largest open target: the group needs at least this many more people."""
        role_count = Counter(candidate.filler.role_id for candidate in chosen)
        skill_count = Counter(
            skill_id for candidate in chosen for skill_id in candidate.filler.skill_ids
        )
        return max(
            0,
            headcount - len(chosen),
            *(count - role_count[role_id] for role_id, count in roles.items()),
            *(count - skill_count[skill_id] for skill_id, count in skills.items()),
        )

    # (penalty, people, staff IDs) of the best group so far: smaller is better
    best: tuple[Fraction, int, tuple[int, ...]] | None = None
    best_group: tuple[SolverCandidate, ...] = ()

    def search(
        index: int, chosen: list[SolverCandidate], cost: Fraction, skipped: frozenset[_Kind]
    ) -> None:
        nonlocal best, best_group
        needed = missing(chosen)
        if needed == 0:
            score = (
                cost,
                len(chosen),
                tuple(sorted(candidate.filler.staff_id for candidate in chosen)),
            )
            if best is None or score < best:
                best, best_group = score, tuple(chosen)
            # One more person never makes a covering group cheaper
            return
        if index + needed > len(ordered):
            return
        if best is not None:
            floor = cost + spent[index + needed] - spent[index]
            if floor > best[0] or (floor == best[0] and len(chosen) + needed > best[1]):
                return
        if kinds[index] not in skipped:
            chosen.append(ordered[index])
            search(index + 1, chosen, cost + prices[index], skipped)
            chosen.pop()
            # An earlier candidate of a kind is never worse than a later one
            skipped = skipped | {kinds[index]}
        search(index + 1, chosen, cost, skipped)

    search(0, [], Fraction(0), frozenset())
    return best_group
