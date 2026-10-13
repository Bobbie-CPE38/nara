"""Stage 3 decides the staff IDs in blocks: more than one block gives the round 1 group too."""

import random
from collections.abc import Sequence
from fractions import Fraction
from typing import Any

import pytest
from ortools.sat.python import cp_model

from app.domain.enums import SolverStatus
from app.optimization import solver
from app.optimization.solver import _BLOCK, _cheapest_covering_group, _Round
from tests.unit.optimization.build_solver_baseline import CROSS, FLOAT, SAME, person, soft_weights
from tests.unit.optimization.round1_search import cheapest_covering_group
from tests.unit.optimization.solver_baseline import LIMIT

# Ties everywhere: whole hours in two steps, one run length, no overtime
TIE_HEAVY = soft_weights(1000, 0, 1, 0, 0)
SEEDS = range(7000, 7060)


def problem(seed: int) -> tuple[list[Any], int, dict[int, int], dict[int, int], Any]:
    rng = random.Random(seed)
    heavy = seed % 2 == 0
    candidates = [
        person(
            staff_id,
            *(skill for skill in (1, 2, 3, 4) if rng.random() < 0.3),
            role=rng.choice([1, 2]),
            hours=Fraction(8 * rng.randint(0, 1)) if heavy else Fraction(rng.randint(0, 40), 2),
            run=1 if heavy else rng.randint(1, 3),
            source=SAME if heavy else rng.choice([SAME, FLOAT, CROSS]),
        )
        for staff_id in rng.sample(range(1, 400), rng.randint(_BLOCK + 1, 150))
    ]
    headcount = rng.randint(0, 2)
    roles = {role: rng.randint(1, 2) for role in (1, 2) if rng.random() < 0.5}
    skills = {skill: rng.randint(1, 2) for skill in (1, 2, 3, 4) if rng.random() < 0.4}
    return candidates, headcount, roles, skills, TIE_HEAVY if heavy else soft_weights()


@pytest.mark.parametrize("seed", SEEDS)
def test_more_than_one_block_gives_the_round_1_group(seed: int) -> None:
    candidates, headcount, roles, skills, weights = problem(seed)
    arguments = {"headcount_gap": headcount, "role_gaps": roles, "skill_gaps": skills}

    expected = cheapest_covering_group(candidates, weights=weights, **arguments)
    selection = _cheapest_covering_group(
        candidates, weights=weights, time_limit_seconds=LIMIT, **arguments
    )

    assert selection.status is SolverStatus.OPTIMAL
    assert selection.group is not None
    assert sorted(c.filler.staff_id for c in selection.group) == sorted(
        c.filler.staff_id for c in expected
    )


def test_a_pool_of_300_needs_about_ten_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    real = solver._run_cp_sat
    rounds: list[int] = []

    def counted(model: cp_model.CpModel, variables: Sequence[Any], seconds: float) -> _Round:
        rounds.append(1)
        return real(model, variables, seconds)

    monkeypatch.setattr(solver, "_run_cp_sat", counted)
    candidates = [person(staff_id, *([1] if staff_id % 3 == 0 else [])) for staff_id in range(300)]

    selection = _cheapest_covering_group(
        candidates,
        headcount_gap=4,
        role_gaps={1: 4},
        skill_gaps={1: 2},
        weights=soft_weights(),
        time_limit_seconds=LIMIT,
    )

    assert selection.status is SolverStatus.OPTIMAL
    # Stage 1, stage 2 and at most one round per block of 40 candidates
    assert len(rounds) <= 2 + -(-300 // _BLOCK)
