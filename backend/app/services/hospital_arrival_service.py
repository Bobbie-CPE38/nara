"""The people of the hospital demo come to work by themselves (round 6 PR EV6, 6.36.3).

Called by job_service.run_due_work() before NO_SHOW looks for missing people. Without it,
every shift start of the hospital demo would turn its 20 people into NO_SHOW cases.

Only the profile's own people on their own REGULAR rows arrive, and only while the profile
is loaded and active: a replacement or anyone else put on a hospital shift must check in
like everyone, so a missing replacement still becomes a NO_SHOW (review of #145). Someone
with a leave that overlaps the shift, or a reported absence for it, does not arrive.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Attendance,
    DemoDataset,
    RosterAssignment,
    Shift,
    StaffingEvent,
    StaffUnavailability,
    Ward,
)
from app.domain.enums import (
    STAFF_EVENT_TYPES,
    ActorName,
    AssignmentType,
    CheckInSource,
    RosterStatus,
)
from app.seed import hospital_demo
from app.services import actor_service, attendance_service, merge_window_service


def check_in_arrivals(db: Session) -> list[int]:
    """Check in, on time, the profile's people whose shift has begun. Commits per shift.

    Returns the new ATTENDANCE IDs. One cheap read and nothing else while the profile is
    not loaded, or is paused.
    """
    loaded = db.scalar(
        select(DemoDataset.id).where(DemoDataset.profile == hospital_demo.PROFILE).limit(1)
    )
    if loaded is None:
        return []
    now = clock.now()
    reported = exists().where(
        StaffingEvent.shift_id == RosterAssignment.shift_id,
        StaffingEvent.staff_id == RosterAssignment.staff_id,
        StaffingEvent.event_type.in_(list(STAFF_EVENT_TYPES)),
    )
    checked_in = exists().where(
        Attendance.shift_id == RosterAssignment.shift_id,
        Attendance.staff_id == RosterAssignment.staff_id,
    )
    on_leave = exists().where(
        StaffUnavailability.staff_id == RosterAssignment.staff_id,
        StaffUnavailability.start_at < Shift.end_at,
        (StaffUnavailability.end_at.is_(None)) | (StaffUnavailability.end_at > Shift.start_at),
    )
    due = db.execute(
        select(RosterAssignment.shift_id, RosterAssignment.id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .join(Ward, Ward.id == Shift.ward_id)
        .where(
            Ward.id > hospital_demo.WARD_BASE,
            Ward.id <= hospital_demo.FLOAT_POOL_WARD,
            Ward.is_active.is_(True),
            RosterAssignment.staff_id > hospital_demo.STAFF_BASE,
            RosterAssignment.staff_id <= hospital_demo.STAFF_LAST,
            RosterAssignment.assignment_type == AssignmentType.REGULAR,
            RosterAssignment.status == RosterStatus.ASSIGNED,
            Shift.start_at <= now,
            Shift.end_at > now,
            ~checked_in,
            ~reported,
            ~on_leave,
        )
        .order_by(RosterAssignment.shift_id, RosterAssignment.id)
    ).all()
    if not due:
        return []
    actor_id = actor_service.component_id(db, ActorName.SYSTEM)
    by_shift: dict[int, list[int]] = {}
    for shift_id, row_id in due:
        by_shift.setdefault(shift_id, []).append(row_id)
    attendance_ids: list[int] = []
    for shift_id, row_ids in by_shift.items():
        # Shift, then its roster rows: the lock order of a check-in (6.11)
        shift = merge_window_service.lock_shift(db, shift_id)
        rows = db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.id.in_(row_ids))
            .order_by(RosterAssignment.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).all()
        for roster in rows:
            arrival = attendance_service.required_arrival_at(roster, shift)
            already = db.scalar(
                select(Attendance.id).where(
                    Attendance.shift_id == shift.id, Attendance.staff_id == roster.staff_id
                )
            )
            if roster.status != RosterStatus.ASSIGNED or already is not None or arrival > now:
                continue
            result = attendance_service.record(
                db,
                roster=roster,
                shift=shift,
                check_in_at=arrival,
                source=CheckInSource.SIMULATED,
                actor_id=actor_id,
            )
            attendance_ids.append(result.attendance_id)
        db.commit()
    return attendance_ids
