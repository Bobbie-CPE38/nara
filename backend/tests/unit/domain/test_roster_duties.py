"""Only recorded transfer links combine roster segments."""

from datetime import timedelta

from app.domain.constraints.context import ShiftSlot
from app.domain.constraints.roster_duties import DutySegment, joined_duties
from tests.unit.domain.test_hard_rules import MONDAY


def segment(assignment, shift, start, end, source=None):
    return DutySegment(
        assignment,
        ShiftSlot(shift, MONDAY + timedelta(hours=start), MONDAY + timedelta(hours=end)),
        source,
    )


def test_linked_pair_is_one_eight_hour_duty():
    assert joined_duties([segment(1, 10, 0, 2), segment(2, 20, 2, 8, 1)]) == (
        ShiftSlot(10, MONDAY, MONDAY + timedelta(hours=8)),
    )


def test_plain_adjacency_does_not_create_a_link():
    assert len(joined_duties([segment(1, 10, 0, 2), segment(2, 20, 2, 8)])) == 2


def test_gap_between_linked_rows_is_still_two_duties():
    assert len(joined_duties([segment(1, 10, 0, 2), segment(2, 20, 3, 8, 1)])) == 2


def test_missing_source_keeps_the_destination():
    destination = segment(2, 20, 2, 8, 1)
    assert joined_duties([destination]) == (destination.shift,)


def test_transfer_chain_is_order_independent():
    first = segment(1, 10, 0, 2)
    second = segment(2, 20, 2, 5, 1)
    third = segment(3, 30, 5, 8, 2)
    assert joined_duties([third, first, second]) == (
        ShiftSlot(10, MONDAY, MONDAY + timedelta(hours=8)),
    )


def test_missing_source_at_week_boundary_uses_the_remaining_segment_start():
    from app.domain.constraints.soft_metrics import working_time_at

    source = segment(1, 10, -1, 1)  # Sunday 23:00 -> Monday 01:00.
    destination = segment(2, 20, 1, 7, 1)
    moment = MONDAY + timedelta(hours=8)
    complete = working_time_at(
        moment,
        shifts=joined_duties([source, destination]),
        night_shift_ids={10, 20},
        overtime_minutes=0,
    )
    missing = working_time_at(
        moment,
        shifts=joined_duties([destination]),
        night_shift_ids={10, 20},
        overtime_minutes=0,
    )
    assert complete.hours_today == complete.hours_this_week == 0
    assert missing.hours_today == missing.hours_this_week == 6
    assert complete.consecutive_shifts == missing.consecutive_shifts == 1
    assert complete.rest_hours == missing.rest_hours == 1
