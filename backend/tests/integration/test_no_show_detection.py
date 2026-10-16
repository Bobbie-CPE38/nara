"""NO_SHOW stage 1: the job finds a person who did not come and writes only an event
(docs/workflow.md, section 6.24 and the silent-failure table of "สถานะของรอบ 5").

Shift 1 is the ICU night D 23:00 - D+1 07:00 with staff 101-105 REGULAR ASSIGNED and a
merge window of 600 seconds here, so the event written by the job stays RECEIVED.
Shift 2 is the day shift two days later with 202 and 203. The clock is frozen.
"""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Attendance,
    AuditLog,
    RosterAssignment,
    Shift,
    StaffingEvent,
    StaffUnavailability,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    AvailabilityReason,
    CheckInSource,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.seed import load
from app.seed.scenarios import merge_gap
from app.services import (
    actor_service,
    attendance_service,
    event_service,
    late_arrival_service,
    no_show_service,
)
from tests.integration.case_rows import cancel_roster
from tests.integration.conftest import DEMO_NOW
from tests.integration.no_show_rows import (
    DAY_SHIFT,
    DEADLINE,
    END,
    GRACE,
    NIGHT_SHIFT,
    START,
    absences,
    add_row,
    add_shift,
    at,
    audit_of,
    check_in,
    check_in_everyone,
    no_show_events,
    roster_row,
)

pytestmark = pytest.mark.usefixtures("stub_handlers")

SECOND = timedelta(seconds=1)
DAY_START = DEMO_NOW.replace(hour=7) + timedelta(days=2)  # shift 2 starts


@pytest.fixture
def merging(seeded: Session) -> Session:
    """The Golden Case with a ten minute window on the night shift."""
    merge_gap.seed(seeded)
    return seeded


def detect(db: Session) -> list[int]:
    return no_show_service.detect_due_no_shows(db)


def only_101_is_missing(db: Session) -> None:
    check_in_everyone(db, except_staff=(101,))


# ---- the deadline ------------------------------------------------------------------------------


def test_check_in_exactly_at_the_deadline_is_on_time(merging: Session) -> None:
    at(DEADLINE)
    result = attendance_service.check_in(
        merging,
        staff_id=101,
        shift_id=NIGHT_SHIFT,
        source=CheckInSource.SELF,
        actor_id=actor_service.user_id(merging, 101),
    )
    assert result.on_time is True and result.check_in_at == DEADLINE

    check_in_everyone(merging, except_staff=(101,))
    at(DEADLINE + SECOND)
    assert detect(merging) == []


def test_the_job_at_the_deadline_writes_nothing_and_a_second_later_one_event(
    merging: Session,
) -> None:
    only_101_is_missing(merging)

    at(DEADLINE)
    assert detect(merging) == []
    assert no_show_events(merging) == []

    at(DEADLINE + SECOND)
    event_ids = detect(merging)
    [event] = no_show_events(merging)
    assert event_ids == [event.id]
    assert event.staff_id == 101
    assert event.status == EventStatus.RECEIVED
    assert event.payload == {
        "reason": "NO_SHOW",
        "roster_assignment_id": roster_row(merging, 101).id,
    }


def test_a_seeded_regular_row_has_its_deadline_at_the_shift_start_plus_15_minutes(
    merging: Session,
) -> None:
    row = roster_row(merging, 101)
    shift = merging.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    # The seed created the row at reset (D 21:00): created_at must not move the deadline
    assert row.created_at == DEMO_NOW
    assert attendance_service.deadline_at(row, shift) == START + GRACE

    at(START + GRACE - SECOND)
    assert detect(merging) == []
    at(START + GRACE + SECOND)
    detect(merging)
    assert sorted(
        event.staff_id or 0 for event in no_show_events(merging) if event.shift_id == NIGHT_SHIFT
    ) == [101, 102, 103, 104, 105]


# ---- stage 1 writes only the event ------------------------------------------------------------


