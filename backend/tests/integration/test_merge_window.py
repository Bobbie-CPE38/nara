"""The merge window of a shift: receiving events and closing the window
(docs/workflow.md, sections 3.1 to 3.6 and 7.3).

The scenarios give a shift a window of 600 seconds, so an event waits as
RECEIVED until the demo clock has moved on and the window is closed.
"""

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingRequirement,
    StaffUnavailability,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AuditAction,
    CaseStatus,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.seed.scenarios import merge_gap, threshold
from app.services import (
    actor_service,
    case_service,
    event_service,
    gap_service,
    merge_window_service,
)
from app.services.event_service import EventOutcome
from app.workflow import orchestrator
from app.workflow.handlers import assess_staffing
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT = 1, 2
HEAD_NURSE = 900
WINDOW = merge_gap.MERGE_WINDOW_SECONDS

# What the steps after the window write is tested with those steps
pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def merging(seeded: Session) -> Session:
    """The Golden Case with a ten minute window on the night shift."""
    merge_gap.seed(seeded)
    return seeded


@pytest.fixture
def overstaffed(seeded: Session) -> Session:
    """The Golden Case plus shift 3, which has more people than its workload needs."""
    threshold.seed(seeded)
    return seeded


def report(
    db: Session,
    staff_id: int,
    *,
    event_type: EventType = EventType.STAFF_UNAVAILABLE,
    shift_id: int = NIGHT_SHIFT,
    **details: Any,
) -> EventOutcome:
    staff = db.get(Staff, staff_id)
    assert staff is not None
    return event_service.receive_event(
        db,
        staff_id=staff_id,
        actor_id=actor_service.user_id(db, staff_id),
        role_id=staff.role_id,
        event_type=event_type,
        shift_id=shift_id,
        **details,
    )


def close_after(db: Session, seconds: int) -> list[merge_window_service.ClosedWindow]:
    clock.advance(timedelta(seconds=seconds))
    return merge_window_service.close_due_windows(db)


def event_row(db: Session, event_id: int) -> StaffingEvent:
    db.expire_all()
    row = db.get(StaffingEvent, event_id)
    assert row is not None
    return row


def roster_status(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> RosterStatus:
    db.expire_all()
    return db.scalars(
        select(RosterAssignment.status).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


def audit(db: Session) -> list[AuditLog]:
    """Every audit row but CASE_STATUS_CHANGED, like section 7.3 lists them."""
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action != AuditAction.CASE_STATUS_CHANGED)
            .order_by(AuditLog.id)
        )
    )


def count(db: Session, model: type) -> int:
    result = db.scalar(select(func.count()).select_from(model))
    assert result is not None
    return result


def required_staff(db: Session, shift_id: int) -> int:
    db.expire_all()
    return db.scalars(
        select(StaffingRequirement.required_staff).where(StaffingRequirement.shift_id == shift_id)
    ).one()


# --------------------------------------------------------------------------- #
# PART A: an event of a shift with a window only waits
# --------------------------------------------------------------------------- #
def test_event_waits_as_received_and_touches_no_other_table(merging: Session) -> None:
    outcome = report(merging, 105)

    assert outcome == EventOutcome(
        event_id=outcome.event_id,
        event_status=EventStatus.RECEIVED,
        case_id=None,
        case_status=None,
        # Round 6 PR EV10: the reporter is told when the window can close
        window_closes_at=DEMO_NOW + timedelta(seconds=WINDOW),
    )
    event = event_row(merging, outcome.event_id)
    assert (event.status, event.processed_at, event.case_id) == (EventStatus.RECEIVED, None, None)
    assert event.occurred_at == DEMO_NOW
    # Q41: the leave and the roster wait for the window to close
    assert roster_status(merging, 105) is RosterStatus.ASSIGNED
    assert count(merging, StaffUnavailability) == 0
    assert count(merging, StaffingCase) == 0
    rows = audit(merging)
    assert [row.action for row in rows] == [AuditAction.EVENT_RECEIVED]
    assert (rows[0].event_id, rows[0].case_id) == (outcome.event_id, None)


def test_waiting_event_is_committed_once(merging: Session) -> None:
    with mock.patch.object(merging, "commit", wraps=merging.commit) as commit:
        report(merging, 105)

    assert commit.call_count == 1


def test_return_time_waits_in_the_payload_until_the_window_closes(merging: Session) -> None:
    """PART B writes the leave, so PART A has to keep what the reporter said."""
    shift = merging.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    back_at = shift.start_at + timedelta(hours=4)

    outcome = report(merging, 105, end_at=back_at)

    assert event_row(merging, outcome.event_id).payload == {"end_at": "2026-10-10T03:00:00+07:00"}
    close_after(merging, WINDOW)
    assert merging.scalars(select(StaffUnavailability.end_at)).one() == back_at


