"""
Unplanned leave of a staff member on an assigned shift (docs/workflow.md, section 3),
and the change of its end (section 9.5, round 3 PR R).

record_unplanned_leave() writes the STAFF_UNAVAILABILITY row and cancels the
roster row; its caller (event_service) owns the audit rows and the transaction.
update_end_at() owns its own audit row and commit.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffUnavailability,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AuditAction,
    AvailabilityReason,
    EntityType,
    OutreachStatus,
    RosterStatus,
)
from app.domain.staffing.ward_authority import manages_ward
from app.services import audit_service, hard_rule_service


class NoAssignedRosterError(LookupError):
    """The staff member has no ASSIGNED roster row in the shift.

    Also what a repeated leave report finds: the first one already cancelled the row.
    """


def lock_assigned_roster(db: Session, *, staff_id: int, shift_id: int) -> RosterAssignment:
    """Return the staff member's one ASSIGNED roster row in the shift, locked.

    Event intake already runs one request at a time per shift, through the
    shift lock that event_service takes first. So a repeated report for the
    same person simply finds no ASSIGNED row here and raises
    NoAssignedRosterError.

    This row lock is for writers that do not take the shift lock: it keeps
    another transaction from changing this roster row while it is cancelled.
    """
    rows = db.scalars(
        select(RosterAssignment)
        .where(
            RosterAssignment.staff_id == staff_id,
            RosterAssignment.shift_id == shift_id,
            RosterAssignment.status == RosterStatus.ASSIGNED,
        )
        .with_for_update(key_share=True)
    ).all()
    if not rows:
        raise NoAssignedRosterError(
            f"Staff {staff_id} has no assigned roster row in shift {shift_id}"
        )
    if len(rows) > 1:
        raise RuntimeError(
            f"Staff {staff_id} has {len(rows)} assigned roster rows in shift {shift_id}"
        )
    return rows[0]


def record_unplanned_leave(
    db: Session, *, roster: RosterAssignment, shift: Shift, end_at: datetime | None
) -> StaffUnavailability:
    """Create the unavailability period and cancel the roster row. Flush, never commit.

    `end_at` is the return time the staff member gave. Without one the period
    ends with the shift.
    """
    unavailability = StaffUnavailability(
        staff_id=roster.staff_id,
        start_at=shift.start_at,
        end_at=end_at if end_at is not None else shift.end_at,
        # It overlaps an assigned shift, so it is unplanned by definition
        reason=AvailabilityReason.UNPLANNED_LEAVE,
    )
    db.add(unavailability)
    roster.status = RosterStatus.CANCELLED
    db.flush()
    return unavailability


class UnavailabilityNotFoundError(LookupError):
    """No STAFF_UNAVAILABILITY row has this ID."""


class UnavailabilityForbiddenError(PermissionError):
    """The caller is not a head nurse of the staff member's home ward."""


class InvalidUnavailabilityEndError(ValueError):
    """The new end is not after the start of the period."""


@dataclass(frozen=True)
class OverlappingOffer:
    outreach_id: int
    case_id: int
    status: OutreachStatus


@dataclass(frozen=True)
class EndAtUpdate:
    unavailability: StaffUnavailability
    previous_end_at: datetime | None
    # ASSIGNED rows of the person whose shift the new period overlaps
    overlapping_assignment_ids: list[int]
    # SENT or ACCEPTED offers of running cases whose shift the new period overlaps
    overlapping_offers: list[OverlappingOffer]


def update_end_at(
    db: Session,
    *,
    unavailability_id: int,
    end_at: datetime,
    role_id: int,
    home_ward_id: int,
    actor_id: int,
) -> EndAtUpdate:
    """Change when a leave period ends, write UNAVAILABILITY_UPDATED, then commit.

    Check order: 404 period → 403 role, then ward of the person (the ward rule
    of approvals, R2-Q21) → 422 end not after start. The STAFF row is locked
    first, so a plan of the same person sees the period before or after the
    change, never half of it. Nothing else changes: roster rows and offers the
    new period overlaps stay as they are and are only reported. GET /roster
    flags those rows with is_unavailable.
    """
    period = db.get(StaffUnavailability, unavailability_id)
    if period is None:
        raise UnavailabilityNotFoundError(f"No unavailability {unavailability_id}")
    head_nurse = db.scalar(select(Role.id).where(Role.name == HEAD_NURSE_ROLE))
    if head_nurse is None or role_id != head_nurse:
        raise UnavailabilityForbiddenError("Only a head nurse can change a leave period")
    staff_ward = db.scalar(select(Staff.home_ward_id).where(Staff.id == period.staff_id))
    if staff_ward is None or not manages_ward(home_ward_id=home_ward_id, ward_id=staff_ward):
        raise UnavailabilityForbiddenError(
            "The staff member is not a head nurse of the person's ward"
        )

    hard_rule_service.lock_staff(db, [period.staff_id])
    period = db.scalars(
        select(StaffUnavailability)
        .where(StaffUnavailability.id == unavailability_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if end_at <= period.start_at:
        raise InvalidUnavailabilityEndError("end_at must be after the start of the leave")

    previous = period.end_at
    period.end_at = end_at
    audit_service.log(
        db,
        case_id=None,
        actor_id=actor_id,
        action=AuditAction.UNAVAILABILITY_UPDATED,
        entity_type=EntityType.STAFF_UNAVAILABILITY,
        entity_id=period.id,
        payload={
            "unavailability_id": period.id,
            "staff_id": period.staff_id,
            "previous_end_at": None if previous is None else _iso(previous),
            "end_at": _iso(end_at),
        },
    )
    result = EndAtUpdate(
        unavailability=period,
        previous_end_at=previous,
        overlapping_assignment_ids=_overlapping_assignments(
            db, period.start_at, end_at, period.staff_id
        ),
        overlapping_offers=_overlapping_offers(db, period.start_at, end_at, period.staff_id),
    )
    db.commit()
    return result


def _iso(moment: datetime) -> str:
    """Audit times as +07:00, like UNAVAILABILITY_CREATED."""
    return moment.astimezone(clock.APP_TIMEZONE).isoformat()


def _overlaps(start_at: datetime, end_at: datetime) -> tuple[ColumnElement[bool], ...]:
    """The overlap of the UNAVAILABLE hard rule, against SHIFT columns.

    After update_end_at() the period always has an end.
    """
    return (Shift.start_at < end_at, Shift.end_at > start_at)


def _overlapping_assignments(
    db: Session, start_at: datetime, end_at: datetime, staff_id: int
) -> list[int]:
    return list(
        db.scalars(
            select(RosterAssignment.id)
            .join(Shift, Shift.id == RosterAssignment.shift_id)
            .where(
                RosterAssignment.staff_id == staff_id,
                RosterAssignment.status == RosterStatus.ASSIGNED,
                *_overlaps(start_at, end_at),
            )
            .order_by(RosterAssignment.id)
        )
    )


def _overlapping_offers(
    db: Session, start_at: datetime, end_at: datetime, staff_id: int
) -> list[OverlappingOffer]:
    rows = db.execute(
        select(CandidateOutreach.id, CandidateOutreach.case_id, CandidateOutreach.status)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .join(Shift, Shift.id == CandidateItem.proposed_shift_id)
        .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
        .where(
            CandidateItem.staff_id == staff_id,
            CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
            StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            *_overlaps(start_at, end_at),
        )
        .order_by(CandidateOutreach.id)
    ).all()
    return [
        OverlappingOffer(outreach_id=outreach_id, case_id=case_id, status=status)
        for outreach_id, case_id, status in rows
    ]
