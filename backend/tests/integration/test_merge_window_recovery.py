"""Merge windows on real connections: a close that fails, and requests that
arrive while a close is running (docs/workflow.md, section 3.2).

Section 3.2 gives three reasons why a new window never mixes with an old one,
and asks for tests of them:

  1. A close changes all its events in one transaction. If it fails, all of
     them are still RECEIVED.
  2. Receiving an event and closing a window take the same shift lock.
  3. A status never goes back to RECEIVED.

These tests commit for real, because a rollback and a lock wait cannot be seen
inside the single transaction the other tests share.
"""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.base import Base
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingRequirement,
    StaffUnavailability,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    AuditAction,
    CaseStatus,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.main import app
from app.seed import load
from app.seed.scenarios import merge_gap, threshold
from app.services import (
    actor_service,
    event_service,
    gap_service,
    merge_window_service,
    unavailability_service,
)
from app.services.merge_window_service import ClosedWindow

NIGHT_SHIFT = 1
WINDOW = merge_gap.MERGE_WINDOW_SECONDS

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def committed_scenarios(frozen_clock: datetime) -> Iterator[None]:
    """The Golden Case with both window scenarios, committed so every connection sees it."""
    with SessionLocal.begin() as db:
        load(db)
        merge_gap.seed(db)
        threshold.seed(db)
    try:
        yield
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def report(staff_id: int, shift_id: int = NIGHT_SHIFT) -> int:
    """Report a leave in its own session, like one request. Returns the event ID."""
    with SessionLocal() as db:
        staff = db.get(Staff, staff_id)
        assert staff is not None
        return event_service.receive_event(
            db,
            staff_id=staff_id,
            actor_id=actor_service.user_id(db, staff_id),
            role_id=staff.role_id,
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=shift_id,
        ).event_id


def close_due() -> list[ClosedWindow]:
    with SessionLocal() as db:
        return merge_window_service.close_due_windows(db)


def events() -> dict[int, tuple[EventStatus, datetime | None, int | None]]:
    with SessionLocal() as db:
        return {
            row.id: (row.status, row.processed_at, row.case_id)
            for row in db.scalars(select(StaffingEvent).order_by(StaffingEvent.id))
        }


def assigned(shift_id: int = NIGHT_SHIFT) -> set[int]:
    with SessionLocal() as db:
        return set(
            db.scalars(
                select(RosterAssignment.staff_id).where(
                    RosterAssignment.shift_id == shift_id,
                    RosterAssignment.status == RosterStatus.ASSIGNED,
                )
            )
        )


def count(model: type) -> int:
    with SessionLocal() as db:
        result = db.scalar(select(func.count()).select_from(model))
        assert result is not None
        return result


def audit_actions() -> list[AuditAction]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AuditLog.action)
                .where(AuditLog.action != AuditAction.CASE_STATUS_CHANGED)
                .order_by(AuditLog.id)
            )
        )


# --------------------------------------------------------------------------- #
# 1. A close that fails stores nothing, and the next try closes the window
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fails_at", ["second_event", "gap_check"])
def test_close_that_fails_midway_leaves_every_event_received(
    committed_scenarios: None, monkeypatch: pytest.MonkeyPatch, fails_at: str
) -> None:
    """By the time it fails, the close has already cancelled a roster row,
    written a leave and an audit row for the first event."""
    first, second = report(104), report(105)
    clock.advance(timedelta(seconds=WINDOW))

    with monkeypatch.context() as patch:
        if fails_at == "second_event":
            real_record = unavailability_service.record_unplanned_leave

            def record_first_only(db: Session, **kwargs: Any) -> StaffUnavailability:
                if kwargs["roster"].staff_id == 105:
                    raise RuntimeError("database went away")
                return real_record(db, **kwargs)

            patch.setattr(unavailability_service, "record_unplanned_leave", record_first_only)
        else:

            def broken_assess(db: Session, shift: Shift) -> gap_service.ShiftAssessment:
                raise RuntimeError("database went away")

            patch.setattr(gap_service, "assess_shift", broken_assess)

        assert close_due() == []

    assert events() == {
        first: (EventStatus.RECEIVED, None, None),
        second: (EventStatus.RECEIVED, None, None),
    }
    assert assigned() == {101, 102, 103, 104, 105}
    assert count(StaffUnavailability) == 0
    assert count(StaffingCase) == 0
    assert audit_actions() == [AuditAction.EVENT_RECEIVED, AuditAction.EVENT_RECEIVED]
    with SessionLocal() as db:
        requirement = db.get(StaffingRequirement, 1)
        assert requirement is not None
        assert requirement.required_staff == 5

    # The job tries again on its next round (section 3.9)
    (window,) = close_due()

    assert window.event_ids == (first, second)
    assert window.case_id is not None
    assert {status for status, _, _ in events().values()} == {EventStatus.PROCESSED}
    assert assigned() == {101, 102, 103}
    assert count(StaffUnavailability) == 2


