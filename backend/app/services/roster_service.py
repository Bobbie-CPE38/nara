"""Replacement assignment creation (workflow.md section 6.4, seam 8).

The execution handler owns audit rows; the orchestrator owns status and commit.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidatePlan,
    RosterAssignment,
    Shift,
    StaffingCase,
)
from app.domain.enums import AssignmentType, RosterStatus
from app.services import availability_service


def create_replacement(db: Session, case: StaffingCase) -> RosterAssignment:
    """Create from exactly one completed, approved request, never commit.

    Flush the caller's decision first: production sessions disable autoflush.
    Follow the request's item, rather than a newer plan or a rank-1 lookup.
    Reject inconsistent case/plan/shift references before creating a roster row.
    Errors propagate to the orchestrator's D11 handling; do not catch and continue.
    """
    db.flush()
    approval = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.case_id == case.id,
            ApprovalRequest.is_pending.is_(False),
            ApprovalRequest.is_approved.is_(True),
        )
    ).one()
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
    # Availability may change while the approval waits. Use Safety's same rules.
    availability_service.assert_available(db, shift, item.staff_id)

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
