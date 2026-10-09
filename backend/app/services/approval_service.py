"""Approval decisions for the Golden Path; the orchestrator owns the commit."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import ApprovalRequest, StaffingCase
from app.domain.enums import AuditAction, CaseStatus, EntityType
from app.services import audit_service
from app.workflow import orchestrator


class ApprovalNotFoundError(LookupError):
    """No approval request has this ID."""


class ApproverRoleError(ValueError):
    """The authenticated staff member does not have the required role."""


class ApprovalNotPendingError(ValueError):
    """The request has already been decided."""


class UnsupportedApprovalDecisionError(ValueError):
    """The skeleton has no transition for declining approval yet."""


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
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise ApprovalNotFoundError(f"No approval request {approval_id}")
    if role_id != request.required_approver_role:
        raise ApproverRoleError("The staff member does not have the required approver role")
    if not request.is_pending:
        raise ApprovalNotPendingError(f"Approval request {approval_id} is not pending")
    if not isinstance(approved, bool):
        raise TypeError("approved must be a bool")
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
