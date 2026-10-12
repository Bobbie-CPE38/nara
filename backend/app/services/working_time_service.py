"""
Working-time snapshots (round 1 contract, section 8.3).

The only writer of STAFF_WORKING_TIME_SNAPSHOT. The Solver calls capture() once
per Optimize round and scores the candidates with the values it returns.

Rules:
  * One captured_at for every person of a round: the caller reads the clock once.
  * A new row per person per call. Rows are never updated;
    CANDIDATE_ITEMS.working_time_snapshot_id names the row a plan used.
  * Never commits and writes no audit row. The caller flushes its own pending
    changes first.
  * Only roster rows in COMMITTED_ROSTER_STATUSES count. Day and week are the
    definitions of domain.constraints.context (Q14), taken at captured_at.
  * overtime_hours is overtime already worked: the ATTENDANCE rows of the week
    (by check_in_at) that are summarised, meaning check_out_at, work_minutes and
    overtime_minutes are all set.
  * rest_hours is 0 while a shift runs and also when the person has no earlier
    shift: the column is NOT NULL, so the two cannot be told apart.
  * Shifts that ended more than _RUN_LOOKBACK before the week are not loaded, so
    a run that long is cut. The run counts are not used for checks or scoring in
    round 1; the Solver scores projected_consecutive_shifts instead.
"""

from collections.abc import Collection
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Attendance, RosterAssignment, Shift, StaffWorkingTimeSnapshot
from app.domain.constraints.context import ShiftSlot, week_start
from app.domain.constraints.soft_metrics import WorkingTime, working_time_at
from app.domain.enums import COMMITTED_ROSTER_STATUSES, ShiftType

_RUN_LOOKBACK = timedelta(days=31)


class CapturedWorkingTime(NamedTuple):
    """The stored row and the exact values it was written from."""

    snapshot: StaffWorkingTimeSnapshot
    values: WorkingTime


def capture(
    db: Session, staff_ids: Collection[int], *, captured_at: datetime
) -> dict[int, CapturedWorkingTime]:
    """Write one snapshot per person as of captured_at; flush but never commit."""
    if not staff_ids:
        return {}
    week = week_start(captured_at)
    week_end = week + timedelta(days=7)

    shifts: dict[int, list[ShiftSlot]] = {}
    night_shift_ids: set[int] = set()
    roster_rows = db.execute(
        select(RosterAssignment.staff_id, Shift.id, Shift.start_at, Shift.end_at, Shift.shift_type)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(
            RosterAssignment.staff_id.in_(staff_ids),
            RosterAssignment.status.in_(list(COMMITTED_ROSTER_STATUSES)),
            Shift.end_at > week - _RUN_LOOKBACK,
            Shift.start_at < week_end,
        )
    )
    for staff_id, shift_id, start_at, end_at, shift_type in roster_rows:
        shifts.setdefault(staff_id, []).append(ShiftSlot(shift_id, start_at, end_at))
        if shift_type is ShiftType.NIGHT:
            night_shift_ids.add(shift_id)

    overtime_rows = db.execute(
        select(Attendance.staff_id, func.sum(Attendance.overtime_minutes))
        .where(
            Attendance.staff_id.in_(staff_ids),
            Attendance.check_out_at.is_not(None),
            Attendance.work_minutes.is_not(None),
            Attendance.overtime_minutes.is_not(None),
            Attendance.check_in_at >= week,
            Attendance.check_in_at < week_end,
        )
        .group_by(Attendance.staff_id)
    )
    overtime_minutes = {staff_id: int(minutes or 0) for staff_id, minutes in overtime_rows}

    captured: dict[int, CapturedWorkingTime] = {}
    for staff_id in sorted(set(staff_ids)):
        values = working_time_at(
            captured_at,
            shifts=shifts.get(staff_id, ()),
            night_shift_ids=night_shift_ids,
            overtime_minutes=overtime_minutes.get(staff_id, 0),
        )
        snapshot = StaffWorkingTimeSnapshot(
            staff_id=staff_id,
            hours_today=_decimal(values.hours_today),
            hours_this_week=_decimal(values.hours_this_week),
            rest_hours=_decimal(values.rest_hours),
            overtime_hours=_decimal(values.overtime_hours),
            consecutive_shifts=values.consecutive_shifts,
            consecutive_night_shifts=values.consecutive_night_shifts,
            captured_at=captured_at,
        )
        db.add(snapshot)
        captured[staff_id] = CapturedWorkingTime(snapshot=snapshot, values=values)
    # The candidate items need the snapshot ids, and SessionLocal has autoflush off
    db.flush()
    return captured


def _decimal(value: Fraction) -> Decimal:
    """Exact when the value has a finite decimal form, else 28 significant digits."""
    return Decimal(value.numerator) / Decimal(value.denominator)
