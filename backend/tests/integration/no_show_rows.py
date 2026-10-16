"""Row builders for tests that run the NO_SHOW job (docs/workflow.md, section 6.24).

The Golden Case night shift (id 1) starts D 23:00 and has staff 101-105 REGULAR
ASSIGNED. A test that moves the clock past the 15 minute deadline would see every
one of them as a NO_SHOW, so it first checks the people in with check_in_everyone():
the same function the seed uses, attendance_service.record().
"""

from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import NO_SHOW_GRACE_SECONDS
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    StaffingEvent,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffUnavailability,
)
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    CheckInSource,
    EventType,
    RosterStatus,
    ShiftType,
)
from app.services import actor_service, attendance_service
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT = 1, 2
START = DEMO_NOW.replace(hour=23)  # the night shift starts
END = START + timedelta(hours=8)
DEADLINE = START + timedelta(seconds=NO_SHOW_GRACE_SECONDS)
GRACE = timedelta(seconds=NO_SHOW_GRACE_SECONDS)


def at(moment: datetime) -> None:
    clock.set_time(moment)


def roster_row(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> RosterAssignment:
    """The person's one ASSIGNED row of the shift, as it is in the database now."""
    db.expire_all()
    return db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id,
            RosterAssignment.shift_id == shift_id,
            RosterAssignment.status == RosterStatus.ASSIGNED,
        )
    ).one()


def rows_of(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> list[RosterAssignment]:
    """Every row of the person in the shift, in every status, by id."""
    db.expire_all()
    return list(
        db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id)
            .order_by(RosterAssignment.id)
        )
    )


def check_in(
    db: Session, row: RosterAssignment, *, check_in_at: datetime | None = None
) -> datetime:
    """Record a check-in of `row` (on time unless `check_in_at` says otherwise)."""
    shift = db.get(Shift, row.shift_id)
    assert shift is not None
    moment = check_in_at or attendance_service.required_arrival_at(row, shift)
    attendance_service.record(
        db,
        roster=row,
        shift=shift,
        check_in_at=moment,
        source=CheckInSource.SIMULATED,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
    )
    return moment


def check_in_everyone(
    db: Session, shift_id: int | None = None, *, except_staff: Collection[int] = ()
) -> None:
    """On-time check-in of every ASSIGNED row but the people in `except_staff`.

    Without `shift_id` it covers every shift: the seed has other wards whose shifts run
    at the same time as shift 1, and the job would find their rows too.
    """
    query = (
        select(RosterAssignment)
        .where(
            RosterAssignment.status == RosterStatus.ASSIGNED,
            RosterAssignment.staff_id.not_in(list(except_staff)),
        )
        .order_by(RosterAssignment.id)
    )
    if shift_id is not None:
        query = query.where(RosterAssignment.shift_id == shift_id)
    rows = db.scalars(query).all()
    for row in rows:
        check_in(db, row)
    db.flush()


def add_shift(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
    merge_window_seconds: int = 0,
    required_staff: int = 1,
) -> Shift:
    """A shift of ward 1 with a requirement of `required_staff` RNs and no roster rows."""
    shift = Shift(
        id=(db.scalar(select(func.max(Shift.id))) or 0) + 1,
        ward_id=1,
        patient_count=2,
        start_at=start_at,
        end_at=end_at,
        shift_type=ShiftType.DAY,
        is_active=True,
        merge_window_seconds=merge_window_seconds,
    )
    db.add(shift)
    db.flush()
    requirement = StaffingRequirement(
        shift_id=shift.id,
        required_staff=required_staff,
        minimum_staff=required_staff,
        created_at=DEMO_NOW,
    )
    db.add(requirement)
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=requirement.id, role_id=1, required_count=required_staff
        )
    )
    db.flush()
    return shift


def add_row(
    db: Session,
    staff_id: int,
    shift: Shift,
    *,
    status: RosterStatus = RosterStatus.ASSIGNED,
    assignment_type: AssignmentType = AssignmentType.REGULAR,
    transferred_from: RosterAssignment | None = None,
    actual_start_at: datetime | None = None,
    created_at: datetime | None = None,
) -> RosterAssignment:
    row = RosterAssignment(
        staff_id=staff_id,
        shift_id=shift.id,
        status=status,
        assignment_type=assignment_type,
        candidate_source=None,
        actual_start_at=actual_start_at,
        transferred_from_assignment_id=None if transferred_from is None else transferred_from.id,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row


def no_show_events(db: Session) -> list[StaffingEvent]:
    db.expire_all()
    return [
        event
        for event in db.scalars(select(StaffingEvent).order_by(StaffingEvent.id))
        if event.event_type is EventType.STAFF_UNAVAILABLE
        and event.payload.get("reason") == "NO_SHOW"
    ]


def absences(db: Session) -> list[StaffUnavailability]:
    db.expire_all()
    return list(db.scalars(select(StaffUnavailability).order_by(StaffUnavailability.id)))


def audit_of(db: Session, action: AuditAction) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))