def test_stage_one_writes_only_the_event_and_its_received_audit_row(merging: Session) -> None:
    only_101_is_missing(merging)
    at(DEADLINE + SECOND)
    [event_id] = detect(merging)

    assert absences(merging) == []
    assert roster_row(merging, 101).status == RosterStatus.ASSIGNED
    assert audit_of(merging, AuditAction.UNAVAILABILITY_CREATED) == []
    [received] = audit_of(merging, AuditAction.EVENT_RECEIVED)
    assert received.event_id == event_id
    assert received.actor_id == actor_service.component_id(merging, ActorName.SYSTEM)
    assert received.payload == {
        "event_type": "STAFF_UNAVAILABLE",
        "shift_id": NIGHT_SHIFT,
        "staff_id": 101,
    }


def test_two_job_runs_while_the_window_is_open_write_one_event(merging: Session) -> None:
    only_101_is_missing(merging)
    at(DEADLINE + SECOND)
    first = detect(merging)
    at(DEADLINE + timedelta(minutes=5))
    second = detect(merging)

    assert len(first) == 1 and second == []
    assert len(no_show_events(merging)) == 1


# ---- who is not a NO_SHOW ---------------------------------------------------------------------


def test_a_person_with_an_overlapping_leave_period_is_not_a_no_show(merging: Session) -> None:
    only_101_is_missing(merging)
    merging.add(
        StaffUnavailability(
            staff_id=101, start_at=START, end_at=END, reason=AvailabilityReason.PLANNED_LEAVE
        )
    )
    merging.flush()
    at(DEADLINE + SECOND)
    assert detect(merging) == []


def test_a_person_with_a_leave_waiting_for_its_window_is_not_a_no_show(merging: Session) -> None:
    only_101_is_missing(merging)
    at(START)
    event_service.receive_event(
        merging,
        staff_id=101,
        actor_id=actor_service.user_id(merging, 101),
        role_id=1,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
    )
    at(DEADLINE + SECOND)
    assert detect(merging) == []


def test_a_person_with_a_cancellation_waiting_for_its_window_is_not_a_no_show(
    merging: Session,
) -> None:
    only_101_is_missing(merging)
    at(START)
    event_service.receive_event(
        merging,
        staff_id=900,
        actor_id=actor_service.user_id(merging, 900),
        role_id=2,
        event_type=EventType.ASSIGNMENT_CANCELLED,
        shift_id=NIGHT_SHIFT,
        target_staff_id=101,
        reason="Moved to another ward",
    )
    at(DEADLINE + SECOND)
    assert detect(merging) == []


def test_a_person_moved_out_of_the_row_mid_shift_is_not_a_no_show(merging: Session) -> None:
    only_101_is_missing(merging)
    later = add_shift(merging, start_at=START + timedelta(hours=2), end_at=END + timedelta(days=1))
    # The source of a mid-shift move stays ASSIGNED; the destination points back to it
    add_row(merging, 101, later, transferred_from=roster_row(merging, 101))
    at(DEADLINE + SECOND)
    assert detect(merging) == []


@pytest.mark.parametrize("status", [RosterStatus.CANCELLED, RosterStatus.COMPLETED])
def test_a_row_that_is_not_assigned_is_not_checked(merging: Session, status: RosterStatus) -> None:
    only_101_is_missing(merging)
    roster_row(merging, 101).status = status
    merging.flush()
    at(DEADLINE + SECOND)
    assert detect(merging) == []


def test_a_row_is_checked_only_while_the_shift_runs(merging: Session) -> None:
    only_101_is_missing(merging)
    at(END - SECOND)
    assert len(detect(merging)) == 1

    at(END)
    assert detect(merging) == []


