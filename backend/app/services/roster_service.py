"""Replacement assignment creation (workflow.md section 6.4, seam 8) and the
roster read of a shift (section 9.3).

The execution handler owns audit rows; the orchestrator owns status and commit.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidatePlan,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    Ward,
)
from app.domain.enums import AssignmentType, RosterStatus
from app.domain.errors import ShiftNotFoundError
from app.schemas.roster import RosterRow, RosterShift, ShiftRoster


def create_replacement(
    db: Session, case: StaffingCase, *, approval: ApprovalRequest
) -> RosterAssignment:
    """Create the selected approval's replacement in the decision transaction.

    Caller holds Shift, Request, Offer, case and Staff locks. No commit or audit.
    Do not recheck Hard Rules at execution (Q38); Safety owns that check.
    """
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

    assignment = RosterAssignment(
        staff_id=item.staff_id,
        shift_id=item.proposed_shift_id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        candidate_source=item.source,
    )
    db.add(assignment)
    db.flush()
    return assignment


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
            RosterAssignment.staff_id,
            RosterAssignment.created_at,
            RosterAssignment.updated_at,
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
