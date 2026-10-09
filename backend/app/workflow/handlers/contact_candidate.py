from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType
from app.services import actor_service, audit_service, outreach_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Send the rank-1 mock offer, then pause until the candidate responds."""
    outreach, staff_id = outreach_service.send_offer(db, case)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.OUTREACH_AGENT),
        action=AuditAction.OFFER_SENT,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=outreach.id,
        payload={
            "outreach_id": outreach.id,
            "staff_id": staff_id,
            "channel": outreach.channel.value,
        },
    )
    return HandlerResult(next_status=CaseStatus.WAITING_RESPONSE, wait=True)
