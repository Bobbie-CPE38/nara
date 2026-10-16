"""NO_SHOW stage 2: closing the window records the absence and cancels the row
(docs/workflow.md, section 6.24).

Shift 1 is the ICU night D 23:00 - D+1 07:00 with staff 101-105 REGULAR ASSIGNED. Most
tests give it a window of 600 seconds, so the event of stage 1 waits; the ones that
say "zero window" use the Golden Case as it is. Handlers are stubs: what the case
does after it opens is tested with the workflow.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import StaffingCase, StaffingEvent
from app.domain.enums import (
    ActorName,
    AuditAction,
    AvailabilityReason,
    EventIgnoredReason,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.seed.scenarios import merge_gap
from app.services import (
    actor_service,
    event_service,
    gap_service,
    merge_window_service,
    no_show_service,
    unavailability_service,
    working_time_service,
)
from tests.integration.case_rows import cancel_roster
from tests.integration.no_show_rows import (
    DEADLINE,
    END,
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
    rows_of,
)

pytestmark = pytest.mark.usefixtures("stub_handlers")

SECOND = timedelta(seconds=1)
WINDOW = timedelta(seconds=merge_gap.MERGE_WINDOW_SECONDS)


@pytest.fixture
def merging(seeded: Session) -> Session:
    """The Golden Case with a ten minute window on the night shift."""
    merge_gap.seed(seeded)
    return seeded


def event_row(db: Session, event_id: int) -> StaffingEvent:
    db.expire_all()
    event = db.get(StaffingEvent, event_id)
    assert event is not None
    return event


def waiting_no_show(db: Session, *, missing: tuple[int, ...] = (101,)) -> list[int]:
    """Check in everyone else, let the deadline pass, and run stage 1. The events wait."""
    check_in_everyone(db, except_staff=missing)
    at(DEADLINE + SECOND)
    return no_show_service.detect_due_no_shows(db)


def close_windows(db: Session) -> list[merge_window_service.ClosedWindow]:
    at(DEADLINE + SECOND + WINDOW)
    return merge_window_service.close_due_windows(db)


def count_cases(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(StaffingCase)) or 0


def ignored_reasons(db: Session) -> list[str]:
    return [row.payload["reason"] for row in audit_of(db, AuditAction.EVENT_IGNORED)]


# ---- stage 2 writes the absence ---------------------------------------------------------------


def test_stage_two_records_the_absence_cancels_the_row_and_writes_the_audit_as_system(
    merging: Session,
) -> None:
    [event_id] = waiting_no_show(merging)
    row_id = roster_row(merging, 101).id
    [closed] = close_windows(merging)

    [absence] = absences(merging)
    assert (absence.staff_id, absence.reason) == (101, AvailabilityReason.NO_SHOW)
    assert (absence.start_at, absence.end_at) == (START, END)
    [original] = rows_of(merging, 101)
    assert original.id == row_id and original.status == RosterStatus.CANCELLED
    [audit] = audit_of(merging, AuditAction.UNAVAILABILITY_CREATED)
    assert audit.actor_id == actor_service.component_id(merging, ActorName.SYSTEM)
    assert audit.event_id == event_id and audit.entity_id == absence.id
    assert audit.payload == {
        "unavailability_id": absence.id,
        "staff_id": 101,
        "reason": "NO_SHOW",
        "start_at": START.isoformat(),
        "end_at": END.isoformat(),
    }
    # 4 of 5 people are on the shift: the event counts, a case opens
    event = event_row(merging, event_id)
    assert event.status == EventStatus.PROCESSED
    assert event.case_id == closed.case_id is not None


def test_a_leave_event_without_a_reason_still_goes_through_the_leave_path(
    merging: Session,
) -> None:
    check_in_everyone(merging)
    event_service.receive_event(
        merging,
        staff_id=105,
        actor_id=actor_service.user_id(merging, 105),
        role_id=1,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
    )
    close_windows(merging)

    [absence] = absences(merging)
    assert absence.reason == AvailabilityReason.UNPLANNED_LEAVE
    [audit] = audit_of(merging, AuditAction.UNAVAILABILITY_CREATED)
    assert audit.actor_id == actor_service.user_id(merging, 105)


def test_two_no_shows_of_one_shift_join_one_window_and_one_case(seeded: Session) -> None:
    """Zero window: stage 1 writes both events in one transaction, then closes once."""
    check_in_everyone(seeded, except_staff=(101, 102))
    at(DEADLINE + SECOND)
    event_ids = no_show_service.detect_due_no_shows(seeded)

    assert len(event_ids) == 2
    events = [event_row(seeded, event_id) for event_id in event_ids]
    assert {event.status for event in events} == {EventStatus.PROCESSED}
    assert len({event.case_id for event in events}) == 1 and events[0].case_id is not None
    assert count_cases(seeded) == 1
    assert len(absences(seeded)) == 2


# ---- the row changed while the event waited ---------------------------------------------------


def test_a_row_cancelled_while_the_event_waits_is_ignored(merging: Session) -> None:
    [event_id] = waiting_no_show(merging)
    cancel_roster(merging, 101)
    close_windows(merging)

    assert event_row(merging, event_id).status == EventStatus.IGNORED
    assert ignored_reasons(merging) == [EventIgnoredReason.NO_ASSIGNED_ROSTER.value]
    assert absences(merging) == []
    assert count_cases(merging) == 0


def test_a_mid_shift_move_source_that_is_still_assigned_is_not_cancelled(
    merging: Session,
) -> None:
    [event_id] = waiting_no_show(merging)
    later = add_shift(merging, start_at=START + timedelta(hours=2), end_at=END + timedelta(days=1))
    # The person was moved out after the event: the source stays ASSIGNED
    add_row(merging, 101, later, transferred_from=roster_row(merging, 101))
    close_windows(merging)

    assert event_row(merging, event_id).status == EventStatus.IGNORED
    assert ignored_reasons(merging) == [EventIgnoredReason.NO_ASSIGNED_ROSTER.value]
    assert roster_row(merging, 101).status == RosterStatus.ASSIGNED
    assert absences(merging) == []


# ---- the shift ended while the event waited ---------------------------------------------------


def _ended_while_waiting(db: Session) -> int:
    """Stage 1 one minute before the end of the shift; its window closes after the end."""
    check_in_everyone(db, except_staff=(101,))
    at(END - timedelta(minutes=1))
    [event_id] = no_show_service.detect_due_no_shows(db)
    return event_id


def _close_after_the_end(db: Session) -> list[merge_window_service.ClosedWindow]:
    at(END + WINDOW)
    return merge_window_service.close_due_windows(db)


def test_a_window_closing_after_the_shift_ended_records_history_and_opens_no_case(
    merging: Session,
) -> None:
    event_id = _ended_while_waiting(merging)
    [closed] = _close_after_the_end(merging)

    [absence] = absences(merging)
    assert (absence.reason, absence.start_at, absence.end_at) == (
        AvailabilityReason.NO_SHOW,
        START,
        END,
    )
    [row] = rows_of(merging, 101)
    assert row.status == RosterStatus.CANCELLED
    assert closed.case_id is None and count_cases(merging) == 0
    assert event_row(merging, event_id).status == EventStatus.IGNORED
    assert ignored_reasons(merging) == [EventIgnoredReason.SHIFT_ENDED.value]
    assert len(audit_of(merging, AuditAction.UNAVAILABILITY_CREATED)) == 1


def test_a_late_check_in_while_the_event_waits_restores_the_row_and_opens_no_case(
    merging: Session,
) -> None:
    event_id = _ended_while_waiting(merging)
    arrived = END - timedelta(seconds=30)
    check_in(merging, roster_row(merging, 101), check_in_at=arrived)
    _close_after_the_end(merging)

    original, restored = rows_of(merging, 101)
    assert original.status == RosterStatus.CANCELLED
    assert restored.status == RosterStatus.ASSIGNED
    assert (restored.actual_start_at, restored.actual_end_at) == (arrived, original.actual_end_at)
    [absence] = absences(merging)
    assert (absence.start_at, absence.end_at) == (START, arrived)
    assert count_cases(merging) == 0
    assert event_row(merging, event_id).status == EventStatus.IGNORED
    assert ignored_reasons(merging) == [EventIgnoredReason.SHIFT_ENDED.value]


def test_an_event_that_only_records_history_joins_the_case_another_event_opens(
    merging: Session,
) -> None:
    no_show_id = _ended_while_waiting(merging)
    # A leave of 105 on the same window: with 101 also gone the shift is under its minimum
    outcome = event_service.receive_event(
        merging,
        staff_id=105,
        actor_id=actor_service.user_id(merging, 105),
        role_id=1,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
    )
    [closed] = _close_after_the_end(merging)

    assert closed.case_id is not None
    for event_id in (no_show_id, outcome.event_id):
        event = event_row(merging, event_id)
        assert (event.status, event.case_id) == (EventStatus.PROCESSED, closed.case_id)


# ---- a late check-in before stage 2 -----------------------------------------------------------


def test_a_late_check_in_before_the_next_job_run_still_writes_the_event_and_stage_two_restores(
    seeded: Session,
) -> None:
    """Zero window: one job call writes the event and closes the window."""
    check_in_everyone(seeded, except_staff=(101,))
    arrived = START + timedelta(minutes=20)
    at(arrived)
    check_in(seeded, roster_row(seeded, 101), check_in_at=arrived)

    [event_id] = no_show_service.detect_due_no_shows(seeded)

    assert [event.id for event in no_show_events(seeded)] == [event_id]
    original, restored = rows_of(seeded, 101)
    assert original.status == RosterStatus.CANCELLED
    assert (restored.status, restored.actual_start_at) == (RosterStatus.ASSIGNED, arrived)
    [absence] = absences(seeded)
    assert (absence.start_at, absence.end_at) == (START, arrived)
    # The restored person fills the seat again, so the shift passes the threshold
    assert event_row(seeded, event_id).status == EventStatus.IGNORED
    assert ignored_reasons(seeded) == [EventIgnoredReason.THRESHOLD_NOT_PASSED.value]
    assert count_cases(seeded) == 0


def test_hours_and_the_gap_use_the_actual_arrival_time(seeded: Session) -> None:
    check_in_everyone(seeded, except_staff=(101,))
    arrived = START + timedelta(minutes=20)
    at(arrived)
    check_in(seeded, roster_row(seeded, 101), check_in_at=arrived)
    no_show_service.detect_due_no_shows(seeded)

    captured = working_time_service.capture(seeded, [101, 102], captured_at=END)
    missed = captured[102].values.hours_this_week - captured[101].values.hours_this_week
    assert float(missed) == pytest.approx(20 / 60)

    shift = merge_window_service.lock_shift(seeded, NIGHT_SHIFT)
    assert not gap_service.assess_shift(seeded, shift).result.has_gap


def test_a_restored_row_is_not_checked_again_by_the_next_job_run(seeded: Session) -> None:
    check_in_everyone(seeded, except_staff=(101,))
    arrived = START + timedelta(minutes=20)
    at(arrived)
    check_in(seeded, roster_row(seeded, 101), check_in_at=arrived)
    no_show_service.detect_due_no_shows(seeded)

    at(END - SECOND)
    assert no_show_service.detect_due_no_shows(seeded) == []
    assert len(no_show_events(seeded)) == 1


# ---- several shifts in a row ------------------------------------------------------------------


def test_a_person_who_is_late_in_two_shifts_in_a_row_gets_a_new_row_in_each(
    merging: Session,
) -> None:
    second = add_shift(
        merging,
        start_at=END,
        end_at=END + timedelta(hours=8),
        merge_window_seconds=merge_gap.MERGE_WINDOW_SECONDS,
    )
    add_row(merging, 101, second)
    check_in_everyone(merging, except_staff=(101,))

    for shift_id, shift_start in ((NIGHT_SHIFT, START), (second.id, END)):
        at(shift_start + timedelta(minutes=16))
        assert len(no_show_service.detect_due_no_shows(merging)) == 1
        arrived = shift_start + timedelta(minutes=20)
        check_in(merging, roster_row(merging, 101, shift_id), check_in_at=arrived)
        at(shift_start + timedelta(minutes=30))
        merge_window_service.close_due_windows(merging)

        original, restored = rows_of(merging, 101, shift_id)
        assert (original.status, restored.status) == (RosterStatus.CANCELLED, RosterStatus.ASSIGNED)
        assert restored.actual_start_at == arrived

    assert [absence.reason for absence in absences(merging)] == [AvailabilityReason.NO_SHOW] * 2


# ---- a leave reported after the NO_SHOW -------------------------------------------------------


def test_a_leave_reported_after_stage_two_is_refused_and_the_reason_stays_no_show(
    merging: Session,
) -> None:
    waiting_no_show(merging)
    close_windows(merging)

    with pytest.raises(unavailability_service.NoAssignedRosterError):
        event_service.receive_event(
            merging,
            staff_id=101,
            actor_id=actor_service.user_id(merging, 101),
            role_id=1,
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=NIGHT_SHIFT,
        )
    merging.rollback()
    assert [absence.reason for absence in absences(merging)] == [AvailabilityReason.NO_SHOW]


def test_a_leave_reported_while_the_no_show_waits_is_ignored_and_the_reason_stays_no_show(
    merging: Session,
) -> None:
    [no_show_id] = waiting_no_show(merging)
    at(DEADLINE + timedelta(seconds=2))
    leave = event_service.receive_event(
        merging,
        staff_id=101,
        actor_id=actor_service.user_id(merging, 101),
        role_id=1,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
    )
    close_windows(merging)

    assert event_row(merging, leave.event_id).status == EventStatus.IGNORED
    assert event_row(merging, no_show_id).status == EventStatus.PROCESSED
    assert ignored_reasons(merging) == [EventIgnoredReason.NO_ASSIGNED_ROSTER.value]
    assert [absence.reason for absence in absences(merging)] == [AvailabilityReason.NO_SHOW]
