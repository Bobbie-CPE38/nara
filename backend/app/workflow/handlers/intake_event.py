from sqlalchemy.orm import Session

from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Stub: request the initial assessment of an opened case."""
    return HandlerResult(next_status=CaseStatus.ASSESSING)
