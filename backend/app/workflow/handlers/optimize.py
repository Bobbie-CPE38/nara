from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.staffing_case import StaffingCase
from app.domain.enums import (
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    ManualHandoffReason,
    SolverStatus,
)
from app.services import actor_service, audit_service, explanation_service, optimization_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Plan the candidates of the case, or stop it when nobody can take the shift (T6)."""
    result = optimization_service.create_plan(db, case)
    actor_id = actor_service.component_id(db, ActorName.CONSTRAINT_FAIR_SCHEDULING_AGENT)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.SOLVER_EXECUTED,
        entity_type=EntityType.CANDIDATE_PLANS,
        entity_id=result.plan.id,
        payload={
            "plan_id": result.plan.id,
            "solver_status": result.plan.solver_status.value,
            "candidate_count": len(result.items),
        },
    )
    if settings.llm_enabled and result.items:
        # A small PENDING row in this transaction; the Job writes the sentence later (PR X)
        explanation_service.enqueue(db, result.plan, candidate_count=len(result.items))
    if result.items:
        return HandlerResult(next_status=CaseStatus.OUTREACH)

    # Not a system fault, so not FAILED: a person has to staff the shift (Q2)
    reason = (
        ManualHandoffReason.SOLVER_TIMEOUT
        if result.plan.solver_status is SolverStatus.UNKNOWN
        else ManualHandoffReason.NO_FEASIBLE_PLAN
    )
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.MANUAL_HANDOFF,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            "reason": reason.value,
            "stopped_at": CaseStatus.OPTIMIZING.value,
            "cancelled_outreach_ids": [],
            "skipped": [{"staff_id": row.staff_id, "reason": row.reason} for row in result.skipped],
        },
    )
    return HandlerResult(next_status=CaseStatus.MANUAL_HANDOFF)
