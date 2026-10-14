"""Exact integer scaling of the costs and the tie-breaks that depend on it (contract 4.7)."""

from fractions import Fraction

import pytest

from app.domain.constraints.penalties import SoftWeights, plan_penalty
from app.domain.enums import SolverStatus
from app.optimization import solver
from app.optimization.solver import (
    SolverCandidate,
    SolverScalingOverflowError,
    _scaled_costs,
    solve,
)
from tests.unit.optimization.build_solver_baseline import SEED, hand_made, person, soft_weights
from tests.unit.optimization.solver_baseline import LIMIT

ONLY_HOURS = soft_weights(0, 0, 1, 0, 0)
FRACTIONS = soft_weights(0, 0, Fraction(1, 3), Fraction(1, 7), 0)


def only_skill(
    candidates: list[SolverCandidate], weights: SoftWeights, skill: int = 1, gap: int = 1
) -> solver.SolverResult:
    return solve(
        headcount_gap=0,
        role_gaps={},
        skill_gaps={skill: gap},
        candidates=candidates,
        weights=weights,
        time_limit_seconds=LIMIT,
    )


@pytest.mark.parametrize(
    ("costs", "scaled"),
    [
        ([Fraction(5, 4), Fraction(13, 10)], [25, 26]),
        ([Fraction(1, 3), Fraction(1, 7)], [7, 3]),
        ([Fraction(1000), Fraction(2000)], [1, 2]),
        ([Fraction(0), Fraction(0), Fraction(0)], [0, 0, 0]),
    ],
)
def test_the_costs_scale_to_the_smallest_whole_numbers(
    costs: list[Fraction], scaled: list[int]
) -> None:
    assert _scaled_costs(costs) == scaled


def test_costs_too_large_to_scale_raise_instead_of_rounding() -> None:
    primes = (999983, 999979, 999961, 999959)
    candidates = [person(index, 1, hours=Fraction(1, p)) for index, p in enumerate(primes, 1)]

    with pytest.raises(SolverScalingOverflowError):
        only_skill(candidates, ONLY_HOURS)


def test_the_largest_accepted_costs_are_solved_exactly() -> None:
    candidates = [
        person(1, 1, hours=2**57 + 3),
        person(2, 1, hours=2**57 + 1),
        person(3, 1, hours=2**57),
    ]

    result = only_skill(candidates, ONLY_HOURS)

    assert result.status is SolverStatus.OPTIMAL
    assert set(result.first_wave) == {2, 3}
    assert solver._MAX_SCALED_TOTAL == 2**60


def test_the_score_is_the_exact_plan_penalty_with_fractional_weights() -> None:
    candidates = [
        person(1, 1, hours=Fraction(21, 2), overtime=Fraction(7, 4)),
        person(2, 1, hours=10, overtime=Fraction(1, 3)),
        person(3, 1, hours=Fraction(43, 4), overtime=Fraction(5, 6)),
        person(4, 1, hours=Fraction(7, 3)),
    ]

    result = only_skill(candidates, FRACTIONS)

    by_id = {candidate.filler.staff_id: candidate for candidate in candidates}
    wave = [by_id[staff_id].metrics for staff_id in result.first_wave]
    assert result.status is SolverStatus.OPTIMAL
    assert result.objective_score == plan_penalty(wave, FRACTIONS)
    assert result.objective_score is not None
    assert result.objective_score.denominator != 1


def test_close_but_unequal_fractional_costs_pick_the_cheaper_group() -> None:
    # Two of four are needed. 5 and 6 are the cheapest by 1/1000 hours each
    candidates = [
        person(1, 1, hours=10 + Fraction(3, 1000)),
        person(2, 1, hours=10 + Fraction(2, 1000)),
        person(5, 1, hours=10),
        person(6, 1, hours=10 + Fraction(1, 1000)),
    ]

    result = only_skill(candidates, ONLY_HOURS)

    assert set(result.first_wave) == {5, 6}


def test_equal_costs_pick_the_group_with_fewer_people() -> None:
    # Every cost is 0, so {3, 4} and the four of them cost the same
    x, y = 1, 2
    candidates = [person(1, x), person(2, y), person(3, x, y), person(4, x, y)]

    result = solve(
        headcount_gap=0,
        role_gaps={},
        skill_gaps={x: 1, y: 1},
        candidates=candidates,
        weights=ONLY_HOURS,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.OPTIMAL
    assert set(result.first_wave) == {3, 4}
    assert result.objective_score == 0


def test_equal_cost_and_size_pick_the_lower_ids_even_with_the_same_id_sum() -> None:
    """[200, 201, 204] and [200, 202, 203] cost the same and sum to 605."""
    made, wave = next(item for item in hand_made() if item[0].name == "tie/equal_id_sum")
    assert wave == [200, 201, 204]

    result = solve(
        headcount_gap=made.headcount_gap,
        role_gaps=made.role_gaps,
        skill_gaps=made.skill_gaps,
        candidates=made.candidates,
        weights=SEED,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.OPTIMAL
    assert sorted(result.first_wave) == [200, 201, 204]
