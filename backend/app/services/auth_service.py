"""Web accounts and sessions (round 6 PR AU1, docs/workflow.md 6.33.2 and 6.33.7).

Every auth write (login, logout, a password change, the account script) and every
session check first takes the shared side of the Auth reset gate, a transaction
advisory lock. A demo reset holds its exclusive side from before it copies the accounts
until it commits, so no auth write lands in the old tables after the copy and is lost,
and no request reads a session table that is being rebuilt. The gate comes before any
row lock. Then: STAFF, then AUTH_ACCOUNT, then AUTH_SESSION.

Each function here commits or rolls back itself, so the gate is released at once.
Times are real UTC (app.core.auth_clock), never the Demo Clock. A raw token or password
is never stored or logged; only the session token's SHA-256 reaches the database.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Connection, func, select, text, update
from sqlalchemy.orm import Session

from app.core import auth_clock, passwords
from app.core.config import settings
from app.db.models import Actor, AuthAccount, AuthSession, Role, Staff
from app.domain.enums import ActorType, StaffStatus

# pg_advisory_xact_lock(6210, 1): exclusive for a demo reset, shared for auth writes
AUTH_RESET_GATE = (6210, 1)

ApiRole = Literal["staff", "head_nurse", "supervisor"]
# ROLE.name to the role the API speaks (6.33.3). A role outside this map cannot log in
API_ROLES: dict[str, ApiRole] = {
    "RN": "staff",
    "HEAD_NURSE": "head_nurse",
    "SUPERVISOR": "supervisor",
}


class AccountError(Exception):
    """An account script request that cannot be done, in words safe to print."""


class SessionGoneError(Exception):
    """The session ended while the request was running."""


@dataclass(frozen=True)
class SessionUser:
    """A checked session: who it belongs to, from the database as it is now."""

    staff: Staff
    actor_id: int
    session_id: int
    role: ApiRole
    must_change_password: bool


def hold_auth_gate(db: Session) -> None:
    """Shared side of the reset gate, until this transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock_shared(:a, :b)"), _gate_params())


def take_reset_gate(connection: Connection) -> None:
    """Exclusive side, for the demo reset. Waits for every auth transaction to end."""
    connection.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), _gate_params())


def _gate_params() -> dict[str, int]:
    return {"a": AUTH_RESET_GATE[0], "b": AUTH_RESET_GATE[1]}


def login(db: Session, staff_id: int, password: str) -> tuple[str, SessionUser] | None:
    """A new session for the right password, or None. None says nothing about why:
    no account, wrong password, a closed account and an inactive staff member look
    alike, and each one still verifies a hash."""
    hold_auth_gate(db)
    # FOR SHARE: a password change waits for this login, then revokes its session
    row = db.execute(
        select(AuthAccount, Staff, Actor.id, Role.name)
        .join(Staff, Staff.auth_subject == AuthAccount.staff_subject)
        .join(Actor, (Actor.staff_id == Staff.id) & (Actor.actor_type == ActorType.USER))
        .join(Role, Role.id == Staff.role_id)
        .where(Staff.id == staff_id)
        .with_for_update(of=AuthAccount, read=True)
    ).first()
    usable = (
        row is not None
        and row[0].disabled_at is None
        and row[1].status == StaffStatus.ACTIVE
        and row[3] in API_ROLES
    )
    password_hash = row[0].password_hash if row is not None and usable else None
    if not passwords.verify_password(password_hash, password) or row is None:
        db.rollback()
        return None
    account, staff, actor_id, role_name = row

    token = passwords.new_session_token()
    now = auth_clock.now()
    session = AuthSession(
        account_subject=account.staff_subject,
        token_hash=passwords.token_digest(token),
        credential_version=account.credential_version,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.auth_session_max_age_seconds),
    )
    db.add(session)
    db.flush()
    user = SessionUser(
        staff=staff,
        actor_id=actor_id,
        session_id=session.id,
        role=API_ROLES[role_name],
        must_change_password=account.must_change_password,
    )
    db.commit()
    return token, user


