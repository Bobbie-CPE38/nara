"""Web accounts for testing that need no LINE (round 6 PR EV7, docs/workflow.md 6.37.9).

A web account is normally made from LINE (REGISTER, 6.33.6) or by the account script. For a
demo that is slow: every tester needs a phone bound to a staff member first. After a demo
reset the Demo control gives these people an account with DEMO_ACCOUNT_PASSWORD, so they
log in at once. Nothing is made while the setting is unset, an existing account (and its
password) is never touched, and accounts are kept across resets like every other (6.33.7).

The password is shared and known to every tester, so by default only nurses get one: a nurse
reads their own shifts and offers, nothing of a ward. A head nurse or the Supervisor can
open every ward, the Demo control and staff management, so their accounts are made only
when DEMO_MANAGER_ACCOUNTS is on as well, on purpose and for a test session.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import auth_clock, passwords
from app.core.config import settings
from app.db.models import AuthAccount, Staff
from app.domain.enums import StaffStatus
from app.seed import hospital_demo
from app.services import auth_service

# The Golden Case: the nurse on leave and the ICU candidates
GOLDEN_NURSES = (105, 201, 202, 203)
# Both head nurses and the Supervisor
GOLDEN_MANAGERS = (900, 902, 950)
# The hospital demo: each ward's first RN, and its head nurse
HOSPITAL_NURSES = tuple(
    hospital_demo.STAFF_BASE + 100 * ward + 2 for ward in range(len(hospital_demo.WARD_NAMES))
)
HOSPITAL_MANAGERS = tuple(
    hospital_demo.STAFF_BASE + 100 * ward + 1 for ward in range(len(hospital_demo.WARD_NAMES))
)


def wanted() -> tuple[int, ...]:
    """The staff IDs that get a test account under the current settings."""
    if settings.demo_account_password is None:
        return ()
    if settings.demo_manager_accounts:
        return (*GOLDEN_NURSES, *GOLDEN_MANAGERS, *HOSPITAL_NURSES, *HOSPITAL_MANAGERS)
    return (*GOLDEN_NURSES, *HOSPITAL_NURSES)


def ensure(db: Session) -> list[int]:
    """Make the missing test accounts in one transaction; return the staff IDs that got one.

    Idempotent: a person who has an account by now, from an overlapping reset or REGISTER,
    is skipped by the insert itself. Commits.
    """
    staff_ids = wanted()
    if not staff_ids:
        return []
    assert settings.demo_account_password is not None
    auth_service.hold_auth_gate(db)
    missing = db.execute(
        select(Staff.id, Staff.auth_subject)
        .outerjoin(AuthAccount, AuthAccount.staff_subject == Staff.auth_subject)
        .where(
            Staff.id.in_(staff_ids),
            Staff.status == StaffStatus.ACTIVE,
            AuthAccount.staff_subject.is_(None),
        )
        .order_by(Staff.id)
    ).all()
    if not missing:
        db.rollback()
        return []
    # One hash for all: they share the password anyway, and Argon2id per person would hold
    # the reset lock for seconds
    password_hash = passwords.hash_password(settings.demo_account_password.get_secret_value())
    now = auth_clock.now()
    created = db.scalars(
        insert(AuthAccount)
        .values(
            [
                {
                    "staff_subject": subject,
                    "password_hash": password_hash,
                    "must_change_password": False,
                    "credential_version": 1,
                    "created_at": now,
                    "updated_at": now,
                    "password_changed_at": now,
                }
                for _, subject in missing
            ]
        )
        .on_conflict_do_nothing(index_elements=[AuthAccount.staff_subject])
        .returning(AuthAccount.staff_subject)
    ).all()
    db.commit()
    made = set(created)
    return [staff_id for staff_id, subject in missing if subject in made]
