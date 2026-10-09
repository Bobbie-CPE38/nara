from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType
from app.services import actor_service, audit_service, optimization_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub solver: plan the fixed Golden Case candidates, then request outreach."""
    plan, items = optimization_service.create_stub_plan(db, case)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.CONSTRAINT_FAIR_SCHEDULING_AGENT),
        action=AuditAction.SOLVER_EXECUTED,
        entity_type=EntityType.CANDIDATE_PLANS,
        entity_id=plan.id,
        payload={
            "plan_id": plan.id,
            "solver_status": plan.solver_status.value,
            "candidate_count": len(items),
        },
    )
    return HandlerResult(next_status=CaseStatus.OUTREACH)
