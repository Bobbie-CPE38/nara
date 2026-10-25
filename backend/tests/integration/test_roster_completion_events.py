"""Roster completion never discards a staff event accepted before the shift ended
(round 3 PR R review, docs/workflow.md 6.18).

The merge_gap scenario gives the night shift (2026-10-09 23:00 to 2026-10-10
07:00, 101 to 105 on it) a ten minute window. Each test reports five minutes
before the shift ends, so the window closes after it.
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import AuditAction, CaseStatus, EventStatus, EventType, RosterStatus
from app.seed.scenarios import merge_gap
from app.services import actor_service, event_service, job_service, roster_completion_service
from tests.integration.case_rows import make_case

NIGHT_SHIFT = 1
WINDOW = merge_gap.MERGE_WINDOW_SECONDS

# What the steps after the window write is tested with those steps
pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def merging(seeded: Session) -> Session:
    merge_gap.seed(seeded)
    night = seeded.get(Shift, NIGHT_SHIFT)
    assert night is not None
    clock.set_time(night.end_at - timedelta(minutes=5))
    return seeded


def report(db: Session, reporter: int, event_type: EventType, **details: Any) -> int:
    staff = db.get(Staff, reporter)
    assert staff is not None
    return event_service.receive_event(
        db,
        staff_id=reporter,
        actor_id=actor_service.user_id(db, reporter),
        role_id=staff.role_id,
        event_type=event_type,
        shift_id=NIGHT_SHIFT,
        **details,
    ).event_id


def state(db: Session, event_id: int, staff_id: int) -> tuple[EventStatus, RosterStatus]:
    db.expire_all()
    event = db.get(StaffingEvent, event_id)
    assert event is not None
    row = db.scalars(
        select(RosterAssignment.status).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()
    return event.status, row


def actions(db: Session, event_id: int) -> list[AuditAction]:
    return list(
        db.scalars(
            select(AuditLog.action).where(AuditLog.event_id == event_id).order_by(AuditLog.id)
        )
    )


def night_rows(db: Session, assignment_ids: list[int]) -> list[int]:
    """The IDs on the ICU night shift: the Medicine night of the seed ends at the same time."""
    return list(
        db.scalars(
            select(RosterAssignment.id).where(
                RosterAssignment.id.in_(assignment_ids), RosterAssignment.shift_id == NIGHT_SHIFT
            )
        )
    )


def test_a_leave_reported_before_the_end_applies_after_the_job_runs(merging: Session) -> None:
    event_id = report(merging, 105, EventType.STAFF_UNAVAILABLE)

    clock.advance(timedelta(seconds=WINDOW))
    work = job_service.run_due_work(merging)

    assert state(merging, event_id, 105) == (EventStatus.PROCESSED, RosterStatus.CANCELLED)
    assert merging.scalars(select(StaffUnavailability.staff_id)).all() == [105]
    assert AuditAction.UNAVAILABILITY_CREATED in actions(merging, event_id)
    # The other four people on the shift were completed in the same tick
    assert len(night_rows(merging, work.completed_assignment_ids)) == 4


def test_a_cancellation_reported_before_the_end_applies_after_the_job_runs(
    merging: Session,
) -> None:
    event_id = report(
        merging,
        900,
        EventType.ASSIGNMENT_CANCELLED,
        target_staff_id=104,
        reason="Moved to another ward",
    )

    clock.advance(timedelta(seconds=WINDOW))
    job_service.run_due_work(merging)

    assert state(merging, event_id, 104) == (EventStatus.PROCESSED, RosterStatus.CANCELLED)
    assert AuditAction.ASSIGNMENT_CANCELLED in actions(merging, event_id)


def test_a_leave_on_a_shift_with_a_running_case_joins_it_when_its_window_closes(
    merging: Session,
) -> None:
    """Round 6 PR EV10 (6.40): a waiting case no longer holds the leave back."""
    running = make_case(merging, CaseStatus.WAITING_RESPONSE)
    merging.commit()
    event_id = report(merging, 105, EventType.STAFF_UNAVAILABLE)

    clock.advance(timedelta(seconds=WINDOW))
    job_service.run_due_work(merging)

    assert state(merging, event_id, 105) == (EventStatus.PROCESSED, RosterStatus.CANCELLED)
    event = merging.get(StaffingEvent, event_id)
    assert event is not None and event.case_id == running.id
    assert merging.scalars(select(StaffUnavailability.staff_id)).all() == [105]


def test_closing_the_window_still_applies_to_a_row_completed_meanwhile(
    merging: Session,
) -> None:
    """The second guard: the job lost the race and completed the row anyway."""
    event_id = report(merging, 105, EventType.STAFF_UNAVAILABLE)
    row = merging.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 105, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()
    row.status = RosterStatus.COMPLETED
    merging.commit()

    clock.advance(timedelta(seconds=WINDOW))
    job_service.run_due_work(merging)

    assert state(merging, event_id, 105) == (EventStatus.PROCESSED, RosterStatus.CANCELLED)


def test_a_person_without_a_queued_event_is_still_completed(merging: Session) -> None:
    report(merging, 105, EventType.STAFF_UNAVAILABLE)
    clock.advance(timedelta(minutes=5))

    completed = roster_completion_service.complete_ended_shifts(merging)

    completed_staff = set(
        merging.scalars(
            select(RosterAssignment.staff_id).where(
                RosterAssignment.id.in_(night_rows(merging, completed))
            )
        )
    )
    assert completed_staff == {101, 102, 103, 104}
