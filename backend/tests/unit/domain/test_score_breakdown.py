"""Score breakdown codec for the plan snapshot (round 3 contract, section 6.15)."""

from dataclasses import replace
from fractions import Fraction
from typing import Any

import pytest

from app.domain.constraints.penalties import SoftWeights, candidate_penalty
from app.domain.constraints.score_breakdown import (
    ScoreMismatchError,
    display_number,
    exact_fields,
    fraction_text,
    parse_fraction,
    score_from_snapshot,
    weights_from_snapshot,
    weights_snapshot,
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

FRACTIONAL = replace(
    WEIGHTS,
    consecutive_shift=Fraction(3, 10),
    workload_imbalance=Fraction(1, 7),
    projected_overtime=Fraction(1, 4),
)

FRESH = SoftMetrics(
    staff_id=201,
    source=SAME,
    hours_this_week=Fraction(0),
    projected_consecutive_shifts=1,
    overtime_hours=Fraction(0),
)

TIRED = SoftMetrics(
    staff_id=202,
    source=FLOAT,
    hours_this_week=Fraction(22, 3),
    projected_consecutive_shifts=3,
    overtime_hours=Fraction(1, 3),
)


def entry(metrics: SoftMetrics, weights: SoftWeights) -> dict[str, Any]:
    """A snapshot candidate as create_plan() writes it, float fields included."""
    return {
        "staff_id": metrics.staff_id,
        "source": metrics.source.value,
        "hours_this_week": float(metrics.hours_this_week),
        "projected_consecutive_shifts": metrics.projected_consecutive_shifts,
        "overtime_hours": float(metrics.overtime_hours),
        "penalty": float(candidate_penalty(metrics, weights)),
        "first_wave": True,
        **exact_fields(metrics, weights),
    }


def test_fraction_text_is_always_n_over_d() -> None:
    assert fraction_text(Fraction(5)) == "5/1"
    assert fraction_text(Fraction(1, 3)) == "1/3"
    assert parse_fraction(fraction_text(Fraction(22, 3))) == Fraction(22, 3)
    assert parse_fraction(fraction_text(Fraction(5))) == 5


@pytest.mark.parametrize("bad", [1.5, 5, None])
def test_parse_fraction_only_takes_text(bad: object) -> None:
    with pytest.raises(TypeError):
        parse_fraction(bad)


@pytest.mark.parametrize("weights", [WEIGHTS, FRACTIONAL], ids=["whole", "fractional"])
def test_weights_round_trip(weights: SoftWeights) -> None:
    snapshot = weights_snapshot(weights)

    assert snapshot["candidate_count"] == "1000/1"
    assert snapshot["source_order"] == ["SAME_WARD", "FLOAT_POOL", "CROSS_WARD"]
    assert weights_from_snapshot(snapshot) == weights


def test_display_number() -> None:
    whole, part = display_number(Fraction(1005)), display_number(Fraction(1, 4))

    assert whole == 1005 and isinstance(whole, int)
    assert part == 0.25 and isinstance(part, float)


@pytest.mark.parametrize(
    "key",
    ["hours_this_week_exact", "overtime_hours_exact", "penalty_exact", "first_wave"],
)
def test_an_entry_missing_a_field_raises(key: str) -> None:
    item = entry(FRESH, WEIGHTS)
    del item[key]

    with pytest.raises(ScoreMismatchError):
        score_from_snapshot(WEIGHTS, item)


def test_an_exact_field_that_is_not_text_raises() -> None:
    item = entry(FRESH, WEIGHTS)
    item["penalty_exact"] = 1005.0

    with pytest.raises(ScoreMismatchError):
        score_from_snapshot(WEIGHTS, item)


def test_weights_missing_a_key_raise() -> None:
    raw = weights_snapshot(WEIGHTS)
    del raw["candidate_source"]

    with pytest.raises(ScoreMismatchError):
        weights_from_snapshot(raw)


def test_the_terms_sum_to_the_stored_penalty() -> None:
    score = score_from_snapshot(WEIGHTS, entry(FRESH, WEIGHTS))

    assert score.total == 1005
    assert [term.points for term in score.terms] == [1000, 5, 0, 0, 0]
    assert score.first_wave is True


def test_a_fractional_case_sums_exactly() -> None:
    score = score_from_snapshot(FRACTIONAL, entry(TIRED, FRACTIONAL))

    assert score.total == candidate_penalty(TIRED, FRACTIONAL)
    assert (
        score.total == Fraction(1000) + Fraction(9, 10) + Fraction(22, 21) + Fraction(1, 12) + 200
    )


def test_a_tampered_penalty_raises() -> None:
    item = entry(FRESH, WEIGHTS)
    item["penalty_exact"] = "1006/1"

    with pytest.raises(ScoreMismatchError):
        score_from_snapshot(WEIGHTS, item)


def test_the_float_fields_are_never_read() -> None:
    item = entry(TIRED, FRACTIONAL)
    expected = score_from_snapshot(FRACTIONAL, item)
    item.update(hours_this_week="garbage", overtime_hours=None, penalty=-1.0)

    assert score_from_snapshot(FRACTIONAL, item) == expected
