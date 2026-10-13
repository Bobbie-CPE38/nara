"""Golden Case with both first-wave candidates declining (round 1 PR 2b).

Load base_data and golden_case first. No extra master data is needed. The test
sends these responses through HTTP: 201 REJECT, 202 REJECT, then 203 ACCEPT.
The first two leave their offers REJECTED; 203 receives Wave 2.
"""

from sqlalchemy.orm import Session

from app.db.models import Staff
from app.domain.enums import StaffStatus
from app.services import policy_service

RESPONSES = ((201, "REJECT"), (202, "REJECT"), (203, "ACCEPT"))


def seed(db: Session) -> None:
    """Ensure the three participants are active and the ordinary cap is three."""
    for staff_id, _ in RESPONSES:
        staff = db.get(Staff, staff_id)
        if staff is None:
            raise LookupError("Load the Golden Case before candidate_reject")
        staff.status = StaffStatus.ACTIVE
    policy_service.get_outreach_policy(db).maximum_concurrent_offers_per_staff = 3
    db.flush()
