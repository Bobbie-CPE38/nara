from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType
from app.services import actor_service, audit_service, roster_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Create the approved replacement and request resolution without committing."""
    assignment = roster_service.create_replacement(db, case)
    actor_id = actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.ASSIGNMENT_CREATED,
        entity_type=EntityType.ROSTER_ASSIGNMENT,
        entity_id=assignment.id,
        payload={
            "assignment_id": assignment.id,
            "staff_id": assignment.staff_id,
            "assignment_type": assignment.assignment_type.value,
        },
    )
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.CASE_RESOLVED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={"assignment_ids": [assignment.id]},
    )
    return HandlerResult(next_status=CaseStatus.RESOLVED)
