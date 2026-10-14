"""Local administrator operations and signed LINK consumption (workflow 6.16).

Never commits: the caller commits issuance/unlinking, and the webhook commits
LINK with its dedup row. Lock order is Staff → link code → that staff's Contacts.
No Offer/Case locks are taken. Raw codes and LINE UIDs must not be logged/audited.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import MAX_BIGINT
from app.db.models import Contact, LineAccountLinkCode, Staff
from app.domain.enums import ActorName, AuditAction, EntityType, StaffStatus
from app.services import actor_service, audit_service

CODE_LIFETIME = timedelta(minutes=10)
_CODE = re.compile(r"[A-Za-z0-9_-]{32}\Z")


class LineAccountError(ValueError):
    """Expected refusal; messages contain no secret or LINE identity."""


class InvalidLinkCodeError(LineAccountError):
    pass


class LineAccountAlreadyBoundError(LineAccountError):
    pass


class LinkStaffUnavailableError(LineAccountError):
    pass


@dataclass(frozen=True)
class IssuedCode:
    code: SecretStr
    expires_at: datetime


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _lock_staff(db: Session, staff_id: int, *, require_active: bool = True) -> Staff:
    if isinstance(staff_id, bool) or not 1 <= staff_id <= MAX_BIGINT:
        raise LinkStaffUnavailableError("Invalid staff ID")
    staff = db.scalar(
        select(Staff)
        .where(Staff.id == staff_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if staff is None or (require_active and staff.status != StaffStatus.ACTIVE):
        raise LinkStaffUnavailableError("Staff is missing or inactive")
    return staff


def _user_actor(db: Session, staff_id: int) -> int:
    try:
        return actor_service.user_id(db, staff_id)
    except actor_service.ActorNotFoundError:
        raise LinkStaffUnavailableError("Staff has no user actor") from None


def _contacts(db: Session, staff_id: int) -> list[Contact]:
    return list(
        db.scalars(
            select(Contact)
            .where(Contact.staff_id == staff_id)
            .order_by(Contact.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def issue_code(db: Session, staff_id: int) -> IssuedCode:
    _lock_staff(db, staff_id)
    _user_actor(db, staff_id)
    # Refuse existing bindings, including inactive ones: explicit unlink is required.
    if db.scalar(
        select(Contact.id)
        .where(Contact.staff_id == staff_id, Contact.line_uid.is_not(None))
        .limit(1)
    ):
        raise LineAccountAlreadyBoundError("Unlink the existing LINE account first")
    now = clock.now()
    raw = secrets.token_urlsafe(24)  # 192 random bits; 32 case-sensitive ASCII characters.
    db.add(
        LineAccountLinkCode(
            staff_id=staff_id,
            code_hash=hash_code(raw),
            created_at=now,
            expires_at=now + CODE_LIFETIME,
        )
    )
    db.flush()
    return IssuedCode(SecretStr(raw), now + CODE_LIFETIME)


def link(db: Session, code: str, uid: str) -> Contact:
    if not _CODE.fullmatch(code) or not uid or len(uid) > 255:
        raise InvalidLinkCodeError("Invalid link code or LINE sender")
    code_id = db.scalar(
        select(LineAccountLinkCode.id).where(LineAccountLinkCode.code_hash == hash_code(code))
    )
    if code_id is None:
        raise InvalidLinkCodeError("Invalid link code")
    staff_id = db.scalar(
        select(LineAccountLinkCode.staff_id).where(LineAccountLinkCode.id == code_id)
    )
    if staff_id is None:
        raise InvalidLinkCodeError("Invalid link code")
    _lock_staff(db, staff_id)
    actor_id = _user_actor(db, staff_id)
    row = db.scalar(
        select(LineAccountLinkCode)
        .where(LineAccountLinkCode.id == code_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = clock.now()
    if (
        row is None
        or row.used_at is not None
        or row.revoked_at is not None
        or now >= row.expires_at
    ):
        raise InvalidLinkCodeError("Link code is expired, used or revoked")
    contacts = _contacts(db, staff_id)
    if any(item.line_uid is not None for item in contacts):
        raise LineAccountAlreadyBoundError("Unlink the existing LINE account first")
    if db.scalar(select(Contact.id).where(Contact.line_uid == uid).limit(1)) is not None:
        raise LineAccountAlreadyBoundError("LINE account is already linked")
    consumed = db.scalar(
        update(LineAccountLinkCode)
        .where(
            LineAccountLinkCode.id == row.id,
            LineAccountLinkCode.used_at.is_(None),
            LineAccountLinkCode.revoked_at.is_(None),
            LineAccountLinkCode.expires_at > now,
        )
        .values(used_at=now)
        .returning(LineAccountLinkCode.id)
    )
    if consumed is None:
        raise InvalidLinkCodeError("Link code is expired, used or revoked")
    contact = next((item for item in contacts if item.is_active), None)
    if contact is None:
        contact = Contact(staff_id=staff_id, is_active=True)
        db.add(contact)
    contact.line_uid = uid
    try:
        db.flush()
    except IntegrityError as error:
        if (
            getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "uq_contacts_line_uid"
        ):
            # Different staff can concurrently claim one UID. Caller rolls back
            # the whole transaction, including the code consumption and dedup.
            raise LineAccountAlreadyBoundError("LINE account is already linked") from error
        raise
    audit_service.log(
        db,
        case_id=None,
        actor_id=actor_id,
        action=AuditAction.LINE_ACCOUNT_LINKED,
        entity_type=EntityType.CONTACTS,
        entity_id=contact.id,
        payload={"contact_id": contact.id, "staff_id": staff_id},
    )
    return contact


def unlink(db: Session, staff_id: int) -> int:
    _lock_staff(db, staff_id, require_active=False)
    # Invalidate unused codes, so a pre-unlink code cannot rebind the old account.
    db.execute(
        update(LineAccountLinkCode)
        .where(
            LineAccountLinkCode.staff_id == staff_id,
            LineAccountLinkCode.used_at.is_(None),
            LineAccountLinkCode.revoked_at.is_(None),
        )
        .values(revoked_at=clock.now())
    )
    count = 0
    for contact in _contacts(db, staff_id):
        if contact.line_uid is None:
            continue
        contact.line_uid = None
        audit_service.log(
            db,
            case_id=None,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
            action=AuditAction.LINE_ACCOUNT_UNLINKED,
            entity_type=EntityType.CONTACTS,
            entity_id=contact.id,
            payload={"contact_id": contact.id, "staff_id": staff_id},
        )
        count += 1
    db.flush()
    return count
