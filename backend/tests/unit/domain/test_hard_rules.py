"""Hard Rules of the round 1 contract, section 7 (docs/round1/round1-contract-draft.md)."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.core.clock import APP_TIMEZONE
from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import (
    CandidateContext,
    HardRulePolicy,
    RosterEntry,
    ShiftSlot,
    SourceShift,
    UnavailabilityPeriod,
    projected_consecutive_shifts,
    week_start,
)
from app.domain.constraints.evaluator import evaluate
from app.domain.constraints.hard_rules import HARD_RULES
from app.domain.enums import RosterStatus, StaffStatus

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2

MONDAY = datetime(2026, 10, 12, tzinfo=APP_TIMEZONE)

# The seeded policy (base_data.py)
POLICY = HardRulePolicy(
    require_active_staff=True,
    prevent_shift_conflict=True,
    require_matching_role=True,
    require_matching_skill=True,
    preserve_source_ward_minimum=True,
    preserve_minimum_staffing=True,
    minimum_rest_hours=Decimal(11),
    maximum_daily_hours=Decimal(12),
    maximum_weekly_hours=Decimal(52),
    maximum_consecutive_shifts=7,
)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """Bangkok time, `day` days after Monday 2026-10-12."""
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute)


def slot(shift_id: int, start_at: datetime, hours: float = 8) -> ShiftSlot:
    return ShiftSlot(shift_id, start_at, start_at + timedelta(hours=hours))


def on(shift: ShiftSlot, status: RosterStatus = RosterStatus.ASSIGNED) -> RosterEntry:
    return RosterEntry(shift, status)


def day_shifts(days: range) -> tuple[RosterEntry, ...]:
    """An 08:00 to 16:00 shift on each day, so 16 hours of rest between them."""
    return tuple(on(slot(100 + day, at(day, 8))) for day in days)


# Wednesday 08:00 to 16:00
PROPOSED = slot(1, at(2, 8))


def candidate(**changes: Any) -> CandidateContext:
    """An RN with ICU and BLS, free all week, selected for headcount only.

    The requirement of the shift lists RN, so that is the role set the caller passes.
    """
    values: dict[str, Any] = {
        "staff_id": 201,
        "status": StaffStatus.ACTIVE,
        "role_id": RN,
        "skill_ids": frozenset({ICU, BLS}),
        "proposed_shift": PROPOSED,
        "roster": (),
        "unavailability": (),
        "target_role_ids": frozenset({RN}),
        "target_skill_ids": frozenset(),
    }
    return CandidateContext(**(values | changes))


# One way to break each rule and no other rule
BREAKS: dict[HardRuleCode, dict[str, Any]] = {
    HardRuleCode.STAFF_NOT_ACTIVE: {"status": StaffStatus.INACTIVE},
    HardRuleCode.ALREADY_ON_SHIFT: {"roster": (on(PROPOSED),)},
    HardRuleCode.UNAVAILABLE: {"unavailability": (UnavailabilityPeriod(at(2, 10), at(2, 12)),)},
    HardRuleCode.SHIFT_CONFLICT: {"roster": (on(slot(2, at(2, 14), hours=2)),)},
    HardRuleCode.ROLE_MISMATCH: {"target_role_ids": frozenset({HEAD_NURSE})},
    HardRuleCode.SKILL_MISMATCH: {
        "skill_ids": frozenset({BLS}),
        "target_skill_ids": frozenset({ICU}),
    },
    # Tuesday 22:00 to Wednesday 02:00 leaves 6 hours before the proposed shift
    HardRuleCode.INSUFFICIENT_REST: {"roster": (on(slot(2, at(1, 22), hours=4)),)},
    HardRuleCode.DAILY_HOURS_EXCEEDED: {"proposed_shift": slot(1, at(2, 8), hours=13)},
    # Six other shifts in the week: 48 + 8 = 56 hours, in a run of exactly 7
    HardRuleCode.WEEKLY_HOURS_EXCEEDED: {
        "roster": day_shifts(range(0, 2)) + day_shifts(range(3, 7))
    },
    # The seven days before a Monday shift: a run of 8, but only 8 hours this week
    HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED: {
        "proposed_shift": slot(1, at(0, 8)),
        "roster": day_shifts(range(-7, 0)),
    },
    HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION: {
        "source_shift": SourceShift(assigned_count=5, required_staff=5, minimum_staff=4)
    },
}

FLAGS: dict[HardRuleCode, str] = {
    HardRuleCode.STAFF_NOT_ACTIVE: "require_active_staff",
    HardRuleCode.SHIFT_CONFLICT: "prevent_shift_conflict",
    HardRuleCode.ROLE_MISMATCH: "require_matching_role",
    HardRuleCode.SKILL_MISMATCH: "require_matching_skill",
    HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION: "preserve_source_ward_minimum",
}


# --------------------------------------------------------------------------- #
# Codes, order and flags
# --------------------------------------------------------------------------- #
def test_codes_follow_the_contract_table() -> None:
    assert [code.value for code in HardRuleCode] == [
        "STAFF_NOT_ACTIVE",
        "ALREADY_ON_SHIFT",
        "UNAVAILABLE",
        "SHIFT_CONFLICT",
        "ROLE_MISMATCH",
        "SKILL_MISMATCH",
        "INSUFFICIENT_REST",
        "DAILY_HOURS_EXCEEDED",
        "WEEKLY_HOURS_EXCEEDED",
        "CONSECUTIVE_SHIFTS_EXCEEDED",
        "SOURCE_WARD_MINIMUM_VIOLATION",
    ]
    assert [rule.code for rule in HARD_RULES] == list(HardRuleCode)


def test_free_candidate_passes_every_rule() -> None:
    result = evaluate(candidate(), POLICY)

    assert result.passed
    assert result.failed_rules == ()
    assert result.checked_rules == tuple(HardRuleCode)


@pytest.mark.parametrize("code", list(HardRuleCode))
def test_each_rule_fails_alone(code: HardRuleCode) -> None:
    result = evaluate(candidate(**BREAKS[code]), POLICY)

    assert result.failed_rules == (code,)
    assert not result.passed


@pytest.mark.parametrize("code", list(FLAGS))
def test_rule_switched_off_is_neither_checked_nor_failed(code: HardRuleCode) -> None:
    policy = replace(POLICY, **{FLAGS[code]: False})

    result = evaluate(candidate(**BREAKS[code]), policy)

    assert result.passed
    assert code not in result.checked_rules


def test_rules_without_a_flag_run_when_every_flag_is_off() -> None:
    policy = replace(POLICY, **dict.fromkeys(FLAGS.values(), False))

    result = evaluate(candidate(), policy)

    assert result.checked_rules == (
        HardRuleCode.ALREADY_ON_SHIFT,
        HardRuleCode.UNAVAILABLE,
        HardRuleCode.INSUFFICIENT_REST,
        HardRuleCode.DAILY_HOURS_EXCEEDED,
        HardRuleCode.WEEKLY_HOURS_EXCEEDED,
        HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,
    )


def test_every_broken_rule_is_reported_in_contract_order() -> None:
    """Safety records all of them, joined with "," in this order (section 7.4)."""
    broken = (
        BREAKS[HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION]
        | BREAKS[HardRuleCode.ROLE_MISMATCH]
        | BREAKS[HardRuleCode.UNAVAILABLE]
        | BREAKS[HardRuleCode.STAFF_NOT_ACTIVE]
    )

    result = evaluate(candidate(**broken), POLICY)

    assert result.failed_rules == (
        HardRuleCode.STAFF_NOT_ACTIVE,
        HardRuleCode.UNAVAILABLE,
        HardRuleCode.ROLE_MISMATCH,
        HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION,
    )
    assert ",".join(result.failed_rules) == (
        "STAFF_NOT_ACTIVE,UNAVAILABLE,ROLE_MISMATCH,SOURCE_WARD_MINIMUM_VIOLATION"
    )


# --------------------------------------------------------------------------- #
# Roster rows that count
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("status", "blocked"),
    [
        (RosterStatus.ASSIGNED, True),
        (RosterStatus.PENDING_APPROVAL, True),
        (RosterStatus.CANCELLED, False),
        (RosterStatus.COMPLETED, False),
    ],
)
def test_only_committed_rows_put_the_candidate_on_the_shift(
    status: RosterStatus, blocked: bool
) -> None:
    result = evaluate(candidate(roster=(on(PROPOSED, status),)), POLICY)

    assert (HardRuleCode.ALREADY_ON_SHIFT in result.failed_rules) is blocked


@pytest.mark.parametrize(
    ("status", "clashes"),
    [
        (RosterStatus.ASSIGNED, True),
        (RosterStatus.PENDING_APPROVAL, True),
        (RosterStatus.CANCELLED, False),
        (RosterStatus.COMPLETED, False),
    ],
)
def test_only_committed_rows_on_other_shifts_count(status: RosterStatus, clashes: bool) -> None:
    other = slot(2, at(2, 14), hours=2)

    result = evaluate(candidate(roster=(on(other, status),)), POLICY)

    assert (HardRuleCode.SHIFT_CONFLICT in result.failed_rules) is clashes
    assert result.details["daily_hours"] == (10 if clashes else 8)


def test_repeated_rows_of_one_shift_count_once() -> None:
    other = slot(2, at(0, 8))

    result = evaluate(candidate(roster=(on(other), on(other))), POLICY)

    assert result.details["weekly_hours"] == 16


# --------------------------------------------------------------------------- #
# UNAVAILABLE and SHIFT_CONFLICT: overlap
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("start_at", "end_at", "blocked"),
    [
        (at(0, 0), None, True),  # no return date: unavailable from start_at on
        (at(2, 15), None, True),
        (at(2, 7), at(2, 8, 1), True),  # one minute into the shift
        (at(2, 0), at(2, 8), False),  # back exactly when the shift starts
        (at(2, 16), None, False),  # leaves exactly when the shift ends
        (at(3, 0), at(4, 0), False),
    ],
)
def test_unavailability_blocks_only_when_it_overlaps_the_shift(
    start_at: datetime, end_at: datetime | None, blocked: bool
) -> None:
    period = UnavailabilityPeriod(start_at, end_at)

    result = evaluate(candidate(unavailability=(period,)), POLICY)

    assert (HardRuleCode.UNAVAILABLE in result.failed_rules) is blocked


@pytest.mark.parametrize(
    ("other", "clashes"),
    [
        (slot(2, at(2, 0)), False),  # ends exactly when the proposed shift starts
        (slot(2, at(2, 16)), False),  # starts exactly when it ends
        (slot(2, at(2, 0), hours=8.5), True),
        (slot(2, at(2, 15, 59)), True),
        (slot(2, at(2, 10), hours=1), True),  # inside the proposed shift
    ],
)
def test_shifts_that_only_touch_do_not_conflict(other: ShiftSlot, clashes: bool) -> None:
    result = evaluate(candidate(roster=(on(other),)), POLICY)

    assert (HardRuleCode.SHIFT_CONFLICT in result.failed_rules) is clashes


def test_overlapping_shift_is_a_conflict_and_not_a_rest_failure() -> None:
    result = evaluate(candidate(**BREAKS[HardRuleCode.SHIFT_CONFLICT]), POLICY)

    assert HardRuleCode.SHIFT_CONFLICT in result.failed_rules
    assert HardRuleCode.INSUFFICIENT_REST not in result.failed_rules


def test_back_to_back_shifts_fail_rest_and_not_conflict() -> None:
    result = evaluate(candidate(roster=(on(slot(2, at(2, 16), hours=4)),)), POLICY)

    assert HardRuleCode.INSUFFICIENT_REST in result.failed_rules
    assert HardRuleCode.SHIFT_CONFLICT not in result.failed_rules


# --------------------------------------------------------------------------- #
# INSUFFICIENT_REST
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("rest", "too_short"),
    [
        (timedelta(hours=11), False),  # equal to the minimum passes
        (timedelta(hours=10, minutes=59), True),
        (timedelta(hours=30), False),
    ],
)
@pytest.mark.parametrize("side", ["before", "after"])
def test_rest_is_checked_before_and_after_the_proposed_shift(
    rest: timedelta, too_short: bool, side: str
) -> None:
    if side == "before":
        other = ShiftSlot(
            2, PROPOSED.start_at - rest - timedelta(hours=4), PROPOSED.start_at - rest
        )
    else:
        other = ShiftSlot(2, PROPOSED.end_at + rest, PROPOSED.end_at + rest + timedelta(hours=4))

    result = evaluate(candidate(roster=(on(other),)), POLICY)

    assert (HardRuleCode.INSUFFICIENT_REST in result.failed_rules) is too_short


@pytest.mark.parametrize(
    ("rest", "too_short"),
    [(timedelta(hours=11, minutes=30), False), (timedelta(hours=11, minutes=29), True)],
)
def test_rest_minimum_can_be_a_fraction_of_an_hour(rest: timedelta, too_short: bool) -> None:
    policy = replace(POLICY, minimum_rest_hours=Decimal("11.5"))
    other = ShiftSlot(2, PROPOSED.start_at - rest - timedelta(hours=4), PROPOSED.start_at - rest)

    result = evaluate(candidate(roster=(on(other),)), policy)

    assert (HardRuleCode.INSUFFICIENT_REST in result.failed_rules) is too_short


# --------------------------------------------------------------------------- #
# DAILY_HOURS_EXCEEDED and WEEKLY_HOURS_EXCEEDED (Q14)
# --------------------------------------------------------------------------- #
def test_night_shift_belongs_to_the_day_it_starts_on() -> None:
    night = slot(1, at(1, 23))  # Tuesday 23:00 to Wednesday 07:00
    wednesday_evening = slot(2, at(2, 18), hours=5)
    tuesday_morning = slot(3, at(1, 7), hours=5)

    ends_on_wednesday = evaluate(
        candidate(proposed_shift=night, roster=(on(wednesday_evening),)), POLICY
    )
    starts_on_tuesday = evaluate(
        candidate(proposed_shift=night, roster=(on(tuesday_morning),)), POLICY
    )

    # All 8 hours count for Tuesday, none for Wednesday
    assert ends_on_wednesday.details["daily_hours"] == 8
    assert ends_on_wednesday.passed
    assert starts_on_tuesday.details["daily_hours"] == 13
    assert starts_on_tuesday.failed_rules == (HardRuleCode.DAILY_HOURS_EXCEEDED,)


def test_daily_hours_equal_to_the_limit_pass() -> None:
    night = slot(1, at(1, 23))
    tuesday_morning = slot(3, at(1, 7), hours=5)
    policy = replace(POLICY, maximum_daily_hours=Decimal(13))

    result = evaluate(candidate(proposed_shift=night, roster=(on(tuesday_morning),)), policy)

    assert result.passed
    assert (result.details["daily_hours"], result.details["daily_limit"]) == (13, 13)


def test_day_is_the_bangkok_date_of_the_start_time() -> None:
    """Tuesday 17:30 UTC is Wednesday 00:30 in Bangkok."""
    start_at = datetime(2026, 10, 13, 17, 30, tzinfo=UTC)
    proposed = ShiftSlot(1, start_at, start_at + timedelta(hours=8))
    wednesday_evening = slot(2, at(2, 20), hours=4)

    result = evaluate(candidate(proposed_shift=proposed, roster=(on(wednesday_evening),)), POLICY)

    assert result.details["daily_hours"] == 12
    assert result.passed


def test_weekly_hours_equal_to_the_limit_pass() -> None:
    roster = (
        *day_shifts(range(0, 2)),
        *day_shifts(range(3, 6)),
        on(slot(2, at(6, 8), hours=4)),
    )

    result = evaluate(candidate(roster=roster), POLICY)

    assert result.passed
    assert (result.details["weekly_hours"], result.details["weekly_limit"]) == (52, 52)


def test_weekly_hours_over_the_limit_fail_with_the_totals_in_details() -> None:
    """The example of section 7.2: {"weekly_hours": 56, "weekly_limit": 52}."""
    result = evaluate(candidate(**BREAKS[HardRuleCode.WEEKLY_HOURS_EXCEEDED]), POLICY)

    assert result.failed_rules == (HardRuleCode.WEEKLY_HOURS_EXCEEDED,)
    assert result.details["weekly_hours"] == 56
    assert result.details["weekly_limit"] == 52


def test_week_runs_from_monday_to_monday_by_start_time() -> None:
    roster = (
        on(slot(2, at(-1, 23, 59), hours=1)),  # Sunday 23:59: the week before
        on(slot(3, at(6, 23))),  # Sunday 23:00: this week, all 8 hours of it
        on(slot(4, at(7, 0))),  # next Monday 00:00: the week after
    )

    result = evaluate(candidate(proposed_shift=slot(1, at(0, 8)), roster=roster), POLICY)

    assert result.details["weekly_hours"] == 16


def test_week_start_is_monday_midnight_in_bangkok() -> None:
    assert MONDAY.weekday() == 0
    assert week_start(MONDAY) == MONDAY
    assert week_start(at(6, 23, 59)) == MONDAY
    assert week_start(at(7, 0)) == MONDAY + timedelta(days=7)
    # Sunday 17:30 UTC is already Monday 00:30 in Bangkok
    assert week_start(datetime(2026, 10, 11, 17, 30, tzinfo=UTC)) == MONDAY
    assert week_start(datetime(2026, 10, 11, 16, 59, tzinfo=UTC)) == MONDAY - timedelta(days=7)


# --------------------------------------------------------------------------- #
# CONSECUTIVE_SHIFTS_EXCEEDED
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("new_start", "run"),
    [
        (at(1, 8), 2),  # Tuesday 08:00: 16 hours of rest
        (at(1, 16), 2),  # Tuesday 16:00: exactly 24 hours still continues the run
        (at(2, 8), 1),  # Wednesday 08:00: 40 hours starts a new run
    ],
)
def test_rest_of_24_hours_or_less_keeps_the_run(new_start: datetime, run: int) -> None:
    """The table of section 7.2: the earlier shift ends on Monday 16:00."""
    context = candidate(proposed_shift=slot(1, new_start), roster=(on(slot(2, at(0, 8))),))

    assert projected_consecutive_shifts(context) == run
    assert evaluate(context, POLICY).details["projected_consecutive_shifts"] == run


@pytest.mark.parametrize(("before", "run", "passes"), [(3, 7, True), (4, 8, False)])
def test_proposed_shift_joins_the_run_before_it_to_the_run_after_it(
    before: int, run: int, passes: bool
) -> None:
    context = candidate(
        proposed_shift=slot(1, at(0, 8)),
        roster=day_shifts(range(-before, 0)) + day_shifts(range(1, 4)),
    )

    result = evaluate(context, POLICY)

    assert result.details["projected_consecutive_shifts"] == run
    assert result.details["consecutive_limit"] == 7
    assert result.passed is passes
    assert (HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED in result.failed_rules) is not passes


def test_only_the_run_that_holds_the_proposed_shift_counts() -> None:
    context = candidate(roster=day_shifts(range(-14, -9)) + day_shifts(range(10, 14)))

    assert projected_consecutive_shifts(context) == 1


def test_cancelled_shift_breaks_the_run() -> None:
    roster = (
        on(slot(2, at(0, 8))),
        on(slot(3, at(1, 8)), RosterStatus.CANCELLED),
    )

    # Monday 16:00 to Wednesday 08:00 is 40 hours of rest
    assert projected_consecutive_shifts(candidate(roster=roster)) == 1


def test_limit_of_zero_lets_nobody_take_a_shift() -> None:
    result = evaluate(candidate(), replace(POLICY, maximum_consecutive_shifts=0))

    assert result.failed_rules == (HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,)


# --------------------------------------------------------------------------- #
# ROLE_MISMATCH and SKILL_MISMATCH (Q55)
# --------------------------------------------------------------------------- #
def test_candidate_selected_for_headcount_passes_without_the_missing_skill() -> None:
    result = evaluate(candidate(skill_ids=frozenset({BLS})), POLICY)

    assert result.passed
    assert {HardRuleCode.ROLE_MISMATCH, HardRuleCode.SKILL_MISMATCH} <= set(result.checked_rules)


def test_candidate_needs_every_skill_they_are_selected_to_fill() -> None:
    context = candidate(skill_ids=frozenset({BLS}), target_skill_ids=frozenset({ICU, BLS}))

    assert evaluate(context, POLICY).failed_rules == (HardRuleCode.SKILL_MISMATCH,)


def test_role_only_has_to_be_one_of_the_target_roles() -> None:
    context = candidate(target_role_ids=frozenset({RN, HEAD_NURSE}))

    assert evaluate(context, POLICY).passed


@pytest.mark.parametrize(("role_id", "passes"), [(RN, True), (HEAD_NURSE, False)])
def test_headcount_only_candidate_needs_a_role_of_the_shift_requirement(
    role_id: int, passes: bool
) -> None:
    """Section 8.3: with no role target to fill, the caller passes the requirement's roles."""
    requirement_roles = frozenset({RN})
    context = candidate(
        role_id=role_id, target_role_ids=requirement_roles, target_skill_ids=frozenset()
    )

    result = evaluate(context, POLICY)

    assert result.passed is passes
    assert result.failed_rules == (() if passes else (HardRuleCode.ROLE_MISMATCH,))


