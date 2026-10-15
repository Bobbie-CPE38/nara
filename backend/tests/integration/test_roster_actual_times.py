"""T2 groundwork; tests write intervals directly until the transfer executor exists."""

from datetime import timedelta

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift
from app.domain.enums import AssignmentType, RosterStatus, ShiftType
from app.services import roster_completion_service, roster_service, working_time_service
from tests.integration.conftest import DEMO_NOW


def pair(db: Session):
    start = DEMO_NOW + timedelta(hours=2)
    shifts = [
        Shift(
            ward_id=1,
            patient_count=2,
            start_at=start,
            end_at=start + timedelta(hours=8),
            shift_type=ShiftType.NIGHT,
            is_active=True,
        )
        for _ in range(2)
    ]
    db.add_all(shifts)
    db.flush()
    source = RosterAssignment(
        staff_id=201,
        shift_id=shifts[0].id,
        status=RosterStatus.COMPLETED,
        assignment_type=AssignmentType.REGULAR,
        actual_end_at=start + timedelta(hours=2),
    )
    db.add(source)
    db.flush()
    destination = RosterAssignment(
        staff_id=201,
        shift_id=shifts[1].id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        actual_start_at=source.actual_end_at,
        transferred_from_assignment_id=source.id,
    )
    db.add(destination)
    db.flush()
    return source, destination, shifts


def test_snapshot_uses_actual_segments_and_counts_a_linked_duty_once(seeded: Session):
    source, destination, shifts = pair(seeded)
    result = working_time_service.capture(
        seeded, [201], captured_at=shifts[0].end_at + timedelta(hours=1)
    )[201].values
    assert result.hours_this_week == 8
    assert result.rest_hours == 1
    assert result.consecutive_shifts == 1
    assert result.consecutive_night_shifts == 1
    assert source.status is RosterStatus.COMPLETED
    assert destination.status is RosterStatus.ASSIGNED


def test_unlinked_adjacent_roster_rows_stay_two_duties(seeded: Session):
    source, destination, shifts = pair(seeded)
    destination.transferred_from_assignment_id = None
    seeded.flush()
    result = working_time_service.capture(
        seeded, [201], captured_at=shifts[0].end_at + timedelta(hours=1)
    )[201].values
    assert result.hours_this_week == 8
    assert result.consecutive_shifts == 2


def test_completion_uses_actual_end_with_null_shift_fallback(seeded: Session):
    source, destination, shifts = pair(seeded)
    source.status = RosterStatus.ASSIGNED
    seeded.flush()
    clock.set_time(source.actual_end_at)
    completed = roster_completion_service.complete_ended_shifts(seeded)
    assert source.id in completed
    assert destination.id not in completed
    assert destination.status is RosterStatus.ASSIGNED


def test_roster_reads_expose_raw_endpoints_and_transfer_link(seeded: Session):
    source, destination, shifts = pair(seeded)
    shift_view = roster_service.get_shift_roster(seeded, shifts[1].id)
    row = shift_view.assignments[0]
    assert row.actual_start_at == destination.actual_start_at
    assert row.actual_end_at is None
    assert row.transferred_from_assignment_id == source.id
    staff_view = roster_service.get_staff_roster(seeded, 201)
    assert [r.transferred_from_assignment_id for r in staff_view.assignments] == [None, source.id]
    assert staff_view.assignments[0].actual_end_at == source.actual_end_at


def test_null_endpoints_preserve_old_roster_times(seeded: Session):
    row = seeded.scalars(select(RosterAssignment).where(RosterAssignment.staff_id == 202)).one()
    assert row.actual_start_at is None and row.actual_end_at is None
    assert (
        working_time_service.capture(seeded, [202], captured_at=DEMO_NOW)[
            202
        ].values.hours_this_week
        == 8
    )


@pytest.mark.parametrize("offset", [0, -1])
def test_actual_endpoint_check_rejects_empty_or_backwards_period(seeded: Session, offset):
    row = seeded.scalars(select(RosterAssignment).where(RosterAssignment.staff_id == 202)).one()
    row.actual_start_at = DEMO_NOW
    row.actual_end_at = DEMO_NOW + timedelta(hours=offset)
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_one_source_cannot_have_two_destinations(seeded: Session):
    source, destination, shifts = pair(seeded)
    seeded.add(
        RosterAssignment(
            staff_id=201,
            shift_id=shifts[1].id,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            transferred_from_assignment_id=source.id,
        )
    )
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_actual_time_columns_are_nullable(seeded: Session):
    columns = {c["name"]: c for c in inspect(seeded.connection()).get_columns("roster_assignment")}
    assert all(
        columns[name]["nullable"]
        for name in ("actual_start_at", "actual_end_at", "transferred_from_assignment_id")
    )


def test_migration_round_trip_preserves_existing_assignments(seeded: Session):
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    from app.seed.reset import ALEMBIC_INI

    connection = seeded.connection()
    migration = (
        ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision("b8d4f1a6c2e9").module
    )
    columns = {"actual_start_at", "actual_end_at", "transferred_from_assignment_id"}
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert not columns & {
            c["name"] for c in inspect(connection).get_columns("roster_assignment")
        }
        migration.upgrade()
    assert columns <= {c["name"] for c in inspect(connection).get_columns("roster_assignment")}
    row = seeded.scalars(select(RosterAssignment).where(RosterAssignment.staff_id == 202)).one()
    seeded.refresh(row)
    assert row.actual_start_at is None and row.actual_end_at is None


def test_leave_flag_uses_the_actual_interval_not_the_whole_shift(seeded: Session):
    from app.db.models import StaffUnavailability
    from app.domain.enums import AvailabilityReason

    source, destination, shifts = pair(seeded)
    seeded.add(
        StaffUnavailability(
            staff_id=201,
            start_at=shifts[0].start_at,
            end_at=source.actual_end_at,
            reason=AvailabilityReason.PLANNED_LEAVE,
        )
    )
    seeded.flush()
    assert (
        roster_service.get_shift_roster(seeded, shifts[1].id).assignments[0].is_unavailable is False
    )
    assert roster_service.get_staff_roster(seeded, 201).assignments[1].is_unavailable is False


def test_linked_duty_crossing_sunday_stays_in_its_originating_week(seeded: Session):
    source, destination, shifts = pair(seeded)
    # Golden clock is Friday; move the example to Sunday 23:00 -> Monday 07:00.
    delta = timedelta(days=2)
    for shift in shifts:
        shift.start_at += delta
        shift.end_at += delta
    source.actual_end_at += delta
    destination.actual_start_at += delta
    seeded.flush()
    sunday = working_time_service.capture(seeded, [201], captured_at=shifts[0].start_at)[201].values
    monday = working_time_service.capture(
        seeded, [201], captured_at=shifts[0].end_at + timedelta(hours=1)
    )[201].values
    assert sunday.hours_this_week == 8
    assert sunday.hours_today == 8
    assert monday.hours_this_week == 0
    assert monday.hours_today == 0
    assert monday.consecutive_shifts == 1
