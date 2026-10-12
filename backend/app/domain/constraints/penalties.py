"""plan_penalty of the round 1 Solver (round 1 contract, section 8.3). Smaller is better.

    plan_penalty = candidate_count_weight    x people in the group
                 + consecutive_shift_weight  x sum of projected_consecutive_shifts
                 + workload_imbalance_weight x sum of hours_this_week
                 + projected_overtime_weight x sum of overtime_hours
                 + roster_change_weight      x existing assignments that move
                 + candidate_source_weight   x sum of source priorities

Every term except the roster changes is a sum over the people of the group, so
the penalty of a group is the sum of candidate_penalty() of its members. Round 1
only adds assignments: nothing moves, and that term is 0.

Exact Fraction arithmetic: equal penalties must compare equal, because a tie is
broken by staff ID. No database access, clock reads, or writes.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from app.domain.constraints.soft_metrics import SoftMetrics, source_priority
from app.domain.enums import CandidateSource

_WEIGHT_NAMES = (
    "candidate_count",
    "consecutive_shift",
    "workload_imbalance",
    "projected_overtime",
    "roster_change",
    "candidate_source",
)


@dataclass(frozen=True, kw_only=True)
class SoftWeights:
    """The SOFT_CONSTRAINT_POLICY values the Solver reads.

    A weight must not be negative: the Solver stops looking at a group as soon as
    it costs more than the best one, which is only right when adding a person
    never lowers the penalty.
    """

    candidate_count: Fraction
    consecutive_shift: Fraction
    workload_imbalance: Fraction
    projected_overtime: Fraction
    roster_change: Fraction
    candidate_source: Fraction
    source_order: tuple[CandidateSource, ...]

    def __post_init__(self) -> None:
        for name in _WEIGHT_NAMES:
            value = getattr(self, name)
            if not isinstance(value, Fraction):
                raise TypeError(f"{name} must be a Fraction")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if len(set(self.source_order)) != len(self.source_order):
            raise ValueError("source_order lists a source twice")


def candidate_penalty(metrics: SoftMetrics, weights: SoftWeights) -> Fraction:
    """What one person adds to the penalty of a group."""
    return (
        weights.candidate_count
        + weights.consecutive_shift * metrics.projected_consecutive_shifts
        + weights.workload_imbalance * metrics.hours_this_week
        + weights.projected_overtime * metrics.overtime_hours
        + weights.candidate_source * source_priority(metrics.source, weights.source_order)
    )


def plan_penalty(
    group: Iterable[SoftMetrics], weights: SoftWeights, *, roster_changes: int = 0
) -> Fraction:
    """Penalty of a group. roster_changes is always 0 in round 1."""
    return (
        sum((candidate_penalty(metrics, weights) for metrics in group), Fraction(0))
        + weights.roster_change * roster_changes
    )
