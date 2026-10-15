"""Replacement assignment creation (workflow.md section 6.4, seam 8) and the
roster reads of a shift and of a staff member (sections 9.3 and 9.5).

The execution handler owns audit rows; the orchestrator owns status and commit.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidatePlan,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffUnavailability,
    Ward,
)
from app.domain.enums import AssignmentType, RosterStatus
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.roster import (
    RosterRow,
    RosterShift,
    RosterStaff,
    ShiftRoster,
    StaffRoster,
    StaffRosterRow,
)
from app.services import roster_time_service
from app.services.unavailability_service import leave_overlaps_shift_sql


def _approved_item(
    db: Session, case: StaffingCase, approval: ApprovalRequest
) -> tuple[CandidateItem, Shift]:
    """The approved request's item and its shift, after the checks both writers share."""
    db.flush()
    if approval.case_id != case.id or approval.is_pending or approval.is_approved is not True:
        raise ValueError("Replacement requires a decided, approved request of this case")
    item = db.get(CandidateItem, approval.candidate_item_id)
    if item is None:
        raise LookupError(f"No candidate item {approval.candidate_item_id}")
    plan = db.get(CandidatePlan, item.plan_id)
    if plan is None or plan.case_id != case.id:
        raise ValueError("Approved candidate plan does not belong to this case")
    if item.proposed_shift_id != case.shift_id:
        raise ValueError("Approved candidate shift does not match this case")

    shift = db.get(Shift, item.proposed_shift_id)
    if shift is None:
        raise LookupError(f"No shift {item.proposed_shift_id}")
    return item, shift


def create_replacement(
    db: Session, case: StaffingCase, *, approval: ApprovalRequest
) -> RosterAssignment:
    """Create the selected approval's replacement in the decision transaction.

    Caller holds Shift, Request, Offer, case and Staff locks. No commit or audit.
    Do not recheck Hard Rules at execution (Q38); Safety owns that check.

    This creates the destination row only. A move out of another shift
    (item.source_assignment_id) goes through create_transfer, which also cancels
    or cuts the source row; this writer refuses it, so one person is never left on
    two overlapping shifts without a link.
    """
    item, shift = _approved_item(db, case, approval)
    if item.source_assignment_id is not None:
        raise ValueError("A move needs create_transfer")

    start, end = roster_time_service.effective_interval(
        shift_start_at=shift.start_at,
        shift_end_at=shift.end_at,
        actual_start_at=item.cover_start_at,
        actual_end_at=item.cover_end_at,
    )
    whole_shift = start == shift.start_at and end == shift.end_at
    assignment = RosterAssignment(
        staff_id=item.staff_id,
        shift_id=item.proposed_shift_id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        candidate_source=item.source,
        actual_start_at=None if whole_shift else item.cover_start_at,
        actual_end_at=None if whole_shift else item.cover_end_at,
    )
    db.add(assignment)
    db.flush()
    return assignment


def create_transfer(
    db: Session, case: StaffingCase, *, approval: ApprovalRequest, transfer_at: datetime
) -> tuple[RosterAssignment, RosterAssignment]:
    """Move the approved person off their source row onto this case's shift.

    Returns (destination, source). Caller holds the locks and has already run the
    transfer checks (transfer_service.execute). No commit, audit or checks here.

    A transfer at or before the source row's effective start cancels it. Later
    than that the source row stays ASSIGNED and ends at `transfer_at`; that branch
    is the mid-shift move of PR C3 and is not reachable in C2.
    """
    item, shift = _approved_item(db, case, approval)
    if item.source_assignment_id is None:
        raise ValueError("A transfer needs a source assignment")
    source = db.get(RosterAssignment, item.source_assignment_id, populate_existing=True)
    if source is None:
        raise LookupError(f"No roster assignment {item.source_assignment_id}")
    source_shift = db.get(Shift, source.shift_id)
    if source_shift is None:
        raise LookupError(f"No shift {source.shift_id}")

    source_start, _ = roster_time_service.effective_interval(
        shift_start_at=source_shift.start_at,
        shift_end_at=source_shift.end_at,
        actual_start_at=source.actual_start_at,
        actual_end_at=source.actual_end_at,
    )
    if transfer_at <= source_start:
        source.status = RosterStatus.CANCELLED
    else:
        roster_time_service.effective_interval(
            shift_start_at=source_shift.start_at,
            shift_end_at=source_shift.end_at,
            actual_start_at=source.actual_start_at,
            actual_end_at=transfer_at,
        )
        source.actual_end_at = transfer_at

    actual_start = transfer_at if transfer_at > shift.start_at else None
    roster_time_service.effective_interval(
        shift_start_at=shift.start_at,
        shift_end_at=shift.end_at,
        actual_start_at=actual_start,
        actual_end_at=None,
    )
    destination = RosterAssignment(
        staff_id=item.staff_id,
        shift_id=shift.id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        candidate_source=item.source,
        actual_start_at=actual_start,
        transferred_from_assignment_id=source.id,
    )
    db.add(destination)
    db.flush()
    return destination, source


