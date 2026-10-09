from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub: assume safety passes and pause for approval; no request is created yet."""
    return HandlerResult(next_status=CaseStatus.WAITING_APPROVAL, wait=True)
