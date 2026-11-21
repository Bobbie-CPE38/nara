"""LINE REGISTER and atomic web signup (workflow 6.33.6).

Preflight owns a short read transaction and closes it before hashing. Caller owns
commit/rollback of the final consume. Lock order: shared reset gate → Staff → registration
codes → Contacts → account. Staff serializes issuance, signup, provisioning and LINK
unlink. Never persist raw codes, UIDs, messages or passwords. No session is issued.
"""

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import auth_clock, passwords
from app.core.rate_limit import REGISTER_ISSUE_PER_SUBJECT, Limit, RateLimiter
from app.db.models import Actor, AuthAccount, AuthRegistrationCode, Contact, Staff
from app.domain.enums import ActorType, StaffStatus
from app.services import auth_service

CODE_LIFETIME = timedelta(seconds=600)
_CODE = re.compile(r"[A-Za-z0-9_-]{32}\Z")
issue_limiter = RateLimiter()


class RegistrationError(ValueError):
    """Generic refusal; never include submitted data."""


class AlreadyRegisteredError(RegistrationError):
    pass


class IssuanceLimitedError(RegistrationError):
    pass


@dataclass(frozen=True)
class RegistrationCode:
    code: SecretStr
    expires_at: datetime


def code_digest(code: str) -> str:
    return hashlib.sha256(b"AUTH_REGISTER\x00" + code.encode()).hexdigest()


def uid_digest(uid: str) -> str:
    return hashlib.sha256(b"AUTH_REGISTER_UID\x00" + uid.encode()).hexdigest()


@dataclass(frozen=True)
class RegistrationPreflight:
    subject: uuid.UUID
    code_hash: str
    eligible: bool


def prepare_registration(db: Session, code: str) -> RegistrationPreflight | None:
    """Read-only early rejection, not authorization. End this transaction before Argon2.

    Keep only immutable values; the locked consume must recheck everything after hashing.
    Like auth_service's login/resolve, this helper owns its short transaction. Call with
    no pending writes. The route counts attempts for a known subject even if ineligible.
    """
    try:
        auth_service.hold_auth_gate(db)
        if _CODE.fullmatch(code) is None:
            return None
        row = db.execute(
            select(AuthRegistrationCode, Staff, Contact, Actor.id, AuthAccount.staff_subject)
            .join(Staff, Staff.auth_subject == AuthRegistrationCode.staff_subject)
            .outerjoin(Contact, Contact.id == AuthRegistrationCode.contact_id)
            .outerjoin(Actor, (Actor.staff_id == Staff.id) & (Actor.actor_type == ActorType.USER))
            .outerjoin(AuthAccount, AuthAccount.staff_subject == Staff.auth_subject)
            .where(AuthRegistrationCode.code_hash == code_digest(code))
            .execution_options(populate_existing=True)
        ).first()
        if row is None:
            return None
        proof, staff, contact, actor_id, account_subject = row
        eligible = bool(
            proof.used_at is None
            and proof.revoked_at is None
            and auth_clock.now() < proof.expires_at
            and staff.status == StaffStatus.ACTIVE
            and actor_id is not None
            and account_subject is None
            and contact is not None
            and contact.is_active
            and contact.staff_id == staff.id
            and contact.line_uid
            and hmac.compare_digest(uid_digest(contact.line_uid), proof.line_uid_hash)
        )
        return RegistrationPreflight(proof.staff_subject, proof.code_hash, eligible)
    finally:
        # Release shared gate and relation locks, including when preflight is refused.
        db.rollback()


def _staff(db: Session, subject: uuid.UUID) -> Staff:
    staff = db.scalar(
        select(Staff)
        .where(Staff.auth_subject == subject)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if staff is None or staff.status != StaffStatus.ACTIVE:
        raise RegistrationError("Registration unavailable")
    if (
        db.scalar(
            select(Actor.id).where(Actor.staff_id == staff.id, Actor.actor_type == ActorType.USER)
        )
        is None
    ):
        raise RegistrationError("Registration unavailable")
    return staff


def revoke_codes(db: Session, subject: uuid.UUID) -> int:
    """Staff must already be locked, before Contacts. Also used by explicit unlink."""
    revoked = db.scalars(
        update(AuthRegistrationCode)
        .where(
            AuthRegistrationCode.staff_subject == subject,
            AuthRegistrationCode.used_at.is_(None),
            AuthRegistrationCode.revoked_at.is_(None),
        )
        .values(revoked_at=auth_clock.now())
        .returning(AuthRegistrationCode.id)
        .execution_options(synchronize_session=False)
    )

    return len(revoked.all())


def issue(db: Session, uid: str) -> RegistrationCode:
    auth_service.hold_auth_gate(db)
    subject = db.scalar(
        select(Staff.auth_subject)
        .join(Contact, Contact.staff_id == Staff.id)
        .where(Contact.line_uid == uid, Contact.is_active.is_(True))
    )
    if subject is None:
        raise RegistrationError("Registration unavailable")
    staff = _staff(db, subject)
    wait = issue_limiter.hit([Limit(f"register:issue:{subject}", REGISTER_ISSUE_PER_SUBJECT)])
    if wait is not None:
        raise IssuanceLimitedError("Try again later")
    # Before Contacts: every code mutation follows the same lock order as consumption.
    revoke_codes(db, subject)
    contact = db.scalar(
        select(Contact)
        .where(Contact.staff_id == staff.id, Contact.line_uid == uid, Contact.is_active.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if contact is None:
        raise RegistrationError("Registration unavailable")
    if db.get(AuthAccount, subject) is not None:
        raise AlreadyRegisteredError("Account already exists")
    now = auth_clock.now()
    raw = secrets.token_urlsafe(24)
    db.add(
        AuthRegistrationCode(
            staff_subject=subject,
            code_hash=code_digest(raw),
            contact_id=contact.id,
            line_uid_hash=uid_digest(uid),
            created_at=now,
            expires_at=now + CODE_LIFETIME,
        )
    )
    db.flush()
    return RegistrationCode(SecretStr(raw), now + CODE_LIFETIME)


def register(db: Session, code: str, password: str) -> int:
    """Service entry point; API can reuse its rate-limited preflight instead."""
    return complete_registration(db, prepare_registration(db, code), password)


def complete_registration(
    db: Session, prepared: RegistrationPreflight | None, password: str
) -> int:
    if prepared is None or not prepared.eligible:
        raise RegistrationError("Registration unavailable")
    if db.in_transaction():
        raise RuntimeError("Registration hashing requires a closed preflight transaction")
    password_hash = passwords.hash_password(password)
    # Hashing may have taken time: never trust the preflight's eligibility here.
    auth_service.hold_auth_gate(db)
    subject = prepared.subject
    staff = _staff(db, subject)
    row = db.scalar(
        select(AuthRegistrationCode)
        .where(AuthRegistrationCode.code_hash == prepared.code_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.staff_subject != subject or row.used_at or row.revoked_at:
        raise RegistrationError("Registration unavailable")
    contact = db.scalar(
        select(Contact)
        .where(Contact.id == row.contact_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = auth_clock.now()
    if (
        now >= row.expires_at
        or contact is None
        or not contact.is_active
        or contact.staff_id != staff.id
        or not contact.line_uid
        or not hmac.compare_digest(uid_digest(contact.line_uid), row.line_uid_hash)
        or db.get(AuthAccount, subject) is not None
    ):
        raise RegistrationError("Registration unavailable")
    db.add(
        AuthAccount(
            staff_subject=subject,
            password_hash=password_hash,
            must_change_password=False,
            credential_version=1,
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )
    )
    row.used_at = now
    db.flush()
    return staff.id