def test_an_event_of_another_person_does_not_hide_a_no_show(merging: Session) -> None:
    check_in_everyone(merging, except_staff=(101, 102))
    at(START)
    event_service.receive_event(
        merging,
        staff_id=102,
        actor_id=actor_service.user_id(merging, 102),
        role_id=1,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
    )
    at(DEADLINE + SECOND)
    detect(merging)
    assert [event.staff_id for event in no_show_events(merging)] == [101]


# ---- replacements count from max(start, created_at) -------------------------------------------


def _replacement(db: Session, *, arrives_at: datetime, assigned_at: datetime) -> RosterAssignment:
    shift = db.get(Shift, DAY_SHIFT)
    assert shift is not None
    check_in_everyone(db)
    return add_row(
        db,
        201,
        shift,
        assignment_type=AssignmentType.REPLACEMENT,
        actual_start_at=arrives_at,
        created_at=assigned_at,
    )


def test_a_replacement_assigned_at_0750_for_0800_checks_in_at_0800_and_is_no_show_after_0815(
    seeded: Session,
) -> None:
    eight = DAY_START + timedelta(hours=1)
    row = _replacement(seeded, arrives_at=eight, assigned_at=eight - timedelta(minutes=10))

    at(eight + GRACE)
    assert detect(seeded) == []
    at(eight + GRACE + SECOND)
    [event_id] = detect(seeded)
    [event] = no_show_events(seeded)
    assert event.id == event_id and event.staff_id == 201
    assert event.payload["roster_assignment_id"] == row.id


def test_a_replacement_who_checks_in_at_0800_is_never_a_no_show(seeded: Session) -> None:
    eight = DAY_START + timedelta(hours=1)
    row = _replacement(seeded, arrives_at=eight, assigned_at=eight - timedelta(minutes=10))
    check_in(seeded, row, check_in_at=eight)

    at(eight + GRACE + timedelta(hours=1))
    assert detect(seeded) == []


def test_a_replacement_assigned_after_the_start_counts_from_the_assignment(
    seeded: Session,
) -> None:
    eight = DAY_START + timedelta(hours=1)
    assigned = eight + timedelta(minutes=10)
    _replacement(seeded, arrives_at=eight, assigned_at=assigned)

    # Past 08:15, but the person was only asked at 08:10: the deadline is 08:25
    at(eight + timedelta(minutes=20))
    assert detect(seeded) == []
    at(assigned + GRACE)
    assert detect(seeded) == []
    at(assigned + GRACE + SECOND)
    assert len(detect(seeded)) == 1


# ---- the chain of moves -----------------------------------------------------------------------


def _chain(db: Session) -> tuple[RosterAssignment, RosterAssignment, RosterAssignment]:
    """Person 201: X on the day shift, moved to Y (another shift), moved to Z on the night shift.

    Moves before a row started cancel the source, so X and Y are CANCELLED history.
    """
    check_in_everyone(db)
    day = db.get(Shift, DAY_SHIFT)
    middle = add_shift(db, start_at=START + timedelta(days=1), end_at=END + timedelta(days=1))
    night = db.get(Shift, NIGHT_SHIFT)
    assert day is not None and night is not None
    first = add_row(db, 201, day, status=RosterStatus.CANCELLED)
    second = add_row(db, 201, middle, status=RosterStatus.CANCELLED, transferred_from=first)
    third = add_row(db, 201, night, transferred_from=second)
    return first, second, third


def test_an_on_time_check_in_at_the_start_of_the_chain_exempts_the_destination(
    merging: Session,
) -> None:
    first, _, third = _chain(merging)
    check_in(merging, first)
    at(DEADLINE + SECOND)
    assert detect(merging) == []
    assert no_show_service.has_on_time_check_in(merging, third)


def test_an_on_time_check_in_in_the_middle_of_the_chain_exempts_the_destination(
    merging: Session,
) -> None:
    _, second, third = _chain(merging)
    check_in(merging, second)
    at(DEADLINE + SECOND)
    assert detect(merging) == []
    assert no_show_service.has_on_time_check_in(merging, third)