def resolve(db: Session, token: str) -> SessionUser | None:
    """The live session of this cookie token, or None.

    One conditional UPDATE checks everything and moves last_seen_at forward: not
    revoked, same credential version as the account, before both the absolute and the
    idle expiry, account open, staff ACTIVE with a USER actor. A concurrent logout or
    password change locks the same row first, and PostgreSQL then rechecks the
    condition, so a revoked session never comes back. last_seen_at never moves back
    and expires_at never moves.
    """
    now = auth_clock.now()
    hold_auth_gate(db)
    row = db.execute(
        update(AuthSession)
        .where(
            AuthSession.token_hash == passwords.token_digest(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            AuthSession.last_seen_at > now - timedelta(seconds=settings.auth_session_idle_seconds),
            AuthAccount.staff_subject == AuthSession.account_subject,
            AuthAccount.credential_version == AuthSession.credential_version,
            AuthAccount.disabled_at.is_(None),
            Staff.auth_subject == AuthAccount.staff_subject,
            Staff.status == StaffStatus.ACTIVE,
            Actor.staff_id == Staff.id,
            Actor.actor_type == ActorType.USER,
            Role.id == Staff.role_id,
        )
        .values(last_seen_at=func.greatest(AuthSession.last_seen_at, now))
        .returning(AuthSession.id, Staff.id, Actor.id, Role.name, AuthAccount.must_change_password)
        .execution_options(synchronize_session=False)
    ).first()
    db.commit()
    if row is None or row[3] not in API_ROLES:
        return None
    session_id, staff_id, actor_id, role_name, must_change = row
    staff = db.get(Staff, staff_id)
    if staff is None:
        return None
    return SessionUser(
        staff=staff,
        actor_id=actor_id,
        session_id=session_id,
        role=API_ROLES[role_name],
        must_change_password=must_change,
    )


def logout(db: Session, token: str) -> None:
    """Revoke this token's session. Nothing to do for an unknown or ended one."""
    hold_auth_gate(db)
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.token_hash == passwords.token_digest(token),
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=auth_clock.now())
        .execution_options(synchronize_session=False)
    )
    db.commit()


def change_password(db: Session, user: SessionUser, current: str, new: str) -> bool:
    """False for a wrong current password (nothing changes). On success every session
    of the account is revoked, this one too, and the user logs in again.

    Raises SessionGoneError if the session ended after the request's own check.
    """
    hold_auth_gate(db)
    account = _lock_account(db, user.staff.auth_subject)
    alive = account is not None and db.scalar(
        select(AuthSession.id).where(
            AuthSession.id == user.session_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.credential_version == account.credential_version,
        )
    )
    if account is None or not alive:
        db.rollback()
        raise SessionGoneError
    if not passwords.verify_password(account.password_hash, current):
        db.rollback()
        return False
    _set_password(db, account, new, must_change=False)
    db.commit()
    return True


# Account script (app.auth_accounts). No HTTP route reaches these.


def create_account(
    db: Session, staff_id: int, password: str, *, must_change_password: bool = True
) -> None:
    hold_auth_gate(db)
    staff = _lock_staff(db, staff_id)
    if db.get(AuthAccount, staff.auth_subject) is not None:
        db.rollback()
        raise AccountError(f"Staff {staff_id} already has an account; use reset-password")
    now = auth_clock.now()
    db.add(
        AuthAccount(
            staff_subject=staff.auth_subject,
            password_hash=passwords.hash_password(password),
            must_change_password=must_change_password,
            credential_version=1,
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )
    )
    db.commit()


def reset_password(db: Session, staff_id: int, password: str) -> None:
    """A temporary password the person must change at the next login."""
    hold_auth_gate(db)
    staff = _lock_staff(db, staff_id)
    account = _lock_account(db, staff.auth_subject)
    if account is None:
        db.rollback()
        raise AccountError(f"Staff {staff_id} has no account; use create")
    _set_password(db, account, password, must_change=True)
    db.commit()


def set_disabled(db: Session, staff_id: int, disabled: bool) -> None:
    """Close (revoking every session) or reopen an account."""
    hold_auth_gate(db)
    staff = _lock_staff(db, staff_id)
    account = _lock_account(db, staff.auth_subject)
    if account is None:
        db.rollback()
        raise AccountError(f"Staff {staff_id} has no account")
    now = auth_clock.now()
    if disabled and account.disabled_at is None:
        account.disabled_at = now
        account.updated_at = now
        _revoke_all(db, account.staff_subject, now)
    elif not disabled and account.disabled_at is not None:
        account.disabled_at = None
        account.updated_at = now
    db.commit()


def _lock_staff(db: Session, staff_id: int) -> Staff:
    staff = db.scalar(select(Staff).where(Staff.id == staff_id).with_for_update())
    if staff is None:
        db.rollback()
        raise AccountError(f"Staff {staff_id} does not exist")
    return staff


def _lock_account(db: Session, subject: uuid.UUID) -> AuthAccount | None:
    return db.scalar(
        select(AuthAccount)
        .where(AuthAccount.staff_subject == subject)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _set_password(db: Session, account: AuthAccount, password: str, *, must_change: bool) -> None:
    now = auth_clock.now()
    account.password_hash = passwords.hash_password(password)
    account.credential_version += 1
    account.must_change_password = must_change
    account.password_changed_at = now
    account.updated_at = now
    _revoke_all(db, account.staff_subject, now)


def _revoke_all(db: Session, subject: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.account_subject == subject, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