def test_window_does_not_close_before_its_time(merging: Session) -> None:
    outcome = report(merging, 105)

    assert close_after(merging, WINDOW - 1) == []

    assert event_row(merging, outcome.event_id).status is EventStatus.RECEIVED
    assert merge_window_service.find_due_shift_ids(merging) == []
    assert merge_window_service.close_window(merging, NIGHT_SHIFT) is None


def test_window_is_measured_from_its_first_event(merging: Session) -> None:
    """A later event joins the window. It does not restart it."""
    first = report(merging, 104)
    clock.advance(timedelta(seconds=WINDOW - 60))
    second = report(merging, 105)

    closed = close_after(merging, 60)

    assert [window.event_ids for window in closed] == [(first.event_id, second.event_id)]


def test_a_shift_without_waiting_events_has_nothing_to_close(merging: Session) -> None:
    assert close_after(merging, WINDOW) == []
    assert merge_window_service.close_window(merging, NIGHT_SHIFT) is None


# --------------------------------------------------------------------------- #
# Case ต3: two people leave in one window and become one case
# --------------------------------------------------------------------------- #
def test_two_leaves_in_one_window_open_one_case(merging: Session) -> None:
    first = report(merging, 104)
    second = report(merging, 105)

    closed = close_after(merging, WINDOW)

    case = merging.scalars(select(StaffingCase)).one()
    assert closed == [
        merge_window_service.ClosedWindow(
            shift_id=NIGHT_SHIFT,
            event_ids=(first.event_id, second.event_id),
            case_id=case.id,
            case_status=CaseStatus.WAITING_RESPONSE,
        )
    ]
    shift = merging.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert case.required_replacement_time == shift.start_at
    for outcome in (first, second):
        event = event_row(merging, outcome.event_id)
        assert (event.status, event.case_id) == (EventStatus.PROCESSED, case.id)
        # Events of one window share processed_at (section 3.2)
        assert event.processed_at == DEMO_NOW + timedelta(seconds=WINDOW)
    assert roster_status(merging, 104) is RosterStatus.CANCELLED
    assert roster_status(merging, 105) is RosterStatus.CANCELLED
    assert sorted(merging.scalars(select(StaffUnavailability.staff_id))) == [104, 105]


def test_merged_case_audit_follows_section_7_3(merging: Session) -> None:
    first = report(merging, 104)
    second = report(merging, 105)
    close_after(merging, WINDOW)

    rows = audit(merging)
    case = merging.scalars(select(StaffingCase)).one()
    assert [(row.action, row.event_id, row.case_id) for row in rows] == [
        (AuditAction.EVENT_RECEIVED, first.event_id, None),
        (AuditAction.EVENT_RECEIVED, second.event_id, None),
        (AuditAction.UNAVAILABILITY_CREATED, first.event_id, None),
        (AuditAction.UNAVAILABILITY_CREATED, second.event_id, None),
        (AuditAction.CASE_OPENED, None, case.id),
    ]
    # Each leave is written as the person on leave
    assert [rows[index].actor_id for index in (2, 3)] == [
        actor_service.user_id(merging, 104),
        actor_service.user_id(merging, 105),
    ]
    # 10 patients, 5 needed, 3 left. The first event already passed the threshold
    assert rows[-1].payload == {
        "event_id": first.event_id,
        "shift_id": NIGHT_SHIFT,
        "headcount_gap": 2,
    }


def test_merged_case_timeline_shows_its_events_before_case_opened(merging: Session) -> None:
    first = report(merging, 104)
    second = report(merging, 105)
    close_after(merging, WINDOW)
    case = merging.scalars(select(StaffingCase)).one()

    detail = case_service.get_case_detail(merging, case.id)
    timeline = case_service.get_case_timeline(merging, case.id)

    assert detail.event_ids == [first.event_id, second.event_id]
    actions = [
        entry.action for entry in timeline if entry.action != AuditAction.CASE_STATUS_CHANGED
    ]
    assert actions == [
        AuditAction.EVENT_RECEIVED,
        AuditAction.EVENT_RECEIVED,
        AuditAction.UNAVAILABILITY_CREATED,
        AuditAction.UNAVAILABILITY_CREATED,
        AuditAction.CASE_OPENED,
    ]