def test_any_role_passes_only_when_the_requirement_lists_no_role() -> None:
    """An empty role set is not how a caller says "headcount only"."""
    result = evaluate(candidate(role_id=HEAD_NURSE, target_role_ids=frozenset()), POLICY)

    assert result.passed
    assert HardRuleCode.ROLE_MISMATCH in result.checked_rules


# --------------------------------------------------------------------------- #
# SOURCE_WARD_MINIMUM_VIOLATION (Q15, Q51)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("assigned", "required", "minimum", "preserve_minimum_staffing", "violates"),
    [
        (5, 5, 4, True, True),  # the example of Q15: 5 staff, target 5
        (6, 5, 4, True, False),
        (5, 3, 5, True, True),  # minimum_staff is the floor of the target
        (5, 3, 5, False, False),  # flag off: required_staff alone
        (4, 4, 2, False, True),
    ],
)
def test_source_shift_keeps_the_target_of_the_gap_calculation(
    assigned: int, required: int, minimum: int, preserve_minimum_staffing: bool, violates: bool
) -> None:
    policy = replace(POLICY, preserve_minimum_staffing=preserve_minimum_staffing)
    source = SourceShift(assigned_count=assigned, required_staff=required, minimum_staff=minimum)

    result = evaluate(candidate(source_shift=source), policy)

    assert (HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in result.failed_rules) is violates


