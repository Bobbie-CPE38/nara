"""The OR-Tools search against the round 1 search on fresh random problems (R2-Q6)."""

import random
from fractions import Fraction

import pytest

from app.domain.constraints.penalties import SoftWeights
from app.domain.enums import SolverStatus
from app.optimization.solver import SolverCandidate, _cheapest_covering_group
from tests.unit.optimization.build_solver_baseline import CROSS, FLOAT, SAME, person, soft_weights
from tests.unit.optimization.round1_search import cheapest_covering_group
from tests.unit.optimization.solver_baseline import LIMIT

# The baseline uses the seeds 101 to 107
SEEDS = range(5000, 5100)
WEIGHTS = (
    soft_weights(),
    soft_weights(1000, Fraction(7, 2), Fraction(1, 3), Fraction(5, 4), 200),
    soft_weights(0, 0, 1, 0, 0),
    soft_weights(0, 0, 0, 0, 0),
    soft_weights(candidate_count=0),
)


def random_candidates(rng: random.Random) -> list[SolverCandidate]:
    ids = rng.sample(range(1, 200), rng.randint(1, 30))
    return [
        person(
            staff_id,
            *(skill for skill in (1, 2, 3, 4) if rng.random() < 0.35),
            role=rng.choice([1, 2]),
            hours=Fraction(rng.randint(0, 30), rng.choice([1, 2, 3])),
            run=rng.randint(1, 4),
            overtime=Fraction(rng.randint(0, 6), rng.choice([1, 4])),
            source=rng.choice([SAME, FLOAT, CROSS]),
        )
        for staff_id in ids
    ]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_group_equals_the_round_1_group(seed: int) -> None:
    rng = random.Random(seed)
    candidates = random_candidates(rng)
    weights: SoftWeights = rng.choice(WEIGHTS)
    headcount = rng.randint(0, 5)
    roles = {role: rng.randint(1, 5) for role in (1, 2) if rng.random() < 0.5}
    skills = {skill: rng.randint(1, 5) for skill in (1, 2, 3, 4) if rng.random() < 0.4}

    expected = cheapest_covering_group(
        candidates,
        headcount_gap=headcount,
        role_gaps=roles,
        skill_gaps=skills,
        weights=weights,
    )
    selection = _cheapest_covering_group(
        candidates,
        headcount_gap=headcount,
        role_gaps=roles,
        skill_gaps=skills,
        weights=weights,
        time_limit_seconds=LIMIT,
    )

    assert selection.status is SolverStatus.OPTIMAL
    assert selection.group is not None
    assert sorted(c.filler.staff_id for c in selection.group) == sorted(
        c.filler.staff_id for c in expected
    )
