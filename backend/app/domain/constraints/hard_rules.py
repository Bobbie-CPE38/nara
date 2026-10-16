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
    duty_slot,
    hours,
    is_on_proposed_shift,
    leave_overlaps_shift,
    other_committed_shifts,
    other_duties,
    projected_consecutive_shifts,
    was_removed_from_proposed_shift,
    weekly_hours,
)
from app.domain.enums import StaffStatus


def staff_not_active(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return context.status != StaffStatus.ACTIVE


def already_on_shift(context: CandidateContext, policy: HardRulePolicy) -> bool:
    return is_on_proposed_shift(context)


def unavailable(context: CandidateContext, policy: HardRulePolicy) -> bool:
    """An unavailability period overlaps the shift, or the candidate was removed from it.

    A leave writes both a CANCELLED roster row and a period. ASSIGNMENT_CANCELLED
    writes only the roster row, and that person must not get the shift back either.
    """
    if was_removed_from_proposed_shift(context):
        return True
    shift = context.proposed_shift
    return any(
        leave_overlaps_shift(period.start_at, period.end_at, shift.start_at, shift.end_at)
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

    With a linked_duty, rest is measured from the whole duty and the linked part
    is not a separate shift: the move is not a break between two shifts.
    """
    proposed = duty_slot(context)
    minimum = Fraction(policy.minimum_rest_hours)
    for other in other_duties(context):
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
    """The source shift must stay fully staffed after the candidate leaves.

    The service layer measures this with the gap calculation of cases, per role
    and skill and per time slice, so "enough staff" means the same thing on both
    shifts (workflow.md 6.19). The rule only reads the result.
    """
    return context.source_shift is not None and context.source_shift.leaves_gap


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
