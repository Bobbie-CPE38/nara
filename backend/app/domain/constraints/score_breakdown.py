"""Exact numbers behind a candidate's rank (round 3 contract, section 6.15).

create_plan() stores the weights and the exact penalty inputs as "numerator/denominator"
text in CANDIDATE_PLANS.input_snapshot. The reader rebuilds the breakdown from that
snapshot alone with Fraction, so it still matches after the policy row is edited or the
float fields round. No database access, clock reads, or writes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from app.domain.constraints.penalties import (
    PenaltyTerm,
    SoftWeights,
    candidate_penalty,
    candidate_penalty_terms,
)
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource

_WEIGHT_KEYS = (
    "candidate_count",
    "consecutive_shift",
    "workload_imbalance",
    "projected_overtime",
    "roster_change",
    "candidate_source",
)


class ScoreMismatchError(RuntimeError):
    """The stored numbers do not add up. A bug, so nothing is rounded to make it fit."""


@dataclass(frozen=True)
class CandidateScore:
    total: Fraction
    terms: tuple[PenaltyTerm, ...]
    first_wave: bool


def fraction_text(value: Fraction) -> str:
    """Always "n/d", also for whole numbers ("1005/1")."""
    return f"{value.numerator}/{value.denominator}"


def parse_fraction(text: object) -> Fraction:
    """Read "n/d" text. Only a str is accepted: a float or int would hide a rounding."""
    if not isinstance(text, str):
        raise TypeError("an exact value must be a string")
    return Fraction(text)


def display_number(value: Fraction) -> int | float:
    """int when whole, else float. For display only, never for a calculation."""
    if value.denominator == 1:
        return value.numerator
    return float(value)


def weights_snapshot(weights: SoftWeights) -> dict[str, Any]:
    snapshot: dict[str, Any] = {key: fraction_text(getattr(weights, key)) for key in _WEIGHT_KEYS}
    snapshot["source_order"] = [source.value for source in weights.source_order]
    return snapshot


def weights_from_snapshot(raw: Mapping[str, Any]) -> SoftWeights:
    """Build SoftWeights from weights_snapshot(), so its validation runs again."""
    try:
        return SoftWeights(
            **{key: parse_fraction(raw[key]) for key in _WEIGHT_KEYS},
            source_order=tuple(CandidateSource(value) for value in raw["source_order"]),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ScoreMismatchError("the stored weights are incomplete") from error


def exact_fields(metrics: SoftMetrics, weights: SoftWeights) -> dict[str, str]:
    """The per-candidate *_exact snapshot keys."""
    return {
        "hours_this_week_exact": fraction_text(metrics.hours_this_week),
        "overtime_hours_exact": fraction_text(metrics.overtime_hours),
        "penalty_exact": fraction_text(candidate_penalty(metrics, weights)),
    }


def score_from_snapshot(weights: SoftWeights, entry: Mapping[str, Any]) -> CandidateScore:
    """Breakdown of one snapshot entry of a plan that has stored weights.

    Reads only the *_exact fields, never the float ones. An entry that lacks a field,
    holds a value that is not "n/d" text, or whose terms do not sum to penalty_exact
    raises ScoreMismatchError: a plan with weights is never treated as a legacy plan.
    """
    staff_id = entry.get("staff_id")
    try:
        metrics = SoftMetrics(
            staff_id=entry["staff_id"],
            source=CandidateSource(entry["source"]),
            hours_this_week=parse_fraction(entry["hours_this_week_exact"]),
            projected_consecutive_shifts=entry["projected_consecutive_shifts"],
            overtime_hours=parse_fraction(entry["overtime_hours_exact"]),
        )
        stored = parse_fraction(entry["penalty_exact"])
        first_wave = bool(entry["first_wave"])
        terms = candidate_penalty_terms(metrics, weights)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ScoreMismatchError(f"the snapshot entry of staff {staff_id} is incomplete") from error
    total = sum((term.points for term in terms), Fraction(0))
    if total != stored:
        raise ScoreMismatchError(f"the terms of staff {staff_id} do not sum to the penalty")
    return CandidateScore(total=total, terms=terms, first_wave=first_wave)