def test_merged_case_stores_one_gap_of_two_people(
    merging: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real ASSESSING step: the gap is computed once, from both leaves together."""
    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.ASSESSING, assess_staffing.handle)
    report(merging, 104)
    report(merging, 105)

    close_after(merging, WINDOW)

    gap = merging.scalars(select(StaffingGap)).one()
    assert (gap.headcount_gap, gap.effective_minimum) == (2, 5)
    case_gap = gap_service.get_case_gap(merging, gap.case_id)
    assert (case_gap.role_gaps, case_gap.skill_gaps) == ({1: 2}, {})


# --------------------------------------------------------------------------- #
# Q42 and Q44: events of a window that has a case
# --------------------------------------------------------------------------- #
def test_event_below_the_threshold_joins_the_case_of_its_window(seeded: Session) -> None:
    """203 leaves the day shift first: 202 still covers its 2 patients. Then 202 leaves."""
    day_shift = seeded.get(Shift, DAY_SHIFT)
    assert day_shift is not None
    day_shift.merge_window_seconds = WINDOW
    seeded.flush()
    first = report(seeded, 203, shift_id=DAY_SHIFT)
    second = report(seeded, 202, shift_id=DAY_SHIFT)

    close_after(seeded, WINDOW)

    case = seeded.scalars(select(StaffingCase)).one()
    for outcome in (first, second):
        event = event_row(seeded, outcome.event_id)
        assert (event.status, event.case_id) == (EventStatus.PROCESSED, case.id)
    rows = audit(seeded)
    assert AuditAction.EVENT_IGNORED not in [row.action for row in rows]
    # CASE_OPENED names the first event that passed, not the first of the window
    assert rows[-1].payload["event_id"] == second.event_id


def test_second_report_of_the_same_leave_is_ignored_alone(merging: Session) -> None:
    """Q44: both are accepted while the window is open. At the close the second
    one finds no roster row left to cancel."""
    first = report(merging, 105)
    second = report(merging, 105)

    close_after(merging, WINDOW)

    case = merging.scalars(select(StaffingCase)).one()
    kept, dropped = event_row(merging, first.event_id), event_row(merging, second.event_id)
    assert (kept.status, kept.case_id) == (EventStatus.PROCESSED, case.id)
    assert (dropped.status, dropped.case_id) == (EventStatus.IGNORED, None)
    assert dropped.processed_at == kept.processed_at
    assert count(merging, StaffUnavailability) == 1
    rows = audit(merging)
    assert [(row.action, row.event_id) for row in rows] == [
        (AuditAction.EVENT_RECEIVED, first.event_id),
        (AuditAction.EVENT_RECEIVED, second.event_id),
        (AuditAction.UNAVAILABILITY_CREATED, first.event_id),
        (AuditAction.EVENT_IGNORED, second.event_id),
        (AuditAction.CASE_OPENED, None),
    ]
    assert rows[3].payload == {
        "event_id": second.event_id,
        "shift_id": NIGHT_SHIFT,
        "reason": "NO_ASSIGNED_ROSTER",
    }
    assert case_service.get_case_detail(merging, case.id).event_ids == [first.event_id]


# --------------------------------------------------------------------------- #
# Cases ต4 and ต5: windows that end without a case
# --------------------------------------------------------------------------- #
def test_window_where_no_event_passes_ignores_every_event(overstaffed: Session) -> None:
    """ต4: two of three nurses leave. One is enough for 2 patients."""
    first = report(overstaffed, 102, shift_id=threshold.SHIFT_ID)
    second = report(overstaffed, 103, shift_id=threshold.SHIFT_ID)

    closed = close_after(overstaffed, threshold.MERGE_WINDOW_SECONDS)

    assert [(window.case_id, window.event_ids) for window in closed] == [
        (None, (first.event_id, second.event_id))
    ]
    assert count(overstaffed, StaffingCase) == 0
    rows = audit(overstaffed)
    assert [(row.action, row.event_id) for row in rows] == [
        (AuditAction.EVENT_RECEIVED, first.event_id),
        (AuditAction.EVENT_RECEIVED, second.event_id),
        (AuditAction.UNAVAILABILITY_CREATED, first.event_id),
        (AuditAction.UNAVAILABILITY_CREATED, second.event_id),
        (AuditAction.EVENT_IGNORED, first.event_id),
        (AuditAction.EVENT_IGNORED, second.event_id),
    ]
    assert {row.payload["reason"] for row in rows[-2:]} == {"THRESHOLD_NOT_PASSED"}
    for outcome in (first, second):
        event = event_row(overstaffed, outcome.event_id)
        assert (event.status, event.case_id) == (EventStatus.IGNORED, None)
        assert event.processed_at is not None
    # What the events changed stays, although no case was opened
    assert roster_status(overstaffed, 102, threshold.SHIFT_ID) is RosterStatus.CANCELLED
    assert roster_status(overstaffed, 103, threshold.SHIFT_ID) is RosterStatus.CANCELLED
    assert required_staff(overstaffed, threshold.SHIFT_ID) == 1


def test_shift_below_minimum_staff_opens_no_case_while_the_threshold_holds(
    overstaffed: Session,
) -> None:
    """Q32: the floor is 3 and 2 are left, so the gap calculation alone would see
    a shortage. The threshold does not look at the floor, and it decides first."""
    outcome = report(overstaffed, 103, shift_id=threshold.SHIFT_ID)

    close_after(overstaffed, threshold.MERGE_WINDOW_SECONDS)

    shift = overstaffed.get(Shift, threshold.SHIFT_ID)
    assert shift is not None
    assert gap_service.assess_shift(overstaffed, shift).result.headcount_gap == 1
    assert event_row(overstaffed, outcome.event_id).status is EventStatus.IGNORED
    assert count(overstaffed, StaffingCase) == 0


def test_later_event_that_restores_coverage_leaves_no_case(overstaffed: Session) -> None:
    """ต5: 8 patients pass the threshold (8 > 2 * 3). 6 patients are covered again."""
    first = report(
        overstaffed,
        HEAD_NURSE,
        event_type=EventType.PATIENT_SURGE,
        shift_id=threshold.SHIFT_ID,
        patient_count=8,
    )
    second = report(
        overstaffed,
        HEAD_NURSE,
        event_type=EventType.PATIENT_SURGE,
        shift_id=threshold.SHIFT_ID,
        patient_count=6,
    )

    closed = close_after(overstaffed, threshold.MERGE_WINDOW_SECONDS)

    assert [window.case_id for window in closed] == [None]
    assert count(overstaffed, StaffingCase) == 0
    rows = audit(overstaffed)
    assert [(row.action, row.event_id) for row in rows] == [
        (AuditAction.EVENT_RECEIVED, first.event_id),
        (AuditAction.EVENT_RECEIVED, second.event_id),
        (AuditAction.PATIENT_COUNT_UPDATED, first.event_id),
        (AuditAction.PATIENT_COUNT_UPDATED, second.event_id),
        (AuditAction.EVENT_IGNORED, first.event_id),
        (AuditAction.EVENT_IGNORED, second.event_id),
    ]
    assert [
        (row.payload["old_patient_count"], row.payload["new_patient_count"]) for row in rows[2:4]
    ] == [(2, 8), (8, 6)]
    assert {row.payload["reason"] for row in rows[-2:]} == {"NO_GAP"}
    shift = overstaffed.get(Shift, threshold.SHIFT_ID)
    assert shift is not None
    assert shift.patient_count == 6
    # Written once, from the last patient count: ceil(6 / 2), not ceil(8 / 2)
    assert required_staff(overstaffed, threshold.SHIFT_ID) == 3


# --------------------------------------------------------------------------- #
# Q43: one running case per shift
# --------------------------------------------------------------------------- #
def _stop(db: Session, case_id: int, status: CaseStatus) -> None:
    case = db.get(StaffingCase, case_id)
    assert case is not None
    case.status = status
    db.flush()


@pytest.mark.parametrize("ended_as", sorted(AUTOMATION_STOPPED_STATUSES))
def test_event_of_a_shift_whose_case_stopped_opens_a_case_of_its_own(
    merging: Session, ended_as: CaseStatus
) -> None:
    first = report(merging, 105)
    (first_window,) = close_after(merging, WINDOW)
    assert first_window.case_id is not None
    first_event = event_row(merging, first.event_id)
    first_processed_at = first_event.processed_at
    _stop(merging, first_window.case_id, ended_as)

    second = report(merging, 104)
    (second_window,) = close_after(merging, WINDOW)

    # A case of its own, never the stopped case of the window before (Q43)
    assert second_window.event_ids == (second.event_id,)
    assert second_window.case_id not in (None, first_window.case_id)
    assert event_row(merging, second.event_id).case_id == second_window.case_id
    assert roster_status(merging, 104) is RosterStatus.CANCELLED
    # The second close touched only the new event
    first_event = event_row(merging, first.event_id)
    assert (first_event.case_id, first_event.processed_at) == (
        first_window.case_id,
        first_processed_at,
    )
    assert count(merging, StaffingCase) == 2


def test_event_joins_the_case_that_waits_on_its_shift(merging: Session) -> None:
    """Round 6 PR EV10 (6.40): the second leave does not wait for the first case to end."""
    first = report(merging, 105)
    (first_window,) = close_after(merging, WINDOW)
    assert first_window.case_id is not None
    second = report(merging, 104)
    # Its own window still applies: ten minutes after it was reported
    assert close_after(merging, WINDOW - 1) == []
    assert roster_status(merging, 104) is RosterStatus.ASSIGNED
    (second_window,) = close_after(merging, 1)

    assert second_window.event_ids == (second.event_id,)
    assert second_window.case_id == first_window.case_id
    outcome = event_service.get_event(merging, second.event_id)
    assert (outcome.event_status, outcome.case_id, outcome.joined_running_case) == (
        EventStatus.PROCESSED,
        first_window.case_id,
        True,
    )
    assert roster_status(merging, 104) is RosterStatus.CANCELLED
    assert count(merging, StaffingCase) == 1
    # The case measured its gap again from the shift as it is now: 104 and 105 are gone
    gap = gap_service.get_case_gap(merging, first_window.case_id).gap
    shift = merging.get_one(Shift, NIGHT_SHIFT)
    assert gap.headcount_gap == gap_service.assess_shift(merging, shift).result.headcount_gap
    assert gap.headcount_gap >= 2
    assert not event_service.get_event(merging, first.event_id).joined_running_case


def test_second_window_measures_the_gap_of_the_whole_shift(
    merging: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first case ended without a replacement, so the shift is short two people
    when the second window closes: its gap is 2, not the 1 its own event caused."""
    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.ASSESSING, assess_staffing.handle)
    report(merging, 105)
    (first_window,) = close_after(merging, WINDOW)
    assert first_window.case_id is not None
    report(merging, 104)
    _stop(merging, first_window.case_id, CaseStatus.MANUAL_HANDOFF)

    (second_window,) = close_after(merging, WINDOW)

    assert second_window.case_id is not None
    assert gap_service.get_case_gap(merging, second_window.case_id).headcount_gap == 2


