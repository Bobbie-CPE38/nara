"""Problems above the baseline size, with no round 1 search to compare to (R2-Q51)."""

import random
from fractions import Fraction

import pytest

from app.domain.constraints.penalties import plan_penalty
from app.domain.enums import SolverStatus
from app.domain.staffing.wave_targets import wave_target
from app.domain.workflow.case_status import gap_closed
from app.optimization.solver import SolverCandidate, solve
from tests.unit.optimization.build_solver_baseline import CROSS, FLOAT, SAME, SEED, person
from tests.unit.optimization.solver_baseline import LIMIT

ICU = 1


def random_problem(seed: int) -> tuple[list[SolverCandidate], int, dict[int, int], dict[int, int]]:
    rng = random.Random(seed)
    candidates = [
        person(
            staff_id,
            *(skill for skill in (1, 2, 3, 4) if rng.random() < 0.3),
            role=rng.choice([1, 2]),
            hours=Fraction(rng.randint(0, 60), rng.choice([1, 2])),
            run=rng.randint(1, 7),
            overtime=Fraction(rng.randint(0, 10), rng.choice([1, 4])),
            source=rng.choice([SAME, FLOAT, CROSS]),
        )
        for staff_id in rng.sample(range(1, 500), rng.randint(40, 80))
    ]
    headcount = rng.randint(8, 12)
    roles = {role: rng.randint(8, 12) for role in (1, 2) if rng.random() < 0.7}
    skills = {skill: rng.randint(8, 12) for skill in (1, 2, 3, 4) if rng.random() < 0.6}
    return candidates, headcount, roles, skills


@pytest.mark.parametrize("seed", range(9000, 9010))
def test_the_first_wave_closes_the_lowered_targets_and_scores_exactly(seed: int) -> None:
    candidates, headcount, roles, skills = random_problem(seed)

    result = solve(
        headcount_gap=headcount,
        role_gaps=roles,
        skill_gaps=skills,
        candidates=candidates,
        weights=SEED,
        time_limit_seconds=LIMIT,
    )

    fillers = [c.filler for c in candidates]
    wave = [c for c in candidates if c.filler.staff_id in result.first_wave]
    assert gap_closed(
        headcount_gap=min(wave_target(headcount), len(candidates)),
        role_gaps={
            role: min(wave_target(gap), sum(f.role_id == role for f in fillers))
            for role, gap in roles.items()
        },
        skill_gaps={
            skill: min(wave_target(gap), sum(skill in f.skill_ids for f in fillers))
            for skill, gap in skills.items()
        },
        fillers=(c.filler for c in wave),
    )
    assert result.objective_score == plan_penalty((c.metrics for c in wave), SEED)
    assert sorted(result.ranked_staff_ids) == sorted(c.filler.staff_id for c in candidates)


def test_the_strictly_cheapest_covering_set_wins_among_expensive_people() -> None:
    tired = {"hours": 40, "run": 6}
    expensive = [person(staff_id, ICU, **tired) for staff_id in range(1, 61)]
    cheap = [person(staff_id, *([ICU] if staff_id < 109 else [])) for staff_id in range(100, 111)]
    # 100 to 110 are 11 people and 9 of them hold ICU: exactly the lowered targets 11 and 9
    candidates = [*expensive, *cheap]
    random.Random(1).shuffle(candidates)

    result = solve(
        headcount_gap=10,
        role_gaps={1: 10},
        skill_gaps={ICU: 8},
        candidates=candidates,
        weights=SEED,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.OPTIMAL
    assert set(result.first_wave) == set(range(100, 111))


def test_equal_people_give_the_lowest_ids_that_cover_the_targets() -> None:
    # Odd IDs hold ICU. 11 people with at least 9 of them odd: the smallest ID tuple
    candidates = [person(staff_id, *([ICU] if staff_id % 2 else [])) for staff_id in range(1, 61)]
    random.Random(2).shuffle(candidates)

    result = solve(
        headcount_gap=10,
        role_gaps={1: 10},
        skill_gaps={ICU: 8},
        candidates=candidates,
        weights=SEED,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.OPTIMAL
    assert set(result.first_wave) == {1, 2, 3, 4, 5, 7, 9, 11, 13, 15, 17}