def test_a_chain_with_no_on_time_check_in_makes_the_destination_a_no_show(
    merging: Session,
) -> None:
    first, _, third = _chain(merging)
    # A late check-in at the source does not count
    check_in(merging, first, check_in_at=DAY_START + GRACE + SECOND)
    at(DEADLINE + SECOND)
    detect(merging)
    [event] = no_show_events(merging)
    assert (event.staff_id, event.payload["roster_assignment_id"]) == (201, third.id)


def test_a_whole_shift_move_before_the_source_started_with_no_check_in_is_a_no_show(
    merging: Session,
) -> None:
    _, _, third = _chain(merging)
    at(DEADLINE + SECOND)
    detect(merging)
    assert [event.payload["roster_assignment_id"] for event in no_show_events(merging)] == [
        third.id
    ]


def test_a_loop_in_the_chain_ends_the_walk(merging: Session) -> None:
    first, _, third = _chain(merging)
    first.transferred_from_assignment_id = third.id
    merging.flush()
    assert no_show_service.has_on_time_check_in(merging, third) is False


# ---- a restored row is never checked again ----------------------------------------------------


def test_a_row_restored_after_a_late_arrival_is_never_a_no_show(merging: Session) -> None:
    only_101_is_missing(merging)
    original = roster_row(merging, 101)
    arrived = START + timedelta(minutes=20)
    check_in(merging, original, check_in_at=arrived)
    original.status = RosterStatus.CANCELLED
    merging.flush()
    restored = late_arrival_service.restore(merging, original=original, check_in_at=arrived)
    assert restored.actual_start_at == arrived

    for later in (arrived + GRACE + SECOND, START + timedelta(hours=3), END - SECOND):
        at(later)
        assert detect(merging) == []
    assert no_show_events(merging) == []


# ---- two connections --------------------------------------------------------------------------


@pytest.fixture
def committed_scene(frozen_clock: datetime) -> Iterator[None]:
    """The Golden Case committed (zero window): 102-105 are checked in, 101 is not."""
    with SessionLocal.begin() as db:
        load(db)
        check_in_everyone(db, except_staff=(101,))
    try:
        yield
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_two_job_connections_at_once_write_one_event_and_one_no_show(
    committed_scene: None,
) -> None:
    at(DEADLINE + SECOND)
    barrier = threading.Barrier(2, timeout=10)
    written: list[list[int]] = []
    errors: list[Exception] = []

    def job() -> None:
        try:
            with SessionLocal() as db:
                barrier.wait()
                written.append(no_show_service.detect_due_no_shows(db))
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=job) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(len(ids) for ids in written) == [0, 1]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StaffingEvent)) == 1
        absence = db.scalars(select(StaffUnavailability)).one()
        assert (absence.staff_id, absence.reason) == (101, AvailabilityReason.NO_SHOW)
        statuses = db.scalars(
            select(RosterAssignment.status).where(RosterAssignment.staff_id == 101)
        ).all()
        assert list(statuses) == [RosterStatus.CANCELLED]
        checked_in = db.scalar(
            select(func.count()).select_from(Attendance).where(Attendance.shift_id == NIGHT_SHIFT)
        )
        assert checked_in == 4
        unavailable_audits = db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.UNAVAILABILITY_CREATED)
        )
        assert unavailable_audits == 1


def test_a_second_job_run_after_the_no_show_was_recorded_finds_nothing(
    committed_scene: None,
) -> None:
    at(DEADLINE + SECOND)
    with SessionLocal() as db:
        assert len(no_show_service.detect_due_no_shows(db)) == 1
    with SessionLocal() as db:
        assert no_show_service.detect_due_no_shows(db) == []


def test_an_unchecked_row_is_left_alone_when_its_row_was_cancelled_first(
    merging: Session,
) -> None:
    only_101_is_missing(merging)
    cancel_roster(merging, 101)
    at(DEADLINE + SECOND)
    assert detect(merging) == []