def test_candidate_without_a_source_shift_passes_but_the_rule_is_checked() -> None:
    result = evaluate(candidate(source_shift=None), POLICY)

    assert result.passed
    assert HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in result.checked_rules


# --------------------------------------------------------------------------- #
# Golden Case (workflow.md section 10.2)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("staff_id", "skill_ids", "on_shift_two", "run", "week"),
    [
        (201, {ICU, BLS}, False, 1, 8),
        (202, {BLS}, True, 2, 16),
        (203, {ICU}, True, 2, 16),
    ],
)
def test_golden_case_candidates_pass_for_the_night_shift(
    staff_id: int, skill_ids: set[int], on_shift_two: bool, run: int, week: int
) -> None:
    day = datetime(2026, 10, 9, tzinfo=APP_TIMEZONE)
    shift_one = ShiftSlot(1, day + timedelta(hours=23), day + timedelta(days=1, hours=7))
    shift_two = ShiftSlot(2, day + timedelta(days=2, hours=7), day + timedelta(days=2, hours=15))
    context = candidate(
        staff_id=staff_id,
        skill_ids=frozenset(skill_ids),
        proposed_shift=shift_one,
        roster=(on(shift_two),) if on_shift_two else (),
        target_role_ids=frozenset({RN}),
    )

    result = evaluate(context, POLICY)

    assert result.passed
    # Shift 2 starts exactly 24 hours after shift 1 ends
    assert result.details["projected_consecutive_shifts"] == run
    assert result.details["weekly_hours"] == week


