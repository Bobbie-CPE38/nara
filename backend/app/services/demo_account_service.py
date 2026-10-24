"""Web accounts for testing that need no LINE (round 6 PR EV7, docs/workflow.md 6.37.9).

A web account is normally made from LINE (REGISTER, 6.33.6) or by the account script. For a
demo that is slow: every tester needs a phone bound to a staff member first. After a demo
reset the Demo control gives these people an account with DEMO_ACCOUNT_PASSWORD, so they
log in at once. Nothing is made while the setting is unset, an existing account (and its
password) is never touched, and accounts are kept across resets like every other (6.33.7).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuthAccount, Staff
from app.domain.enums import StaffStatus
from app.seed import hospital_demo
from app.services import auth_service

# The Golden Case: the nurse on leave, the ICU candidates, both head nurses, the Supervisor
GOLDEN_STAFF = (105, 201, 202, 203, 900, 902, 950)
# The hospital demo: each ward's head nurse and its first RN
HOSPITAL_STAFF = tuple(
    hospital_demo.STAFF_BASE + 100 * ward + ordinal
    for ward in range(len(hospital_demo.WARD_NAMES))
    for ordinal in (1, 2)
)


def ensure(db: Session) -> list[int]:
    """Make the missing test accounts; return the staff IDs that got one. Commits."""
    if settings.demo_account_password is None:
        return []
    password = settings.demo_account_password.get_secret_value()
    wanted = (*GOLDEN_STAFF, *HOSPITAL_STAFF)
    rows = db.execute(
        select(Staff.id, AuthAccount.staff_subject)
        .outerjoin(AuthAccount, AuthAccount.staff_subject == Staff.auth_subject)
        .where(Staff.id.in_(wanted), Staff.status == StaffStatus.ACTIVE)
        .order_by(Staff.id)
    ).all()
    db.rollback()
    created: list[int] = []
    for staff_id, account in rows:
        if account is None:
            auth_service.create_account(db, staff_id, password, must_change_password=False)
            created.append(staff_id)
    return created
