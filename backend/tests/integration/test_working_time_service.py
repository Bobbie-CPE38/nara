"""working_time_service against the seeded PostgreSQL (round 1 contract, section 8.3)."""

from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Attendance, RosterAssignment, StaffWorkingTimeSnapshot
from app.domain.enums import RosterStatus
from app.services import working_time_service
from tests.integration.conftest import DEMO_NOW


def _count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(StaffWorkingTimeSnapshot)) or 0


def _attendance(
    staff_id: int, *, check_in_at, work_minutes: int | None, overtime_minutes: int | None
) -> Attendance:
    return Attendance(
        staff_id=staff_id,
        check_in_at=check_in_at,
        check_out_at=None if work_minutes is None else check_in_at + timedelta(hours=9),
        work_minutes=work_minutes,
        overtime_minutes=overtime_minutes,
        synced_at=DEMO_NOW,
    )


def test_golden_case_values(seeded: Session) -> None:
    result = working_time_service.capture(seeded, [201, 202, 101], captured_at=DEMO_NOW)
    seeded.expire_all()

    assert set(result) == {201, 202, 101}
    free = result[201].snapshot
    assert (free.hours_today, free.hours_this_week, free.rest_hours, free.overtime_hours) == (
        0,
        0,
        0,
        0,
    )
    assert result[202].snapshot.hours_this_week == 8
    assert result[202].snapshot.hours_today == 0
    on_night = result[101].snapshot
    # Shift 1 starts tonight at 23:00 and has not started at 21:00
    assert (on_night.hours_today, on_night.hours_this_week) == (8, 8)
    assert (on_night.rest_hours, on_night.consecutive_shifts) == (0, 0)
    assert all(row.snapshot.captured_at == DEMO_NOW for row in result.values())


def test_every_call_writes_new_rows(seeded: Session) -> None:
    first = working_time_service.capture(seeded, [201], captured_at=DEMO_NOW)
    second = working_time_service.capture(seeded, [201], captured_at=DEMO_NOW)

    assert first[201].snapshot.id != second[201].snapshot.id
    assert _count(seeded) == 2


def test_only_summarised_attendance_of_the_week_counts_as_overtime(seeded: Session) -> None:
    seeded.add_all(
        [
            _attendance(
                201,
                check_in_at=DEMO_NOW - timedelta(hours=12),
                work_minutes=540,
                overtime_minutes=120,
            ),
            _attendance(
                201,
                check_in_at=DEMO_NOW - timedelta(hours=20),
                work_minutes=None,
                overtime_minutes=None,
            ),
            _attendance(
                201,
                check_in_at=DEMO_NOW - timedelta(days=8),
                work_minutes=540,
                overtime_minutes=300,
            ),
        ]
    )
    seeded.flush()

    result = working_time_service.capture(seeded, [201], captured_at=DEMO_NOW)

    assert result[201].values.overtime_hours == 2


def test_a_cancelled_roster_row_does_not_count(seeded: Session) -> None:
    row = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 202, RosterAssignment.shift_id == 2
        )
    ).one()
    row.status = RosterStatus.CANCELLED
    seeded.flush()

    result = working_time_service.capture(seeded, [202], captured_at=DEMO_NOW)

    assert result[202].values.hours_this_week == 0


def test_an_empty_list_writes_nothing(seeded: Session) -> None:
    assert working_time_service.capture(seeded, [], captured_at=DEMO_NOW) == {}
    assert _count(seeded) == 0


def test_capture_never_commits(production_seeded: Session) -> None:
    with patch.object(production_seeded, "commit", side_effect=AssertionError("committed")):
        working_time_service.capture(production_seeded, [201], captured_at=DEMO_NOW)
