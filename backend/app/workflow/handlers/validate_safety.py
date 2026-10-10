from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType
from app.services import actor_service, audit_service, safety_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub safety: pass the accepted candidate, then wait for a manual approval."""
    validation, approval, candidate = safety_service.validate_accepted_candidate(db, case)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.SAFETY_RULE_ENGINE),
        action=AuditAction.SAFETY_PASSED,
        entity_type=EntityType.SAFETY_VALIDATION,
        entity_id=validation.id,
        payload={"validation_id": validation.id, "staff_id": candidate.staff_id},
    )
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.APPROVAL_REQUESTED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=approval.id,
        payload={"approval_id": approval.id, "approval_mode": approval.approval_mode.value},
    )
    return HandlerResult(next_status=CaseStatus.WAITING_APPROVAL, wait=True)