# --------------------------------------------------------------------------- #
# Result and input values
# --------------------------------------------------------------------------- #
def test_details_carry_the_totals_and_limits_as_json_numbers() -> None:
    result = evaluate(candidate(proposed_shift=slot(1, at(2, 8), hours=7.5)), POLICY)

    assert dict(result.details) == {
        "daily_hours": 7.5,
        "daily_limit": 12,
        "weekly_hours": 7.5,
        "weekly_limit": 52,
        "projected_consecutive_shifts": 1,
        "consecutive_limit": 7,
    }
    # Whole hours stay integers, so the snapshot holds 12 and not 12.0
    assert all(isinstance(result.details[key], int) for key in ("daily_limit", "weekly_limit"))
    assert isinstance(result.details["daily_hours"], float)


def test_result_cannot_be_changed_and_can_be_hashed() -> None:
    result = evaluate(candidate(), POLICY)

    with pytest.raises(TypeError):
        result.details["daily_hours"] = 0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.failed_rules = ()  # type: ignore[misc]
    assert result == evaluate(candidate(), POLICY)
    assert hash(result) == hash(evaluate(candidate(), POLICY))


def test_context_copies_the_collections_it_is_given() -> None:
    roster = [on(slot(2, at(0, 8)))]
    skills = {ICU}

    context = candidate(roster=roster, skill_ids=skills, target_skill_ids={ICU})
    roster.clear()
    skills.clear()

    assert len(context.roster) == 1
    assert evaluate(context, POLICY).passed
    with pytest.raises(FrozenInstanceError):
        context.status = StaffStatus.INACTIVE  # type: ignore[misc]


