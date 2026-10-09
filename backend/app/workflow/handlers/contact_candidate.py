from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.services import outreach_service
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Send the rank-1 mock offer, then pause until the candidate responds."""
    outreach_service.send_offer(db, case)
    return HandlerResult(next_status=CaseStatus.WAITING_RESPONSE, wait=True)
