from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub: request a pause until the candidate responds; no offer is sent yet."""
    return HandlerResult(next_status=CaseStatus.WAITING_RESPONSE, wait=True)
