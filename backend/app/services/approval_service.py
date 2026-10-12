"""Approval requests: opened after Safety passes, listed, and decided.

The orchestrator owns decision commits."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE
from app.db.models import ApprovalRequest, CandidateItem, CandidatePlan, Role, StaffingCase
from app.domain.enums import ActorName, ApprovalMode, AuditAction, CaseStatus, EntityType
from app.schemas.approval import PendingApproval
from app.services import actor_service, audit_service
from app.workflow import orchestrator


class ApprovalNotFoundError(LookupError):
    """No approval request has this ID."""


class ApproverRoleError(ValueError):
    """The authenticated staff member does not have the required role."""


class ApprovalNotPendingError(ValueError):
    """The request has already been decided."""


class UnsupportedApprovalDecisionError(ValueError):
    """The skeleton has no transition for declining approval yet."""


def create_request(db: Session, *, case: StaffingCase, item: CandidateItem) -> ApprovalRequest:
    """Open the pending MANUAL request of one candidate who passed Safety (seam 5).

    safety_service calls this inside the transaction of the answer. Flushes and
    writes APPROVAL_REQUESTED. Never commits and never changes case.status.
    """
    # The two foreign keys do not prove the item was planned for this case
    plan = db.get(CandidatePlan, item.plan_id)
    if plan is None or plan.case_id != case.id:
        raise ValueError(f"Candidate item {item.id} does not belong to case {case.id}")
    request = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=db.scalars(
            select(Role.id).where(Role.name == HEAD_NURSE_ROLE)
        ).one(),
        approval_mode=ApprovalMode.MANUAL,
        is_pending=True,
        approver_id=None,
        is_approved=None,
        reason=None,
        decided_at=None,
        requested_at=clock.now(),
    )
    db.add(request)
    # The audit row needs the id, and SessionLocal has autoflush off
    db.flush()
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.APPROVAL_REQUESTED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=request.id,
        payload={"approval_id": request.id, "approval_mode": request.approval_mode.value},
    )
    return request


def decide(
    db: Session,
    *,
    approval_id: int,
    staff_id: int,
    role_id: int,
    actor_id: int,
    approved: bool,
    reason: str | None = None,
) -> tuple[ApprovalRequest, StaffingCase]:
    """Check 404 / 403 / 409 / 422 in order, record approval, then resume.

    Lock the approval request before resume() locks the case. Refresh ORM state
    after waiting, so concurrent decisions cannot overwrite the first answer.
    Neither this function nor the route commits or changes case.status. Errors
    must propagate so closing the request session rolls back any flushed work.
    """
    request = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise ApprovalNotFoundError(f"No approval request {approval_id}")
    if role_id != request.required_approver_role:
        raise ApproverRoleError("The staff member does not have the required approver role")
    if not request.is_pending:
        raise ApprovalNotPendingError(f"Approval request {approval_id} is not pending")
    if not approved:
        raise UnsupportedApprovalDecisionError(
            "Declining approval is not supported in the walking skeleton"
        )
    request.approver_id = staff_id
    request.is_approved = True
    request.reason = reason
    request.decided_at = clock.now()
    request.is_pending = False
    audit_service.log(
        db,
        case_id=request.case_id,
        actor_id=actor_id,
        action=AuditAction.APPROVAL_APPROVED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=request.id,
        payload={"approval_id": request.id, "reason": reason},
    )
    orchestrator.resume(db, request.case_id, CaseStatus.EXECUTING)
    case = db.get(StaffingCase, request.case_id)
    # resume() already loaded and locked this case successfully.
    assert case is not None
    return request, case


def list_pending(db: Session) -> list[PendingApproval]:
    """Read all pending requests by ID, without flushes, commits or locks.

    Do not hide other cases when a case has duplicate pending requests. Any
    uniqueness enforcement belongs at creation, not on this list read.
    Include the approved candidate's identity and proposed shift for the UI.
    """
    rows = db.execute(
        select(
            ApprovalRequest.id,
            ApprovalRequest.case_id,
            ApprovalRequest.candidate_item_id,
            ApprovalRequest.required_approver_role,
            ApprovalRequest.approval_mode,
            ApprovalRequest.is_pending,
            ApprovalRequest.requested_at,
            CandidateItem.staff_id,
            CandidateItem.proposed_shift_id,
        )
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .where(ApprovalRequest.is_pending.is_(True))
        .order_by(ApprovalRequest.id)
    ).mappings()
    return [PendingApproval.model_validate(row) for row in rows]
