"""The eleven Hard Rules (round 1 contract, section 7.2).

Each function answers one question: does the candidate break this rule for the
proposed shift? No database access, clock reads, or writes. evaluator.evaluate()
runs them; callers do not call a single rule on their own.

Limits: reaching a maximum passes and only going over it fails. Rest equal to the
minimum passes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import (
    CandidateContext,
    HardRulePolicy,
    ShiftSlot,
    daily_hours,
    hours,
    is_on_proposed_shift,
    other_committed_shifts,
    projected_consecutive_shifts,
    weekly_hours,
)
from app.domain.enums import StaffStatus
from app.domain.staffing.gap_calculator import effective_minimum_for


def staff_not_active(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return context.status != StaffStatus.ACTIVE


def already_on_shift(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return is_on_proposed_shift(context)


def unavailable(context: CandidateContext, policy: HardRulePolicy) -> bool:
    shift = context.proposed_shift
    return any(
        period.start_at < shift.end_at and (period.end_at is None or period.end_at > shift.start_at)
        for period in context.unavailability
    )


def shift_conflict(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return any(
        _overlaps(other, context.proposed_shift) for other in other_committed_shifts(context)
    )


def role_mismatch(context: CandidateContext, policy: HardRulePolicy) -> bool:
    # Empty = the shift requirement lists no role. A headcount-only candidate still
    # gets the requirement's roles from the caller (see CandidateContext)
    return bool(context.target_role_ids) and context.role_id not in context.target_role_ids


def skill_mismatch(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return not context.target_skill_ids <= context.skill_ids


def insufficient_rest(context: CandidateContext, policy: HardRulePolicy) -> bool:
    """Rest to the shifts before and after the proposed one.

    A shift that overlaps the proposed one is left to SHIFT_CONFLICT, so one clash
    is not reported under two codes.
    """
    proposed = context.proposed_shift
    minimum = Fraction(policy.minimum_rest_hours)
    for other in other_committed_shifts(context):
        if _overlaps(other, proposed):
            continue
        rest = (
            proposed.start_at - other.end_at
            if other.end_at <= proposed.start_at
            else other.start_at - proposed.end_at
        )
        if hours(rest) < minimum:
            return True
    return False


def daily_hours_exceeded(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return daily_hours(context) > Fraction(policy.maximum_daily_hours)


def weekly_hours_exceeded(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return weekly_hours(context) > Fraction(policy.maximum_weekly_hours)


def consecutive_shifts_exceeded(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return projected_consecutive_shifts(context) > policy.maximum_consecutive_shifts


def source_ward_minimum_violation(context: CandidateContext, policy: HardRulePolicy) -> bool:
    """The source shift must keep its target headcount after the candidate leaves.

    The target comes from effective_minimum_for(), the function the gap
    calculation uses, so "enough staff" means the same thing on both shifts.
    """
    source = context.source_shift
    if source is None:
        return False
    target = effective_minimum_for(
        required_staff=source.required_staff,
        minimum_staff=source.minimum_staff,
        preserve_minimum_staffing=policy.preserve_minimum_staffing,
    )
    return source.assigned_count - 1 < target


def _overlaps(first: ShiftSlot, second: ShiftSlot) -> bool:
    """Shifts that only touch at a boundary do not overlap."""
    return first.start_at < second.end_at and first.end_at > second.start_at


@dataclass(frozen=True)
class HardRule:
    code: HardRuleCode
    # False = the policy switches this rule off, and it is not checked at all
    enabled: Callable[[HardRulePolicy], bool]
    violated: Callable[[CandidateContext, HardRulePolicy], bool]


def _always(policy: HardRulePolicy) -> bool:
    return True


# One entry per code, in the order of HardRuleCode
HARD_RULES: tuple[HardRule, ...] = (
    HardRule(
        HardRuleCode.STAFF_NOT_ACTIVE, lambda policy: policy.require_active_staff, staff_not_active
    ),
    HardRule(HardRuleCode.ALREADY_ON_SHIFT, _always, already_on_shift),
    HardRule(HardRuleCode.UNAVAILABLE, _always, unavailable),
    HardRule(
        HardRuleCode.SHIFT_CONFLICT, lambda policy: policy.prevent_shift_conflict, shift_conflict
    ),
    HardRule(
        HardRuleCode.ROLE_MISMATCH, lambda policy: policy.require_matching_role, role_mismatch
    ),
    HardRule(
        HardRuleCode.SKILL_MISMATCH, lambda policy: policy.require_matching_skill, skill_mismatch
    ),
    HardRule(HardRuleCode.INSUFFICIENT_REST, _always, insufficient_rest),
    HardRule(HardRuleCode.DAILY_HOURS_EXCEEDED, _always, daily_hours_exceeded),
    HardRule(HardRuleCode.WEEKLY_HOURS_EXCEEDED, _always, weekly_hours_exceeded),
    HardRule(HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED, _always, consecutive_shifts_exceeded),
    HardRule(
        HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION,
        lambda policy: policy.preserve_source_ward_minimum,
        source_ward_minimum_violation,
    ),
)
