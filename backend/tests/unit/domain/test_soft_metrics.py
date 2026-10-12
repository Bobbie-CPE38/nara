"""Soft Constraint inputs (round 1 contract, section 8.3)."""

from datetime import datetime, timedelta
from fractions import Fraction

import pytest

from app.core.clock import APP_TIMEZONE
from app.domain.constraints.context import ShiftSlot
from app.domain.constraints.soft_metrics import (
    SoftMetrics,
    ranking_key,
    source_priority,
    working_time_at,
)
from app.domain.enums import CandidateSource

MONDAY = datetime(2026, 10, 12, tzinfo=APP_TIMEZONE)
ORDER = (CandidateSource.SAME_WARD, CandidateSource.FLOAT_POOL, CandidateSource.CROSS_WARD)
NOW = MONDAY + timedelta(days=2, hours=12)  # Wednesday 12:00


def at(day: int, hour: int) -> datetime:
    return MONDAY + timedelta(days=day, hours=hour)


def slot(shift_id: int, start_at: datetime, hours: float = 8) -> ShiftSlot:
    return ShiftSlot(shift_id, start_at, start_at + timedelta(hours=hours))


def metrics(
    staff_id: int = 1,
    *,
    source: CandidateSource = CandidateSource.SAME_WARD,
    hours: int = 0,
    run: int = 1,
    overtime: int = 0,
) -> SoftMetrics:
    return SoftMetrics(
        staff_id=staff_id,
        source=source,
        hours_this_week=Fraction(hours),
        projected_consecutive_shifts=run,
        overtime_hours=Fraction(overtime),
    )


def test_ranking_key_orders_by_source_hours_run_overtime_then_staff_id() -> None:
    ordered = [
        metrics(9, hours=50, run=7, overtime=9),
        metrics(9, source=CandidateSource.FLOAT_POOL),
        metrics(9, source=CandidateSource.CROSS_WARD),
    ]
    assert sorted(reversed(ordered), key=lambda m: ranking_key(m, ORDER)) == ordered

    by_hours = [metrics(9, hours=1), metrics(1, hours=2)]
    assert sorted(reversed(by_hours), key=lambda m: ranking_key(m, ORDER)) == by_hours
    by_run = [metrics(9, run=1), metrics(1, run=2)]
    assert sorted(reversed(by_run), key=lambda m: ranking_key(m, ORDER)) == by_run
    by_overtime = [metrics(9, overtime=1), metrics(1, overtime=2)]
    assert sorted(reversed(by_overtime), key=lambda m: ranking_key(m, ORDER)) == by_overtime
    by_id = [metrics(1), metrics(2)]
    assert sorted(reversed(by_id), key=lambda m: ranking_key(m, ORDER)) == by_id


def test_source_priority_rejects_a_source_missing_from_the_order() -> None:
    with pytest.raises(ValueError):
        source_priority(CandidateSource.CROSS_WARD, ORDER[:2])


def test_no_shifts_gives_zeros() -> None:
    result = working_time_at(NOW, shifts=[], night_shift_ids=set(), overtime_minutes=0)

    assert (result.hours_today, result.hours_this_week, result.rest_hours) == (0, 0, 0)
    assert (result.consecutive_shifts, result.consecutive_night_shifts) == (0, 0)


def test_a_running_shift_has_no_rest() -> None:
    shifts = [slot(1, at(0, 8)), slot(2, at(1, 8)), slot(3, at(2, 8))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids=set(), overtime_minutes=0)

    assert result.hours_today == 8
    assert result.hours_this_week == 24
    assert result.rest_hours == 0
    assert (result.consecutive_shifts, result.consecutive_night_shifts) == (3, 0)


def test_rest_since_the_last_shift_ended() -> None:
    shifts = [slot(1, at(0, 8)), slot(2, at(1, 8))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids=set(), overtime_minutes=0)

    assert result.rest_hours == 20
    assert result.consecutive_shifts == 2


def test_a_rest_longer_than_24_hours_ends_the_run() -> None:
    result = working_time_at(
        NOW, shifts=[slot(1, at(0, 8))], night_shift_ids=set(), overtime_minutes=0
    )

    assert result.rest_hours == 44
    assert result.consecutive_shifts == 0


def test_a_future_shift_counts_for_the_week_but_not_the_run() -> None:
    shifts = [slot(1, at(2, 8)), slot(2, at(3, 8))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids=set(), overtime_minutes=0)

    assert result.hours_this_week == 16
    assert result.consecutive_shifts == 1


def test_the_run_crosses_the_week_boundary_but_the_week_hours_do_not() -> None:
    shifts = [slot(1, at(-1, 8)), slot(2, at(0, 8)), slot(3, at(1, 8)), slot(4, at(2, 8))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids=set(), overtime_minutes=0)

    assert result.hours_this_week == 24
    assert result.consecutive_shifts == 4


def test_night_streak_at_the_end_of_the_run() -> None:
    shifts = [slot(1, at(0, 8)), slot(2, at(0, 23)), slot(3, at(1, 23))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids={2, 3}, overtime_minutes=0)

    assert result.consecutive_shifts == 3
    assert result.consecutive_night_shifts == 2


def test_the_same_shift_listed_twice_counts_once() -> None:
    shifts = [slot(1, at(2, 8)), slot(1, at(2, 8))]

    result = working_time_at(NOW, shifts=shifts, night_shift_ids=set(), overtime_minutes=0)

    assert result.hours_this_week == 8
    assert result.consecutive_shifts == 1


def test_overtime_minutes_become_hours() -> None:
    result = working_time_at(NOW, shifts=[], night_shift_ids=set(), overtime_minutes=90)

    assert result.overtime_hours == Fraction(3, 2)


def test_a_naive_moment_raises() -> None:
    with pytest.raises(ValueError):
        working_time_at(
            datetime(2026, 10, 14, 12), shifts=[], night_shift_ids=set(), overtime_minutes=0
        )
