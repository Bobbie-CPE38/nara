"""plan_penalty with the seeded weights (round 1 contract, section 8.3)."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from app.domain.constraints.penalties import (
    SoftWeights,
    candidate_penalty,
    candidate_penalty_terms,
    plan_penalty,
)
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource

SAME, FLOAT, CROSS = (
    CandidateSource.SAME_WARD,
    CandidateSource.FLOAT_POOL,
    CandidateSource.CROSS_WARD,
)

WEIGHTS = SoftWeights(
    candidate_count=Fraction(1000),
    consecutive_shift=Fraction(5),
    workload_imbalance=Fraction(1),
    projected_overtime=Fraction(2),
    roster_change=Fraction(300),
    candidate_source=Fraction(200),
    source_order=(SAME, FLOAT, CROSS),
)


def metrics(
    staff_id: int = 1,
    *,
    hours: int = 0,
    run: int = 1,
    overtime: int = 0,
    source: CandidateSource = SAME,
) -> SoftMetrics:
    return SoftMetrics(
        staff_id=staff_id,
        source=source,
        hours_this_week=Fraction(hours),
        projected_consecutive_shifts=run,
        overtime_hours=Fraction(overtime),
    )


def test_one_candidate() -> None:
    assert candidate_penalty(metrics(hours=8, run=2), WEIGHTS) == 1018


def test_a_group_is_the_sum_and_roster_changes_add_on_top() -> None:
    group = [metrics(1), metrics(2, hours=8, run=2)]

    assert plan_penalty(group, WEIGHTS) == 1005 + 1018
    assert plan_penalty(group, WEIGHTS, roster_changes=1) == 1005 + 1018 + 300


@pytest.mark.parametrize(
    ("cheaper", "dearer"),
    [
        ([metrics(hours=52, run=7, overtime=12)], [metrics(1), metrics(2)]),
        ([metrics(hours=52, run=7, overtime=12)], [metrics(source=FLOAT)]),
        ([metrics(source=FLOAT)], [metrics(source=CROSS)]),
        ([metrics(hours=24)], [metrics(hours=40)]),
        ([metrics(run=3)], [metrics(run=1, hours=16)]),
        ([metrics(overtime=4)], [metrics(run=3)]),
    ],
    ids=[
        "one_tired_over_two_fresh",
        "same_ward_over_float",
        "float_over_cross",
        "hours",
        "run",
        "ot",
    ],
)
def test_the_contract_pairs(cheaper: list[SoftMetrics], dearer: list[SoftMetrics]) -> None:
    assert plan_penalty(cheaper, WEIGHTS) < plan_penalty(dearer, WEIGHTS)


def test_a_negative_weight_raises() -> None:
    with pytest.raises(ValueError):
        replace(WEIGHTS, workload_imbalance=Fraction(-1))


def test_a_weight_must_be_a_fraction() -> None:
    with pytest.raises(TypeError):
        replace(WEIGHTS, candidate_count=Decimal(1000))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(WEIGHTS, candidate_count=1000)  # type: ignore[arg-type]


def test_a_repeated_source_raises() -> None:
    with pytest.raises(ValueError):
        replace(WEIGHTS, source_order=(SAME, SAME))


FRACTIONAL = SoftWeights(
    candidate_count=Fraction(1000),
    consecutive_shift=Fraction(3, 10),
    workload_imbalance=Fraction(1, 7),
    projected_overtime=Fraction(2),
    roster_change=Fraction(300),
    candidate_source=Fraction(200),
    source_order=(SAME, FLOAT, CROSS),
)


@pytest.mark.parametrize("weights", [WEIGHTS, FRACTIONAL], ids=["whole", "fractional"])
@pytest.mark.parametrize(
    "item",
    [
        metrics(),
        metrics(hours=8, run=2, source=FLOAT),
        SoftMetrics(
            staff_id=1,
            source=CROSS,
            hours_this_week=Fraction(22, 3),
            projected_consecutive_shifts=4,
            overtime_hours=Fraction(1, 3),
        ),
    ],
    ids=["fresh", "float_pool", "seven_hours_twenty_minutes"],
)
def test_the_terms_sum_to_the_candidate_penalty(item: SoftMetrics, weights: SoftWeights) -> None:
    terms = candidate_penalty_terms(item, weights)

    assert sum((term.points for term in terms), Fraction(0)) == candidate_penalty(item, weights)


def test_the_terms_come_in_a_fixed_order() -> None:
    names = [term.name for term in candidate_penalty_terms(metrics(), WEIGHTS)]

    assert names == [
        "candidate_count",
        "consecutive_shift",
        "workload_imbalance",
        "projected_overtime",
        "candidate_source",
    ]


@pytest.mark.parametrize("source", [SAME, FLOAT, CROSS])
def test_count_is_one_and_source_is_its_position(source: CandidateSource) -> None:
    terms = {term.name: term for term in candidate_penalty_terms(metrics(source=source), WEIGHTS)}

    assert terms["candidate_count"].value == 1
    assert terms["candidate_source"].value == WEIGHTS.source_order.index(source)
