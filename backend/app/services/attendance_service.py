"""
Check-in of a nurse on an assigned shift (docs/workflow.md, section 6.24).

The pure time rules (required arrival, deadline, accepted window, on time) are
here so the check-in routes, the LINE command and the NO_SHOW job all read the
same ones. check_in() is the one entry point of the routes and owns its audit row
and commit. record() writes the ATTENDANCE row and its ATTENDANCE_CHECKED_IN
audit row without committing; the demo seed calls it too, so every ATTENDANCE row
with a shift_id has exactly one audit row (a repeated check-in reads its roster
row from that audit row).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import CHECK_IN_EARLIEST_SECONDS, NO_SHOW_GRACE_SECONDS
from app.db.models import Attendance, AuditLog, RosterAssignment, Shift
from app.domain.enums import (
    AssignmentType,
    AuditAction,
    CheckInSource,
    EntityType,
    RosterStatus,
)
from app.services import audit_service, merge_window_service, unavailability_service


class CheckInOutsideWindowError(ValueError):
    """A first check-in is before the earliest accepted time or at/after the effective end."""


@dataclass(frozen=True)
class CheckInResult:
    attendance_id: int
    shift_id: int
    check_in_at: datetime
    on_time: bool
    deadline: datetime


def required_arrival_at(roster: RosterAssignment, shift: Shift) -> datetime:
    """When the person must be there: the effective start, or later for a replacement.

    A REPLACEMENT row can be created after the shift started, so it counts from
    max(effective start, created_at). A REGULAR row ignores created_at, because the
    seed creates those rows at reset.
    """
    start = roster.actual_start_at if roster.actual_start_at is not None else shift.start_at
    if roster.assignment_type == AssignmentType.REPLACEMENT:
        return max(start, roster.created_at)
    return start


def deadline_at(roster: RosterAssignment, shift: Shift) -> datetime:
    return required_arrival_at(roster, shift) + timedelta(seconds=NO_SHOW_GRACE_SECONDS)


def effective_end_at(roster: RosterAssignment, shift: Shift) -> datetime:
    return roster.actual_end_at if roster.actual_end_at is not None else shift.end_at


def accepts_check_in(roster: RosterAssignment, shift: Shift, at: datetime) -> bool:
    """Half-open window: arrival - CHECK_IN_EARLIEST_SECONDS <= at < effective end."""
    earliest = required_arrival_at(roster, shift) - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)
    return earliest <= at < effective_end_at(roster, shift)


def is_on_time(roster: RosterAssignment, shift: Shift, check_in_at: datetime) -> bool:
    return check_in_at <= deadline_at(roster, shift)


def check_in(
    db: Session, *, staff_id: int, shift_id: int, source: CheckInSource, actor_id: int
) -> CheckInResult:
    """Record the check-in, or return the one already recorded, then commit.

    Order: lock the SHIFT (404 if missing) → an existing ATTENDANCE row of this
    person in the shift is returned as it is, with no window check, no write and
    no new audit row → lock the person's ASSIGNED roster rows (404) → choose the
    row for the clock, or 422 when none takes it → write → commit. Lock order is SHIFT
    then ROSTER_ASSIGNMENT (workflow.md 6.11). The shift lock also makes two simultaneous
    check-ins of one person run one after the other. On any error the caller must roll back.
    """
    shift = merge_window_service.lock_shift(db, shift_id)

    existing = db.scalar(
        select(Attendance).where(Attendance.staff_id == staff_id, Attendance.shift_id == shift_id)
    )
    if existing is not None:
        result = _existing_result(db, existing, shift)
        db.commit()
        return result

    rows = _lock_assigned_rows(db, staff_id=staff_id, shift_id=shift_id)
    now = clock.now()
    roster = _row_for(rows, shift, now)
    if roster is None:
        # No row takes this moment: say why with the row that comes first in time
        roster = min(rows, key=lambda row: (required_arrival_at(row, shift), row.id))
        earliest = required_arrival_at(roster, shift) - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)
        raise CheckInOutsideWindowError(
            f"Check-in for shift {shift_id} is accepted from {_iso(earliest)}"
            f" until {_iso(effective_end_at(roster, shift))}, not at {_iso(now)}"
        )
    result = record(
        db, roster=roster, shift=shift, check_in_at=now, source=source, actor_id=actor_id
    )
    db.commit()
    return result


def _lock_assigned_rows(db: Session, *, staff_id: int, shift_id: int) -> list[RosterAssignment]:
    """The person's ASSIGNED rows in the shift, locked, in one query ordered by id.

    A person can hold several (T2 allows separate parts of one shift, and a move out
    and back leaves the source prefix ASSIGNED), so this is not lock_assigned_roster(),
    which refuses more than one row.
    """
    rows = list(
        db.scalars(
            select(RosterAssignment)
            .where(
                RosterAssignment.staff_id == staff_id,
                RosterAssignment.shift_id == shift_id,
                RosterAssignment.status == RosterStatus.ASSIGNED,
            )
            .order_by(RosterAssignment.id)
            .with_for_update(key_share=True)
        )
    )
    if not rows:
        raise unavailability_service.NoAssignedRosterError(
            f"Staff {staff_id} has no assigned roster row in shift {shift_id}"
        )
    return rows


def _row_for(rows: list[RosterAssignment], shift: Shift, at: datetime) -> RosterAssignment | None:
    """The row a check-in at `at` belongs to: among the rows whose window takes `at`,
    the one with the earliest required arrival (then the lowest id). None if no row does."""
    taking = [row for row in rows if accepts_check_in(row, shift, at)]
    if not taking:
        return None
    return min(taking, key=lambda row: (required_arrival_at(row, shift), row.id))


def record(
    db: Session,
    *,
    roster: RosterAssignment,
    shift: Shift,
    check_in_at: datetime,
    source: CheckInSource,
    actor_id: int,
) -> CheckInResult:
    """Insert the ATTENDANCE row and its audit row. Flush, never commit, no window check.

    check_out_at and the work and overtime minutes stay NULL: working_time_service
    sums only completed rows, so overtime is not counted twice.
    """
    on_time = is_on_time(roster, shift, check_in_at)
    attendance = Attendance(
        staff_id=roster.staff_id,
        shift_id=shift.id,
        check_in_at=check_in_at,
        synced_at=check_in_at,
    )
    db.add(attendance)
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        actor_id=actor_id,
        action=AuditAction.ATTENDANCE_CHECKED_IN,
        entity_type=EntityType.ATTENDANCE,
        entity_id=attendance.id,
        payload={
            "attendance_id": attendance.id,
            "staff_id": roster.staff_id,
            "shift_id": shift.id,
            "roster_assignment_id": roster.id,
            "check_in_at": _iso(check_in_at),
            "on_time": on_time,
            "source": source.value,
        },
    )
    return CheckInResult(
        attendance_id=attendance.id,
        shift_id=shift.id,
        check_in_at=check_in_at,
        on_time=on_time,
        deadline=deadline_at(roster, shift),
    )


def _existing_result(db: Session, attendance: Attendance, shift: Shift) -> CheckInResult:
    """The answer for a repeated check-in: the row's own time, the roster row of its audit row."""
    roster_id = db.scalar(
        select(AuditLog.payload["roster_assignment_id"].as_integer()).where(
            AuditLog.action == AuditAction.ATTENDANCE_CHECKED_IN,
            AuditLog.entity_type == EntityType.ATTENDANCE,
            AuditLog.entity_id == attendance.id,
        )
    )
    roster = None if roster_id is None else db.get(RosterAssignment, roster_id)
    if roster is None:
        raise RuntimeError(f"Attendance {attendance.id} has no ATTENDANCE_CHECKED_IN audit row")
    return CheckInResult(
        attendance_id=attendance.id,
        shift_id=shift.id,
        check_in_at=attendance.check_in_at,
        on_time=is_on_time(roster, shift, attendance.check_in_at),
        deadline=deadline_at(roster, shift),
    )


def _iso(moment: datetime) -> str:
    """Audit times as +07:00, like UNAVAILABILITY_CREATED."""
    return moment.astimezone(clock.APP_TIMEZONE).isoformat()
