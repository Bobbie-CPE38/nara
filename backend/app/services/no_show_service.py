"""NO_SHOW, stage 1: find rows whose person did not come (docs/workflow.md, section 6.24).

Called by job_service.run_due_work() right before the windows are closed. This
stage writes only STAFF_UNAVAILABLE events with payload.reason = NO_SHOW, through
event_service.record_no_shows(). The roster, the absence and the audit of the
absence are written when the window closes (merge_window_service._apply_no_show).
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import NO_SHOW_GRACE_SECONDS
from app.db.models import Attendance, RosterAssignment, Shift, StaffingEvent, StaffUnavailability
from app.domain.enums import STAFF_EVENT_TYPES, EventStatus, RosterStatus
from app.services import (
    attendance_service,
    event_service,
    merge_window_service,
    roster_time_service,
    unavailability_service,
)

logger = logging.getLogger(__name__)


def detect_due_no_shows(db: Session) -> list[int]:
    """Write the NO_SHOW events that are due now, one transaction per shift. Commits.

    Returns the new event IDs. A shift that raises is rolled back, logged and
    skipped: the next call tries again (same pattern as close_due_windows).
    """
    event_ids: list[int] = []
    for shift_id, row_ids in _candidates(db).items():
        try:
            event_ids.extend(_detect_in_shift(db, shift_id, row_ids))
        except Exception:
            logger.exception("Detecting NO_SHOW in shift %s failed", shift_id)
            db.rollback()
    return event_ids


def is_no_show(db: Session, row: RosterAssignment, shift: Shift, now: datetime) -> bool:
    """Whether the person of this locked row did not come. Reads only.

    The caller holds the shift lock and the row lock, so every fact below is
    current: a leave, a check-in or a move cannot be written meanwhile.
    """
    if row.status != RosterStatus.ASSIGNED:
        return False
    # Exactly at the deadline is still on time: only strictly after it counts
    if not attendance_service.deadline_at(row, shift) < now:
        return False
    end_at = attendance_service.effective_end_at(row, shift)
    if not now < end_at:
        return False
    if has_on_time_check_in(db, row):
        return False
    start_at = row.actual_start_at if row.actual_start_at is not None else shift.start_at
    on_leave = db.scalar(
        select(
            exists().where(
                StaffUnavailability.staff_id == row.staff_id,
                unavailability_service.leave_overlaps_shift_sql(
                    StaffUnavailability.start_at, StaffUnavailability.end_at, start_at, end_at
                ),
            )
        )
    )
    if on_leave:
        return False
    # A leave or a cancellation already waits for its window: it decides the row
    waiting_event = db.scalar(
        select(
            exists().where(
                StaffingEvent.shift_id == row.shift_id,
                StaffingEvent.staff_id == row.staff_id,
                StaffingEvent.event_type.in_(list(STAFF_EVENT_TYPES)),
                StaffingEvent.status == EventStatus.RECEIVED,
            )
        )
    )
    if waiting_event:
        return False
    # The person was moved out of this row mid-shift (the source stays ASSIGNED)
    moved_out = db.scalar(
        select(exists().where(RosterAssignment.transferred_from_assignment_id == row.id))
    )
    return not moved_out


def has_on_time_check_in(db: Session, row: RosterAssignment) -> bool:
    """An on-time check-in on this row or any row before it in its move chain.

    Walks transferred_from_assignment_id back to the first row. A person who
    checked in on time for a source row counts as present for every row after it
    (workflow.md 6.24), so a move creates no second check-in.
    """
    seen: set[int] = set()
    current: RosterAssignment | None = row
    while current is not None and current.id not in seen:
        seen.add(current.id)
        shift = db.get(Shift, current.shift_id)
        assert shift is not None
        check_in_at = db.scalar(
            select(Attendance.check_in_at).where(
                Attendance.staff_id == current.staff_id, Attendance.shift_id == current.shift_id
            )
        )
        if check_in_at is not None and check_in_at <= attendance_service.deadline_at(
            current, shift
        ):
            return True
        source_id = current.transferred_from_assignment_id
        current = None if source_id is None else db.get(RosterAssignment, source_id)
    return False


def _candidates(db: Session) -> dict[int, list[int]]:
    """Row IDs that may be a NO_SHOW, by shift. A hint only: no lock, checked again later.

    The effective start plus the grace period must have passed, and the effective
    end must not have. It is necessary, not enough: a REPLACEMENT counts from
    max(start, created_at), and the check-in, the leave and the move are not read.
    """
    now = clock.now()
    rows = db.execute(
        select(RosterAssignment.shift_id, RosterAssignment.id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(
            RosterAssignment.status == RosterStatus.ASSIGNED,
            roster_time_service.end_at() > now,
            roster_time_service.start_at() + timedelta(seconds=NO_SHOW_GRACE_SECONDS) < now,
        )
        .order_by(RosterAssignment.shift_id, RosterAssignment.id)
    ).all()
    by_shift: dict[int, list[int]] = defaultdict(list)
    for shift_id, row_id in rows:
        by_shift[shift_id].append(row_id)
    return by_shift


def _detect_in_shift(db: Session, shift_id: int, row_ids: list[int]) -> list[int]:
    """Lock the shift, then its candidate rows, and record the events. Commits."""
    shift = merge_window_service.lock_shift(db, shift_id)
    # One query, ordered by id: the same order everywhere that locks several rows
    rows = list(
        db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.id.in_(row_ids))
            .order_by(RosterAssignment.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )
    now = clock.now()
    due = [row for row in rows if is_no_show(db, row, shift, now)]
    if not due:
        # Nothing was written: this only releases the locks
        db.commit()
        return []
    return event_service.record_no_shows(db, shift=shift, rosters=due)
