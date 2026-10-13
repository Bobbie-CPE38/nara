"""Head nurse rejects 201; 202 then accepts and is approved (contract 6.1)."""

from sqlalchemy.orm import Session

from app.db.models import Staff
from app.domain.enums import StaffStatus

EVENT_STAFF_ID = 105
REJECTED_STAFF_ID = 201
REPLACEMENT_STAFF_ID = 202
APPROVER_STAFF_ID = 900
REJECTION_REASON = "Choose another candidate for this shift"


def seed(db: Session) -> None:
    """Golden Case overlay: ensure both candidates are active; no workflow writes."""
    for staff_id in (REJECTED_STAFF_ID, REPLACEMENT_STAFF_ID):
        staff = db.get(Staff, staff_id)
        if staff is None:
            raise LookupError("Load the Golden Case before this scenario")
        staff.status = StaffStatus.ACTIVE
    db.flush()
