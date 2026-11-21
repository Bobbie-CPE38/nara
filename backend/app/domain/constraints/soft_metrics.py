"""Soft Constraint inputs of one candidate (round 1 contract, section 8.3).

SoftMetrics is what plan_penalty and ranking_key read. WorkingTime is what
STAFF_WORKING_TIME_SNAPSHOT stores. No database access, clock reads, or writes:
working_time_service loads the rows and calls working_time_at().

Day, week and consecutive run are the definitions of context.py (Q14). Nothing
here keeps its own copy.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from app.domain.constraints.context import (
    MAX_REST_WITHIN_RUN,
    ShiftSlot,
    hours,
    local_day,
    shift_hours,
    week_start,
)
from app.domain.enums import CandidateSource


@dataclass(frozen=True, kw_only=True)
class SoftMetrics:
    """The values the Solver scores one candidate with.

    hours_this_week comes from the candidate's working-time snapshot.
    projected_consecutive_shifts is not in the snapshot: it is counted from the roster
    with the proposed shift inserted (context.py). Since round 6 PR EV6 (6.36.7)
    overtime_hours is the projected overtime of the week if the person takes this
    shift (projected_overtime_hours()), not only the overtime already worked.
    """

    staff_id: int
    source: CandidateSource
    hours_this_week: Fraction
    projected_consecutive_shifts: int
    overtime_hours: Fraction


# Hours of a week before the work counts as overtime (round 6 PR EV6, 6.36.7)
REGULAR_WEEKLY_HOURS = Fraction(40)


def projected_overtime_hours(
    *, overtime_worked: Fraction, hours_this_week: Fraction, added_hours: Fraction
) -> Fraction:
    """The week's overtime if the person takes the shift: what they already worked over
    their shifts (ATTENDANCE), plus the scheduled hours above REGULAR_WEEKLY_HOURS once
    `added_hours` join the week. Never below the overtime already worked."""
    over = hours_this_week + added_hours - REGULAR_WEEKLY_HOURS
    return overtime_worked + max(Fraction(0), over)


def source_priority(source: CandidateSource, order: Sequence[CandidateSource]) -> int:
    """Position of the source in candidate_source_priority. 0 is the closest source."""
    if source not in order:
        raise ValueError(f"candidate_source_priority does not list {source.value}")
    return order.index(source)


def ranking_key(
    metrics: SoftMetrics, order: Sequence[CandidateSource]
) -> tuple[int, Fraction, int, Fraction, int]:
    """Sort key behind CANDIDATE_ITEMS.rank. Smaller comes first. Never stored."""
    return (
        source_priority(metrics.source, order),
        metrics.hours_this_week,
        metrics.projected_consecutive_shifts,
        metrics.overtime_hours,
        metrics.staff_id,
    )


@dataclass(frozen=True, kw_only=True)
class WorkingTime:
    """The STAFF_WORKING_TIME_SNAPSHOT values of one person at one moment."""

    hours_today: Fraction
    hours_this_week: Fraction
    rest_hours: Fraction
    overtime_hours: Fraction
    consecutive_shifts: int
    consecutive_night_shifts: int


def working_time_at(
    moment: datetime,
    *,
    shifts: Iterable[ShiftSlot],
    night_shift_ids: Collection[int],
    overtime_minutes: int,
) -> WorkingTime:
    """Working time of one person as of `moment`.

    shifts: committed duty intervals. Identical intervals count once; distinct
    intervals on the same shift remain separate unless joined by a transfer link.
    overtime_minutes: overtime the person already worked in the week of `moment`.

    hours_today and hours_this_week add the whole shifts that start on that
    Asia/Bangkok day or in that week, also the ones that have not started yet.
    The other values only look at shifts that started at or before `moment`:
      * rest_hours: time since the latest of them ended. 0 while one is running,
        and 0 when there is none.
      * consecutive_shifts: length of the current run. 0 when the rest since the
        run ended is longer than 24 hours.
      * consecutive_night_shifts: night shifts at the end of that run.
    """
    if moment.utcoffset() is None:
        raise ValueError("moment must be timezone-aware")
    distinct = sorted(
        set(shifts),
        key=lambda shift: (shift.start_at, shift.end_at, shift.shift_id),
    )
    today, week = local_day(moment), week_start(moment)

    run: list[ShiftSlot] = []
    run_end: datetime | None = None
    for shift in distinct:
        if shift.start_at > moment:
            break
        if run_end is not None and shift.start_at - run_end > MAX_REST_WITHIN_RUN:
            run, run_end = [], None
        run.append(shift)
        run_end = shift.end_at if run_end is None else max(run_end, shift.end_at)

    rest_hours = Fraction(0)
    if run_end is not None and run_end < moment:
        rest_hours = hours(moment - run_end)
        if moment - run_end > MAX_REST_WITHIN_RUN:
            run = []

    nights = 0
    for shift in reversed(run):
        if shift.shift_id not in night_shift_ids:
            break
        nights += 1

    return WorkingTime(
        hours_today=sum(
            (shift_hours(shift) for shift in distinct if local_day(shift.start_at) == today),
            Fraction(0),
        ),
        hours_this_week=sum(
            (shift_hours(shift) for shift in distinct if week_start(shift.start_at) == week),
            Fraction(0),
        ),
        rest_hours=rest_hours,
        overtime_hours=Fraction(overtime_minutes, 60),
        consecutive_shifts=len(run),
        consecutive_night_shifts=nights,
    )
