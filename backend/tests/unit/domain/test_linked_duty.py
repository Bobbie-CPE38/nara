"""linked_duty: a moved candidate's kept source part and the proposed shift are one duty.

The Y example (workflow.md section 6.20): Y works ward B 00:00 to 02:00, then moves to
ward A 02:00 to 08:00. Linking comes only from the explicit linked_duty field.
"""

from dataclasses import replace

import pytest

from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import (
    projected_consecutive_shifts,
    weekly_hours,
)
from app.domain.constraints.evaluator import evaluate
from app.domain.enums import RosterStatus
from tests.unit.domain.test_hard_rules import POLICY, at, candidate, on, slot


def y_example(**changes):
    source = slot(10, at(2, 0), hours=2)
    values = {
        "proposed_shift": slot(1, at(2, 2), hours=6),
        "roster": (on(source),),
        "linked_duty": source,
    }
    return candidate(**(values | changes))


def test_y_example_passes_as_one_duty() -> None:
    context = y_example()
    result = evaluate(context, POLICY)
    assert result.failed_rules == ()
    assert result.details["daily_hours"] == 8
    assert result.details["weekly_hours"] == 8
    assert projected_consecutive_shifts(context) == 1


def test_consecutive_count_counts_the_duty_once() -> None:
    earlier = on(slot(20, at(1, 0)))  # Tuesday 00:00 to 08:00, 16 hours of rest
    context = y_example()
    context = replace(context, roster=(*context.roster, earlier))
    assert projected_consecutive_shifts(context) == 2
    assert projected_consecutive_shifts(replace(context, linked_duty=None)) == 3


def test_same_rows_without_link_fail_rest() -> None:
    result = evaluate(y_example(linked_duty=None), POLICY)
    assert HardRuleCode.INSUFFICIENT_REST in result.failed_rules


def test_rest_is_measured_from_the_start_of_the_duty() -> None:
    # Ends Tuesday 22:00, 2 hours before the duty starts at Wednesday 00:00
    before = on(slot(20, at(1, 14)))
    context = y_example()
    context = replace(context, roster=(*context.roster, before))
    assert HardRuleCode.INSUFFICIENT_REST in evaluate(context, POLICY).failed_rules


def test_rest_is_measured_from_the_end_of_the_duty() -> None:
    # Starts Wednesday 10:00, 2 hours after the duty ends at 08:00
    after = on(slot(20, at(2, 10)))
    context = y_example()
    context = replace(context, roster=(*context.roster, after))
    assert HardRuleCode.INSUFFICIENT_REST in evaluate(context, POLICY).failed_rules


def test_enough_rest_around_the_duty_passes() -> None:
    before = on(slot(20, at(1, 0)))  # ends Tuesday 08:00, 16 hours before
    after = on(slot(21, at(2, 19), hours=2))  # starts 11 hours after
    context = y_example()
    context = replace(context, roster=(*context.roster, before, after))
    assert evaluate(context, POLICY).failed_rules == ()


def test_duty_across_midnight_belongs_to_the_start_day() -> None:
    source = slot(10, at(1, 22), hours=2.5)  # Tuesday 22:00 to Wednesday 00:30
    context = candidate(
        proposed_shift=slot(1, at(2, 0, 30), hours=5.5),
        roster=(on(source),),
        linked_duty=source,
    )
    result = evaluate(context, POLICY)
    assert result.failed_rules == ()
    assert result.details["daily_hours"] == 8


def test_day_hours_of_the_start_day_include_other_shifts() -> None:
    # A second shift on Tuesday 12:00 to 18:00 would be 6 + 8 = 14 hours that day
    source = slot(10, at(1, 22), hours=2.5)
    other = on(slot(20, at(1, 12), hours=6))
    context = candidate(
        proposed_shift=slot(1, at(2, 0, 30), hours=5.5),
        roster=(on(source), other),
        linked_duty=source,
    )
    result = evaluate(context, POLICY)
    assert result.details["daily_hours"] == 14
    assert HardRuleCode.DAILY_HOURS_EXCEEDED in result.failed_rules


def test_weekly_hours_count_both_parts_once() -> None:
    other = on(slot(20, at(0, 8)))
    context = y_example()
    context = replace(context, roster=(*context.roster, other))
    assert weekly_hours(context) == 16


def test_link_changes_nothing_for_hours_without_it() -> None:
    context = y_example(linked_duty=None)
    assert weekly_hours(context) == 8


def test_linked_duty_must_be_another_shift() -> None:
    same = slot(1, at(2, 0), hours=2)
    with pytest.raises(ValueError):
        candidate(proposed_shift=slot(1, at(2, 2), hours=6), roster=(on(same),), linked_duty=same)


def test_linked_duty_must_end_where_the_proposed_shift_starts() -> None:
    source = slot(10, at(2, 0), hours=1)  # ends 01:00, proposed starts 02:00
    with pytest.raises(ValueError):
        y_example(roster=(on(source),), linked_duty=source)


def test_linked_duty_must_be_a_committed_roster_entry() -> None:
    source = slot(10, at(2, 0), hours=2)
    with pytest.raises(ValueError):
        y_example(roster=(), linked_duty=source)
    with pytest.raises(ValueError):
        y_example(roster=(on(source, RosterStatus.CANCELLED),), linked_duty=source)
    with pytest.raises(ValueError):
        y_example(roster=(on(slot(10, at(2, 0), hours=3)),), linked_duty=source)
