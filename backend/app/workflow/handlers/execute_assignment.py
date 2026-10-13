"""Finish an already staffed case; assignments are created per approval."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    StaffingCase,
)
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    CaseStatus,
    EntityType,
    OutreachStatus,
    RosterStatus,
)
from app.services import actor_service, audit_service, case_facts_service, outreach_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Verify assigned coverage, cancel unused offers, audit and resolve; no commit.

    Runs under the decision/response locks. Never creates another roster row.
    Approved candidates keep their ACCEPTED offers as assignment history.
    """
    db.flush()
    if not case_facts_service.load_case_facts(db, case).gap_closed_by_assigned:
        raise ValueError("Cannot resolve a case whose assigned candidates do not close its gap")
    assignments = list(
        db.scalars(
            select(RosterAssignment)
            .join(
                CandidateItem,
                (CandidateItem.staff_id == RosterAssignment.staff_id)
                & (CandidateItem.proposed_shift_id == RosterAssignment.shift_id),
            )
            .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
            .where(
                ApprovalRequest.case_id == case.id,
                ApprovalRequest.is_pending.is_(False),
                ApprovalRequest.is_approved.is_(True),
                RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
                RosterAssignment.status.in_([RosterStatus.ASSIGNED, RosterStatus.COMPLETED]),
            )
            .distinct()
            .order_by(RosterAssignment.id)
        )
    )
    assigned_staff = {row.staff_id for row in assignments}
    rows = list(
        db.execute(
            select(CandidateOutreach, CandidateItem.staff_id)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
            )
            .order_by(CandidateOutreach.id)
        )
    )
    cancelled = []
    for offer, staff_id in rows:
        if offer.status == OutreachStatus.SENT or staff_id not in assigned_staff:
            outreach_service.cancel_offer(db, offer)
            cancelled.append(offer.id)
    db.flush()
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.CASE_RESOLVED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            "assignment_ids": [row.id for row in assignments],
            "cancelled_outreach_ids": cancelled,
        },
    )
    return HandlerResult(next_status=CaseStatus.RESOLVED)
