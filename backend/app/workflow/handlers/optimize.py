from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub: assume candidates exist and request outreach."""
    return HandlerResult(next_status=CaseStatus.OUTREACH)
