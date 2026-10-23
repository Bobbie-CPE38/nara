"""The seeded weights follow the priorities of round 6 PR EV6 (docs/workflow.md 6.36.7).

Fewer candidates, then the source (same ward, Float Pool, cross-ward), then the week's
hours, then the consecutive shifts, then the projected overtime. Each priority must win
over the whole range of every priority after it for one person, within the Hard Rules of
the seed (52 hours a week, 7 consecutive shifts). Checked on candidate_penalty() with the
weights read from the seeded policy, as the Solver reads them.
"""

from fractions import Fraction

import pytest
from sqlalchemy.orm import Session

from app.domain.constraints.penalties import SoftWeights, candidate_penalty
from app.domain.constraints.soft_metrics import SoftMetrics, projected_overtime_hours
from app.domain.enums import CandidateSource
from app.services import optimization_service, policy_service

MAX_WEEK, MAX_CONSECUTIVE = Fraction(52), 7
# The overtime one person can bring: the hours above 40 a week, and a few already worked
MAX_OVERTIME = MAX_WEEK - 40 + 4


@pytest.fixture
def weights(seeded: Session) -> SoftWeights:
    return optimization_service._weights(policy_service.get_soft_constraint_policy(seeded))


def _person(
    *,
    source: CandidateSource = CandidateSource.SAME_WARD,
    hours: Fraction = Fraction(0),
    consecutive: int = 1,
    overtime: Fraction = Fraction(0),
) -> SoftMetrics:
    return SoftMetrics(
        staff_id=1,
        source=source,
        hours_this_week=hours,
        projected_consecutive_shifts=consecutive,
        overtime_hours=overtime,
    )


WORST = {"hours": MAX_WEEK, "consecutive": MAX_CONSECUTIVE, "overtime": MAX_OVERTIME}


def test_a_moved_assignment_costs_more_than_any_source_week_run_or_overtime(
    weights: SoftWeights,
) -> None:
    """Review of #145: roster_change sits above the source in 6.36.7."""
    farthest_and_tired = candidate_penalty(
        _person(source=CandidateSource.CROSS_WARD, **WORST), weights
    )
    closest_and_rested = candidate_penalty(_person(consecutive=0), weights)

    assert farthest_and_tired - closest_and_rested < weights.roster_change


def test_one_person_at_worst_costs_less_than_two_at_best(weights: SoftWeights) -> None:
    worst = candidate_penalty(_person(source=CandidateSource.CROSS_WARD, **WORST), weights)
    worst += weights.roster_change
    best = candidate_penalty(_person(consecutive=0), weights)

    assert worst < 2 * best


def test_the_same_ward_wins_over_any_week_consecutive_run_or_overtime(
    weights: SoftWeights,
) -> None:
    assert len(weights.source_order) == len(CandidateSource)
    for closer, farther in (
        (CandidateSource.SAME_WARD, CandidateSource.FLOAT_POOL),
        (CandidateSource.FLOAT_POOL, CandidateSource.CROSS_WARD),
    ):
        tired_but_close = candidate_penalty(_person(source=closer, **WORST), weights)
        rested_but_far = candidate_penalty(_person(source=farther, consecutive=0), weights)
        assert tired_but_close < rested_but_far


def test_one_hour_less_this_week_wins_over_any_consecutive_run_or_overtime(
    weights: SoftWeights,
) -> None:
    """Review of #145: with 20 and 20 an hour of the week and a consecutive shift traded."""
    lighter_week = candidate_penalty(
        _person(hours=Fraction(39), consecutive=MAX_CONSECUTIVE, overtime=MAX_OVERTIME), weights
    )
    heavier_week = candidate_penalty(_person(hours=Fraction(40), consecutive=1), weights)

    assert lighter_week < heavier_week


def test_one_consecutive_shift_less_wins_over_any_overtime(weights: SoftWeights) -> None:
    shorter_run = candidate_penalty(_person(consecutive=2, overtime=MAX_OVERTIME), weights)
    longer_run = candidate_penalty(_person(consecutive=3), weights)

    assert shorter_run < longer_run


def test_less_projected_overtime_wins_when_everything_else_is_equal(weights: SoftWeights) -> None:
    assert candidate_penalty(_person(overtime=Fraction(1)), weights) < candidate_penalty(
        _person(overtime=Fraction(2)), weights
    )


@pytest.mark.parametrize(
    ("worked", "week", "added", "expected"),
    [
        (Fraction(0), Fraction(24), Fraction(8), Fraction(0)),  # 32 hours: no overtime
        (Fraction(0), Fraction(36), Fraction(8), Fraction(4)),  # 44 hours: 4 over 40
        (Fraction(1, 3), Fraction(40), Fraction(8), Fraction(25, 3)),  # 20 minutes already
        (Fraction(2), Fraction(10), Fraction(0), Fraction(2)),  # moved, adds no hours
    ],
)
def test_projected_overtime_counts_the_week_with_the_shift(
    worked: Fraction, week: Fraction, added: Fraction, expected: Fraction
) -> None:
    assert (
        projected_overtime_hours(overtime_worked=worked, hours_this_week=week, added_hours=added)
        == expected
    )