def test_window_of_zero_seconds_joins_the_running_case_at_once(seeded: Session) -> None:
    """The Golden Case shift (round 6 PR EV10, 6.40): the second leave is applied at once."""
    first = report(seeded, 105)
    assert (first.event_status, first.case_status) == (
        EventStatus.PROCESSED,
        CaseStatus.WAITING_RESPONSE,
    )
    assert first.case_id is not None

    second = report(seeded, 104)

    assert (second.event_status, second.case_id, second.joined_running_case) == (
        EventStatus.PROCESSED,
        first.case_id,
        True,
    )
    assert roster_status(seeded, 104) is RosterStatus.CANCELLED
    assert count(seeded, StaffingCase) == 1
    assert merge_window_service.close_due_windows(seeded) == []


def test_a_third_leave_joins_the_same_case_too(seeded: Session) -> None:
    first = report(seeded, 105)
    assert first.case_id is not None
    second = report(seeded, 104)
    third = report(seeded, 103)

    assert {second.case_id, third.case_id} == {first.case_id}
    assert third.event_status is EventStatus.PROCESSED
    assert count(seeded, StaffingCase) == 1


def test_each_due_shift_gets_its_own_close(overstaffed: Session) -> None:
    merge_gap.seed(overstaffed)
    night = report(overstaffed, 105)
    evening = report(overstaffed, 103, shift_id=threshold.SHIFT_ID)

    closed = close_after(overstaffed, WINDOW)

    assert [(window.shift_id, window.event_ids) for window in closed] == [
        (NIGHT_SHIFT, (night.event_id,)),
        (threshold.SHIFT_ID, (evening.event_id,)),
    ]
    assert [window.case_id is None for window in closed] == [False, True]


def test_closing_one_shift_leaves_the_window_of_another_open(overstaffed: Session) -> None:
    merge_gap.seed(overstaffed)
    night = report(overstaffed, 105)
    evening = report(overstaffed, 103, shift_id=threshold.SHIFT_ID)
    clock.advance(timedelta(seconds=WINDOW))

    merge_window_service.close_window(overstaffed, NIGHT_SHIFT)

    assert event_row(overstaffed, night.event_id).status is EventStatus.PROCESSED
    assert event_row(overstaffed, evening.event_id).status is EventStatus.RECEIVED
    assert merge_window_service.find_due_shift_ids(overstaffed) == [threshold.SHIFT_ID]


def test_closing_a_window_of_an_unknown_shift_is_an_error(seeded: Session) -> None:
    with pytest.raises(event_service.ShiftNotFoundError):
        merge_window_service.close_window(seeded, 999)
