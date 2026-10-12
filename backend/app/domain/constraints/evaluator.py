"""Run the Hard Rules for one candidate (round 1 contract, sections 7.3 and 7.4).

The Solver, wave selection and Safety all call evaluate(), so the same data
gives the same answer at all three. No database access, clock reads, or writes:
the caller loads the rows, builds the context and owns persistence and audit.

A broken rule is a code in the result, not an exception, because Safety records
every rule that failed and not only the first.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import (
    CandidateContext,
    HardRulePolicy,
    daily_hours,
    projected_consecutive_shifts,
    weekly_hours,
)
from app.domain.constraints.hard_rules import HARD_RULES


@dataclass(frozen=True)
class HardRuleResult:
    """Outcome for one candidate, in the shape SAFETY_VALIDATION stores.

    checked_rules holds the rules that ran; a rule its policy flag switches off
    is absent. failed_rules is empty when the candidate passed. Both follow the
    order of HardRuleCode. details carries the totals and limits of the hour and
    consecutive-shift rules, ready for validation_snapshot["details"].
    """

    checked_rules: tuple[HardRuleCode, ...]
    failed_rules: tuple[HardRuleCode, ...]
    details: Mapping[str, int | float]

    def __post_init__(self) -> None:
        # Copy first: a read-only view of a caller-owned dict would still change
        # when that caller mutates the original dict.
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def __hash__(self) -> int:
        # MappingProxyType is not hashable on Python 3.11
        return hash((self.checked_rules, self.failed_rules, frozenset(self.details.items())))

    @property
    def passed(self) -> bool:
        return not self.failed_rules


def evaluate(context: CandidateContext, policy: HardRulePolicy) -> HardRuleResult:
    """Check every rule the policy has switched on and report all that fail."""
    checked = tuple(rule for rule in HARD_RULES if rule.enabled(policy))
    return HardRuleResult(
        checked_rules=tuple(rule.code for rule in checked),
        failed_rules=tuple(rule.code for rule in checked if rule.violated(context, policy)),
        details={
            "daily_hours": _number(daily_hours(context)),
            "daily_limit": _number(Fraction(policy.maximum_daily_hours)),
            "weekly_hours": _number(weekly_hours(context)),
            "weekly_limit": _number(Fraction(policy.maximum_weekly_hours)),
            "projected_consecutive_shifts": projected_consecutive_shifts(context),
            "consecutive_limit": policy.maximum_consecutive_shifts,
        },
    )


def _number(value: Fraction) -> int | float:
    """A JSON number: whole hours stay integers, so 56 is not stored as 56.0."""
    return value.numerator if value.denominator == 1 else float(value)