def get_shift_roster(db: Session, shift_id: int) -> ShiftRoster:
    """Read the shift and every roster row on it, without flushes, commits or locks.

    Rows come back in every status, as stored, ordered by ID. Nothing is hidden,
    de-duplicated or counted here: coverage belongs to the gap calculator.
    Two statements whatever the number of rows. Staff columns are named one by
    one, so email and password_hash are never loaded.
    """
    found = db.execute(
        select(Shift, Ward.name).join(Ward, Ward.id == Shift.ward_id).where(Shift.id == shift_id)
    ).first()
    if found is None:
        raise ShiftNotFoundError(f"No shift {shift_id}")
    shift, ward_name = found

    home_ward = aliased(Ward)
    rows = db.execute(
        select(
            RosterAssignment.id,
            RosterAssignment.status,
            RosterAssignment.assignment_type,
            RosterAssignment.candidate_source,
            RosterAssignment.actual_start_at,
            RosterAssignment.actual_end_at,
            RosterAssignment.transferred_from_assignment_id,
            RosterAssignment.staff_id,
            RosterAssignment.created_at,
            RosterAssignment.updated_at,
            _is_unavailable(roster_time_service.start_at(), roster_time_service.end_at()).label(
                "is_unavailable"
            ),
            Staff.first_name,
            Staff.last_name,
            Staff.status.label("staff_status"),
            Staff.role_id,
            Role.name.label("role_name"),
            Staff.home_ward_id,
            home_ward.name.label("home_ward_name"),
        )
        .join(Staff, Staff.id == RosterAssignment.staff_id)
        .join(Role, Role.id == Staff.role_id)
        .join(home_ward, home_ward.id == Staff.home_ward_id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(RosterAssignment.shift_id == shift.id)
        # By id, never a time column: the demo clock is frozen (section 6.4)
        .order_by(RosterAssignment.id)
    ).mappings()
    return ShiftRoster(
        shift=RosterShift(
            id=shift.id,
            ward_id=shift.ward_id,
            ward_name=ward_name,
            shift_type=shift.shift_type,
            start_at=shift.start_at,
            end_at=shift.end_at,
            is_active=shift.is_active,
        ),
        assignments=[RosterRow.model_validate(row) for row in rows],
    )


def get_staff_roster(db: Session, staff_id: int) -> StaffRoster:
    """Read the staff member and every roster row they hold, without flushes, commits or locks.

    Rows come back in every status, ordered by effective start, then row ID: a
    person's shifts read as a timeline. Two statements whatever the number of
    rows. Only the staff columns the answer needs are loaded.
    """
    found = (
        db.execute(
            select(
                Staff.id,
                Staff.first_name,
                Staff.last_name,
                Staff.status.label("staff_status"),
                Staff.role_id,
                Role.name.label("role_name"),
                Staff.home_ward_id,
                Ward.name.label("home_ward_name"),
            )
            .join(Role, Role.id == Staff.role_id)
            .join(Ward, Ward.id == Staff.home_ward_id)
            .where(Staff.id == staff_id)
        )
        .mappings()
        .first()
    )
    if found is None:
        raise StaffNotFoundError(f"No staff {staff_id}")

    rows = db.execute(
        select(
            RosterAssignment.id,
            RosterAssignment.status,
            RosterAssignment.assignment_type,
            RosterAssignment.candidate_source,
            RosterAssignment.actual_start_at,
            RosterAssignment.actual_end_at,
            RosterAssignment.transferred_from_assignment_id,
            RosterAssignment.created_at,
            RosterAssignment.updated_at,
            _is_unavailable(roster_time_service.start_at(), roster_time_service.end_at()).label(
                "is_unavailable"
            ),
            Shift.id.label("shift_id"),
            Shift.ward_id,
            Ward.name.label("ward_name"),
            Shift.shift_type,
            Shift.start_at,
            Shift.end_at,
            Shift.is_active,
        )
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .join(Ward, Ward.id == Shift.ward_id)
        .where(RosterAssignment.staff_id == staff_id)
        .order_by(roster_time_service.start_at(), RosterAssignment.id)
    ).mappings()
    return StaffRoster(
        staff=RosterStaff.model_validate(found),
        assignments=[
            StaffRosterRow(
                id=row["id"],
                status=row["status"],
                assignment_type=row["assignment_type"],
                candidate_source=row["candidate_source"],
                actual_start_at=row["actual_start_at"],
                actual_end_at=row["actual_end_at"],
                transferred_from_assignment_id=row["transferred_from_assignment_id"],
                shift=RosterShift(
                    id=row["shift_id"],
                    ward_id=row["ward_id"],
                    ward_name=row["ward_name"],
                    shift_type=row["shift_type"],
                    start_at=row["start_at"],
                    end_at=row["end_at"],
                    is_active=row["is_active"],
                ),
                is_unavailable=row["is_unavailable"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ],
    )


def _is_unavailable(
    shift_start: datetime | InstrumentedAttribute[datetime] | ColumnElement[datetime],
    shift_end: datetime | InstrumentedAttribute[datetime] | ColumnElement[datetime],
) -> ColumnElement[bool]:
    """ASSIGNED, and a leave period of the row's person overlaps the shift.

    The overlap is unavailability_service.leave_overlaps_shift_sql(), the UNAVAILABLE
    hard rule in SQL. Evaluated in the row query, so the read stays at two statements.
    """
    return and_(
        RosterAssignment.status == RosterStatus.ASSIGNED,
        exists().where(
            StaffUnavailability.staff_id == RosterAssignment.staff_id,
            leave_overlaps_shift_sql(
                StaffUnavailability.start_at, StaffUnavailability.end_at, shift_start, shift_end
            ),
        ),
    )
