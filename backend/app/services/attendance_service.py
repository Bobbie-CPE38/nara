"""
Check-in of a nurse on an assigned shift (docs/workflow.md, section 6.24).

The pure time rules (required arrival, deadline, accepted window, on time) are
here so the check-in routes, the LINE command and the NO_SHOW job all read the
same ones. check_in() is the one entry point of the routes and owns its audit row
and commit. record() writes the ATTENDANCE row and its ATTENDANCE_CHECKED_IN
audit row without committing; the demo seed calls it too, so every ATTENDANCE row
with a shift_id has exactly one audit row (a repeated check-in reads its roster
row from that audit row).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import CHECK_IN_EARLIEST_SECONDS, NO_SHOW_GRACE_SECONDS
from app.db.models import (
    ApprovalRequest,
    Attendance,
    AuditLog,
    CandidateOutreach,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import (
    WAITING_CASE_STATUSES,
    AssignmentType,
    AuditAction,
    CheckInSource,
    EntityType,
    EventType,
    OutreachStatus,
    RosterStatus,
)
from app.services import (
    audit_service,
    hard_rule_service,
    merge_window_service,
    unavailability_service,
    wave_service,
)

# How many times a check-in after a NO_SHOW starts again when new offers appear
CHECK_IN_LOCK_TRIES = 5


class CheckInOutsideWindowError(ValueError):
    """A first check-in is before the earliest accepted time or at/after the effective end."""


class CheckInLockRetryError(ValueError):
    """New offers kept appearing while a late check-in tried to lock the case; retry."""


@dataclass(frozen=True)
class CheckInResult:
    attendance_id: int
    shift_id: int
    check_in_at: datetime
    on_time: bool
    deadline: datetime


def required_arrival_at(roster: RosterAssignment, shift: Shift) -> datetime:
    """When the person must be there: the effective start, or later for a replacement.

    A REPLACEMENT row can be created after the shift started, so it counts from
    max(effective start, created_at). A REGULAR row ignores created_at, because the
    seed creates those rows at reset.
    """
    start = roster.actual_start_at if roster.actual_start_at is not None else shift.start_at
    if roster.assignment_type == AssignmentType.REPLACEMENT:
        return max(start, roster.created_at)
    return start


def deadline_at(roster: RosterAssignment, shift: Shift) -> datetime:
    return required_arrival_at(roster, shift) + timedelta(seconds=NO_SHOW_GRACE_SECONDS)


def effective_end_at(roster: RosterAssignment, shift: Shift) -> datetime:
    return roster.actual_end_at if roster.actual_end_at is not None else shift.end_at


def accepts_check_in(roster: RosterAssignment, shift: Shift, at: datetime) -> bool:
    """Half-open window: arrival - CHECK_IN_EARLIEST_SECONDS <= at < effective end."""
    earliest = required_arrival_at(roster, shift) - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)
    return earliest <= at < effective_end_at(roster, shift)


def is_on_time(roster: RosterAssignment, shift: Shift, check_in_at: datetime) -> bool:
    return check_in_at <= deadline_at(roster, shift)


def check_in(
    db: Session, *, staff_id: int, shift_id: int, source: CheckInSource, actor_id: int
) -> CheckInResult:
    """Record the check-in, or return the one already recorded, then commit.

    Order: lock the SHIFT (404 if missing) → an existing ATTENDANCE row of this
    person in the shift is returned as it is, with no window check, no write and
    no new audit row → lock the person's ASSIGNED roster rows, together with the
    rows a NO_SHOW cancelled, in one query (404) → choose the row for the clock, or
    422 when none takes it → write → commit. Lock order is SHIFT then
    ROSTER_ASSIGNMENT (workflow.md 6.11). The shift lock also makes two simultaneous
    check-ins of one person run one after the other. On any error the caller must roll back.

    A chosen row that a NO_SHOW cancelled is a late arrival after stage 2
    (workflow.md 6.24): _late_check_in() takes the rest of the locks and
    late_arrival_service restores the row. New offers of the case can appear
    between its lock steps; it then starts again, CHECK_IN_LOCK_TRIES times in
    all, and raises CheckInLockRetryError after that (the routes answer 409).
    """
    for _ in range(CHECK_IN_LOCK_TRIES):
        result = _check_in_once(
            db, staff_id=staff_id, shift_id=shift_id, source=source, actor_id=actor_id
        )
        if result is not None:
            return result
    raise CheckInLockRetryError("Could not lock a stable offer set for the check-in; retry")


def _check_in_once(
    db: Session, *, staff_id: int, shift_id: int, source: CheckInSource, actor_id: int
) -> CheckInResult | None:
    """One try of check_in(). None means the transaction was rolled back and must restart."""
    shift = merge_window_service.lock_shift(db, shift_id)

    existing = db.scalar(
        select(Attendance).where(Attendance.staff_id == staff_id, Attendance.shift_id == shift_id)
    )
    if existing is not None:
        result = _existing_result(db, existing, shift)
        db.commit()
        return result

    no_show_rows = _no_show_rows(db, staff_id=staff_id, shift_id=shift_id)
    rows = _lock_rows(db, staff_id=staff_id, shift_id=shift_id, no_show_row_ids=set(no_show_rows))
    now = clock.now()
    roster = _row_for(rows, shift, now)
    if roster is None:
        # No row takes this moment: say why with the row that comes first in time
        roster = min(rows, key=lambda row: (required_arrival_at(row, shift), row.id))
        earliest = required_arrival_at(roster, shift) - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)
        raise CheckInOutsideWindowError(
            f"Check-in for shift {shift_id} is accepted from {_iso(earliest)}"
            f" until {_iso(effective_end_at(roster, shift))}, not at {_iso(now)}"
        )
    if roster.status == RosterStatus.ASSIGNED:
        result = record(
            db, roster=roster, shift=shift, check_in_at=now, source=source, actor_id=actor_id
        )
        db.commit()
        return result
    return _late_check_in(
        db,
        shift=shift,
        roster=roster,
        unavailability_id=no_show_rows[roster.id],
        now=now,
        source=source,
        actor_id=actor_id,
    )


def _late_check_in(
    db: Session,
    *,
    shift: Shift,
    roster: RosterAssignment,
    unavailability_id: int,
    now: datetime,
    source: CheckInSource,
    actor_id: int,
) -> CheckInResult | None:
    """The person's row was cancelled by a NO_SHOW: lock the rest, record, restore, commit.

    The shift and the rows are already locked. Order after them (workflow.md 6.11):
    the case's pending approval requests, its unfinished offers, the case, then
    the STAFF of its whole plan together with the late person (one query), and
    last the absence, like update_end_at (STAFF, then the period). Without a
    waiting case only the late person's STAFF row is locked. None when the case
    got new requests or offers while the locks were taken: nothing is written,
    the transaction is rolled back and the caller starts again.
    """
    # Imported here: late_arrival_service imports this module
    from app.services import late_arrival_service

    staff_id, shift_id = roster.staff_id, shift.id
    case = late_arrival_service.credited_case(db, shift_id)
    if case is not None and case.status in WAITING_CASE_STATUSES:
        case_id = case.id
        request_ids = _lock_pending_requests(db, case_id)
        offer_ids = _lock_unfinished_offers(db, case_id)
        db.scalars(
            select(StaffingCase)
            .where(StaffingCase.id == case_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).one()
        try:
            plan_staff = [item.staff_id for item in wave_service.plan_items(db, case_id)]
        except LookupError:
            plan_staff = []
        hard_rule_service.lock_staff(db, [*plan_staff, staff_id])
        credited = late_arrival_service.credited_case(db, shift_id)
        if (
            credited is None
            or credited.id != case_id
            or _case_offer_ids(db, case_id) != offer_ids
            or _pending_request_ids(db, case_id) != request_ids
        ):
            # An offer or a request was added, or the case moved on, while locking
            db.rollback()
            return None
    else:
        hard_rule_service.lock_staff(db, [staff_id])
    unavailability = db.scalars(
        select(StaffUnavailability)
        .where(StaffUnavailability.id == unavailability_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    result = record(
        db, roster=roster, shift=shift, check_in_at=now, source=source, actor_id=actor_id
    )
    late_arrival_service.arrive_after_no_show(
        db, shift=shift, original=roster, unavailability=unavailability, check_in_at=now
    )
    return result


def _no_show_rows(db: Session, *, staff_id: int, shift_id: int) -> dict[int, int]:
    """Roster row ID -> unavailability ID of the rows a NO_SHOW cancelled for this person.

    Stage 2 names the row in payload.roster_assignment_id of the STAFF_UNAVAILABLE
    event and the period in `unavailability_id` of the UNAVAILABILITY_CREATED
    audit row of that event. An event stage 2 has not processed has no audit row,
    so its row is still ASSIGNED and is not listed.
    """
    rows = db.execute(
        select(
            StaffingEvent.payload["roster_assignment_id"].as_integer(),
            AuditLog.payload["unavailability_id"].as_integer(),
        )
        .join(AuditLog, AuditLog.event_id == StaffingEvent.id)
        .where(
            StaffingEvent.shift_id == shift_id,
            StaffingEvent.staff_id == staff_id,
            StaffingEvent.event_type == EventType.STAFF_UNAVAILABLE,
            StaffingEvent.payload["reason"].as_string() == merge_window_service.NO_SHOW_REASON,
            AuditLog.action == AuditAction.UNAVAILABILITY_CREATED,
        )
    )
    return {roster_id: unavailability_id for roster_id, unavailability_id in rows}


def _lock_pending_requests(db: Session, case_id: int) -> set[int]:
    """Lock the pending approval requests of the case in one query ordered by id."""
    return set(
        db.scalars(
            select(ApprovalRequest.id)
            .where(ApprovalRequest.case_id == case_id, ApprovalRequest.is_pending.is_(True))
            .order_by(ApprovalRequest.id)
            .with_for_update(key_share=True)
        )
    )


def _pending_request_ids(db: Session, case_id: int) -> set[int]:
    return set(
        db.scalars(
            select(ApprovalRequest.id).where(
                ApprovalRequest.case_id == case_id, ApprovalRequest.is_pending.is_(True)
            )
        )
    )


def _lock_unfinished_offers(db: Session, case_id: int) -> set[int]:
    """Lock the SENT and ACCEPTED offers of the case in one query ordered by id.

    Returns the IDs of every offer of the case, so the caller can tell when a
    new one appears after the locks were taken.
    """
    list(
        db.scalars(
            select(CandidateOutreach.id)
            .where(
                CandidateOutreach.case_id == case_id,
                CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
            )
            .order_by(CandidateOutreach.id)
            .with_for_update(key_share=True)
        )
    )
    return _case_offer_ids(db, case_id)


def _case_offer_ids(db: Session, case_id: int) -> set[int]:
    return set(db.scalars(select(CandidateOutreach.id).where(CandidateOutreach.case_id == case_id)))


def _lock_rows(
    db: Session, *, staff_id: int, shift_id: int, no_show_row_ids: set[int]
) -> list[RosterAssignment]:
    """The person's ASSIGNED rows in the shift and the rows a NO_SHOW cancelled, locked.

    One query ordered by id. A person can hold several ASSIGNED rows (T2 allows
    separate parts of one shift, and a move out and back leaves the source prefix
    ASSIGNED), so this is not lock_assigned_roster(), which refuses more than one row.
    """
    rows = list(
        db.scalars(
            select(RosterAssignment)
            .where(
                RosterAssignment.staff_id == staff_id,
                RosterAssignment.shift_id == shift_id,
                or_(
                    RosterAssignment.status == RosterStatus.ASSIGNED,
                    RosterAssignment.id.in_(no_show_row_ids),
                ),
            )
            .order_by(RosterAssignment.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )
    if not rows:
        raise unavailability_service.NoAssignedRosterError(
            f"Staff {staff_id} has no assigned roster row in shift {shift_id}"
        )
    return rows


def _row_for(rows: list[RosterAssignment], shift: Shift, at: datetime) -> RosterAssignment | None:
    """The row a check-in at `at` belongs to: among the rows whose window takes `at`,
    the one with the earliest required arrival (then the lowest id). None if no row does."""
    taking = [row for row in rows if accepts_check_in(row, shift, at)]
    if not taking:
        return None
    return min(taking, key=lambda row: (required_arrival_at(row, shift), row.id))


def record(
    db: Session,
    *,
    roster: RosterAssignment,
    shift: Shift,
    check_in_at: datetime,
    source: CheckInSource,
    actor_id: int,
) -> CheckInResult:
    """Insert the ATTENDANCE row and its audit row. Flush, never commit, no window check.

    check_out_at and the work and overtime minutes stay NULL: working_time_service
    sums only completed rows, so overtime is not counted twice.
    """
    on_time = is_on_time(roster, shift, check_in_at)
    attendance = Attendance(
        staff_id=roster.staff_id,
        shift_id=shift.id,
        check_in_at=check_in_at,
        synced_at=check_in_at,
    )
    db.add(attendance)
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        actor_id=actor_id,
        action=AuditAction.ATTENDANCE_CHECKED_IN,
        entity_type=EntityType.ATTENDANCE,
        entity_id=attendance.id,
        payload={
            "attendance_id": attendance.id,
            "staff_id": roster.staff_id,
            "shift_id": shift.id,
            "roster_assignment_id": roster.id,
            "check_in_at": _iso(check_in_at),
            "on_time": on_time,
            "source": source.value,
        },
    )
    return CheckInResult(
        attendance_id=attendance.id,
        shift_id=shift.id,
        check_in_at=check_in_at,
        on_time=on_time,
        deadline=deadline_at(roster, shift),
    )


def _existing_result(db: Session, attendance: Attendance, shift: Shift) -> CheckInResult:
    """The answer for a repeated check-in: the row's own time, the roster row of its audit row."""
    roster_id = db.scalar(
        select(AuditLog.payload["roster_assignment_id"].as_integer()).where(
            AuditLog.action == AuditAction.ATTENDANCE_CHECKED_IN,
            AuditLog.entity_type == EntityType.ATTENDANCE,
            AuditLog.entity_id == attendance.id,
        )
    )
    roster = None if roster_id is None else db.get(RosterAssignment, roster_id)
    if roster is None:
        raise RuntimeError(f"Attendance {attendance.id} has no ATTENDANCE_CHECKED_IN audit row")
    return CheckInResult(
        attendance_id=attendance.id,
        shift_id=shift.id,
        check_in_at=attendance.check_in_at,
        on_time=is_on_time(roster, shift, attendance.check_in_at),
        deadline=deadline_at(roster, shift),
    )


def _iso(moment: datetime) -> str:
    """Audit times as +07:00, like UNAVAILABILITY_CREATED."""
    return moment.astimezone(clock.APP_TIMEZONE).isoformat()