def test_shift_times_must_be_aware_and_in_order() -> None:
    naive = datetime(2026, 10, 14, 8)

    with pytest.raises(ValueError, match="timezone-aware"):
        ShiftSlot(1, naive, naive + timedelta(hours=8))
    with pytest.raises(ValueError, match="end after it starts"):
        ShiftSlot(1, at(2, 8), at(2, 8))
    with pytest.raises(ValueError, match="timezone-aware"):
        UnavailabilityPeriod(at(2, 8), naive)


def test_rows_that_disagree_about_a_shift_are_rejected() -> None:
    moved = ShiftSlot(PROPOSED.shift_id, at(3, 8), at(3, 16))

    with pytest.raises(ValueError, match="Conflicting times for shift_id=1"):
        candidate(roster=(on(moved, RosterStatus.CANCELLED),))


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"minimum_rest_hours": 11.0}, TypeError),
        ({"maximum_daily_hours": True}, TypeError),
        ({"maximum_weekly_hours": Decimal(-1)}, ValueError),
        ({"maximum_weekly_hours": Decimal("NaN")}, ValueError),
        ({"maximum_consecutive_shifts": Decimal(7)}, TypeError),
        ({"maximum_consecutive_shifts": -1}, ValueError),
    ],
)
def test_policy_rejects_limits_it_cannot_compare(
    change: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        replace(POLICY, **change)


def test_source_shift_counts_cannot_be_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SourceShift(assigned_count=-1, required_staff=1, minimum_staff=1)