def test_shift_whose_close_fails_does_not_stop_the_other_shifts(
    committed_scenarios: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    night = report(105)
    evening = report(103, shift_id=threshold.SHIFT_ID)
    clock.advance(timedelta(seconds=WINDOW))
    real_apply = merge_window_service._apply

    def apply_but_not_on_the_night_shift(db: Session, shift: Shift, event: StaffingEvent) -> None:
        if shift.id == NIGHT_SHIFT:
            raise RuntimeError("database went away")
        real_apply(db, shift, event)

    monkeypatch.setattr(merge_window_service, "_apply", apply_but_not_on_the_night_shift)

    closed = close_due()

    # The night shift comes first by ID, fails, and the evening shift still closes
    assert [window.shift_id for window in closed] == [threshold.SHIFT_ID]
    assert events()[night][0] is EventStatus.RECEIVED
    assert events()[evening][0] is EventStatus.IGNORED
    assert assigned() == {101, 102, 103, 104, 105}


# --------------------------------------------------------------------------- #
# 2. Receiving and closing share the shift lock
# --------------------------------------------------------------------------- #
def test_event_that_arrives_during_a_close_starts_the_next_window(
    committed_scenarios: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The close is held just before it judges the shift. A request that arrives
    then waits for the shift lock, and is not part of the window being closed."""
    first, second = report(104), report(105)
    clock.advance(timedelta(seconds=WINDOW))
    inside_close, let_close_finish = threading.Event(), threading.Event()
    real_assess = gap_service.assess_shift

    def assess_slowly(db: Session, shift: Shift) -> gap_service.ShiftAssessment:
        inside_close.set()
        assert let_close_finish.wait(timeout=20)
        return real_assess(db, shift)

    monkeypatch.setattr(gap_service, "assess_shift", assess_slowly)
    closed: list[ClosedWindow] = []
    answers: list[dict[str, Any]] = []

    def close() -> None:
        closed.extend(close_due())

    def report_late() -> None:
        with TestClient(app) as late_client:
            response = late_client.post(
                "/events",
                headers={"X-Demo-User": "103"},
                json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT},
            )
            answers.append(response.json())

    closing = threading.Thread(target=close)
    closing.start()
    assert inside_close.wait(timeout=20)
    late = threading.Thread(target=report_late)
    late.start()
    # The late request cannot get past the shift lock while the close holds it
    late.join(timeout=1.5)
    assert late.is_alive()
    assert count(StaffingEvent) == 2

    let_close_finish.set()
    closing.join(timeout=30)
    late.join(timeout=30)

    assert not closing.is_alive() and not late.is_alive()
    (window,) = closed
    assert window.event_ids == (first, second)
    (answer,) = answers
    assert (answer["event_status"], answer["case_id"]) == ("RECEIVED", None)
    # The old window did not take it, and it did not change the old window
    assert events() == {
        first: (EventStatus.PROCESSED, clock.now(), window.case_id),
        second: (EventStatus.PROCESSED, clock.now(), window.case_id),
        answer["event_id"]: (EventStatus.RECEIVED, None, None),
    }
    assert assigned() == {101, 102, 103}
    assert count(StaffingCase) == 1


def test_two_closes_of_one_window_at_once_open_one_case(committed_scenarios: None) -> None:
    """The job and a clock advance, or two job rounds that overlap."""
    report(104)
    report(105)
    clock.advance(timedelta(seconds=WINDOW))
    start = threading.Barrier(2, timeout=10)
    results: list[ClosedWindow | None] = []

    def close() -> None:
        with SessionLocal() as db:
            start.wait()
            results.append(merge_window_service.close_window(db, NIGHT_SHIFT))

    threads = [threading.Thread(target=close) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(result is None for result in results) == [False, True]
    assert count(StaffingCase) == 1
    assert count(StaffUnavailability) == 2
    assert audit_actions().count(AuditAction.CASE_OPENED) == 1


def test_two_events_for_one_shift_at_once_both_join_the_window(committed_scenarios: None) -> None:
    start = threading.Barrier(2, timeout=10)
    statuses: list[int] = []

    def report_leave(staff_id: int) -> None:
        with TestClient(app) as real_client:
            start.wait()
            response = real_client.post(
                "/events",
                headers={"X-Demo-User": str(staff_id)},
                json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT},
            )
            statuses.append(response.status_code)

    threads = [threading.Thread(target=report_leave, args=(staff_id,)) for staff_id in (104, 105)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert statuses == [201, 201]
    clock.advance(timedelta(seconds=WINDOW))
    (window,) = close_due()
    assert len(window.event_ids) == 2
    assert count(StaffingCase) == 1


# --------------------------------------------------------------------------- #
# 3. A status never goes back to RECEIVED
# --------------------------------------------------------------------------- #
def test_closed_events_are_not_touched_by_later_closes(committed_scenarios: None) -> None:
    first = report(105)
    clock.advance(timedelta(seconds=WINDOW))
    (window,) = close_due()
    after_first_close = events()[first]
    with SessionLocal.begin() as db:
        case = db.get(StaffingCase, window.case_id)
        assert case is not None
        case.status = CaseStatus.RESOLVED
    second = report(104)
    clock.advance(timedelta(seconds=WINDOW))

    (next_window,) = close_due()

    assert next_window.event_ids == (second,)
    assert events()[first] == after_first_close
    assert events()[second][0] is EventStatus.PROCESSED
    assert close_due() == []
