"""A demo reset keeps people and accounts, ends sessions (docs/workflow.md 6.33.7, PR AU1).

Also the Auth reset gate, and a revoked session that must stay revoked under concurrent
requests. These tests commit, like test_demo_reset.
"""

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import passwords
from app.db.models import Actor, AuthAccount, AuthSession, Role, Staff, Ward
from app.db.session import SessionLocal, engine
from app.domain.enums import ActorType, StaffStatus
from app.seed import reset as reset_module
from app.seed.reset import IdentityConflictError, reset_demo
from app.services import auth_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

PASSWORD = "kept across resets"
EXTRA_STAFF = 7001


def _subjects(db: Session) -> dict[int, uuid.UUID]:
    return {
        staff_id: subject for staff_id, subject in db.execute(select(Staff.id, Staff.auth_subject))
    }


def _accounts(db: Session) -> dict[uuid.UUID, tuple[Any, ...]]:
    return {
        account.staff_subject: (
            account.password_hash,
            account.must_change_password,
            account.disabled_at,
            account.credential_version,
            account.password_changed_at,
        )
        for account in db.scalars(select(AuthAccount))
    }


def _add_extra_staff(db: Session, staff_id: int, ward_id: int = 1) -> None:
    """A person the seed does not create, as the account script might find them."""
    db.add(
        Staff(
            id=staff_id,
            first_name="Kept",
            last_name="Person",
            email=f"{staff_id}@demo.local",
            password_hash="!",
            role_id=db.scalars(select(Role.id).where(Role.name == "RN")).one(),
            home_ward_id=ward_id,
            status=StaffStatus.ACTIVE,
        )
    )
    db.flush()
    db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
    db.commit()


@pytest.fixture
def accounts() -> dict[str, Any]:
    """After a first reset: accounts for 105 (logged in), 201 (closed), 900 (must change)
    and a kept extra person, each with a password change history."""
    reset_demo()
    with SessionLocal() as db:
        _add_extra_staff(db, EXTRA_STAFF)
        for staff_id in (105, 201, 900, EXTRA_STAFF):
            auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)
        auth_service.reset_password(db, 105, PASSWORD)  # credential_version 2
        auth_service.set_disabled(db, 201, True)
        auth_service.reset_password(db, 900, PASSWORD)
        login = auth_service.login(db, 105, PASSWORD)
        extra_login = auth_service.login(db, EXTRA_STAFF, PASSWORD)
        assert login is not None and extra_login is not None
        return {
            "subjects": _subjects(db),
            "accounts": _accounts(db),
            "token": login[0],
            "extra_actor": db.scalars(select(Actor.id).where(Actor.staff_id == EXTRA_STAFF)).one(),
        }


def test_reset_keeps_every_person_and_account_but_ends_every_session(
    accounts: dict[str, Any],
) -> None:
    reset_demo()

    with SessionLocal() as db:
        assert _subjects(db) == accounts["subjects"]
        assert _accounts(db) == accounts["accounts"]
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert auth_service.resolve(db, accounts["token"]) is None
        # The kept person has a USER actor again, so they can log in
        actor = db.scalars(select(Actor).where(Actor.staff_id == EXTRA_STAFF)).one()
        assert actor.actor_type == ActorType.USER and actor.name == str(EXTRA_STAFF)
        result = auth_service.login(db, EXTRA_STAFF, PASSWORD)
        assert (
            result is not None
            and result[1].staff.auth_subject == (accounts["subjects"][EXTRA_STAFF])
        )
        # Flags survive: closed stays closed, must-change still applies
        assert auth_service.login(db, 201, PASSWORD) is None
        login = auth_service.login(db, 900, PASSWORD)
        assert login is not None and login[1].must_change_password
        # A new staff row goes after the kept IDs
        next_id = db.scalar(text("SELECT nextval(pg_get_serial_sequence('staff', 'id'))"))
        assert next_id is not None and next_id > EXTRA_STAFF


def test_reset_twice_still_keeps_the_same_subjects(accounts: dict[str, Any]) -> None:
    reset_demo()
    reset_demo()

    with SessionLocal() as db:
        assert _subjects(db) == accounts["subjects"]
        assert _accounts(db) == accounts["accounts"]


def test_golden_case_data_is_reloaded_for_seeded_people(accounts: dict[str, Any]) -> None:
    with SessionLocal() as db:
        db.execute(text("UPDATE staff SET first_name = 'Changed' WHERE id = 105"))
        db.commit()

    reset_demo()

    with SessionLocal() as db:
        staff = db.get(Staff, 105)
        assert staff is not None
        assert staff.first_name == "Sudarat"
        assert staff.auth_subject == accounts["subjects"][105]


def test_a_person_whose_ward_is_gone_fails_the_whole_reset(accounts: dict[str, Any]) -> None:
    with SessionLocal() as db:
        db.add(Ward(id=77, name="Scenario ward", is_active=True))
        db.commit()
        _add_extra_staff(db, EXTRA_STAFF + 1, ward_id=77)

    with pytest.raises(IdentityConflictError, match=str(EXTRA_STAFF + 1)):
        reset_demo()

    # Rolled back: the session from before is still there and still works
    with SessionLocal() as db:
        assert db.get(Ward, 77) is not None
        assert db.get(Staff, EXTRA_STAFF + 1) is not None
        assert auth_service.resolve(db, accounts["token"]) is not None
        assert _accounts(db) == accounts["accounts"]


def test_a_failed_reset_keeps_sessions(
    accounts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(db: Session, **kwargs: object) -> None:
        raise RuntimeError("seed failed")

    monkeypatch.setattr(reset_module, "load", broken)
    with pytest.raises(RuntimeError, match="seed failed"):
        reset_demo()

    with SessionLocal() as db:
        assert auth_service.resolve(db, accounts["token"]) is not None


# --------------------------------------------------------------------------- #
# The Auth reset gate and concurrent requests
# --------------------------------------------------------------------------- #
def _waiting_for_lock(timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            if connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    " AND wait_event_type = 'Lock'"
                )
            ):
                return
            connection.rollback()
            time.sleep(0.02)
    pytest.fail("nothing is waiting for a lock")


def _resolve(token: str) -> object:
    with SessionLocal() as db:
        return auth_service.resolve(db, token)


def _in_thread(work: Callable[[], object], results: list[object]) -> threading.Thread:
    def run() -> None:
        try:
            results.append(work())
        except BaseException as error:
            results.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_reset_waits_for_an_auth_write_in_progress_and_keeps_it(
    accounts: dict[str, Any],
) -> None:
    """A password change holding the shared gate: the reset copies only after it commits,
    so the new password is the one kept."""
    results: list[object] = []
    db = SessionLocal()
    try:
        auth_service.hold_auth_gate(db)
        account = db.scalars(
            select(AuthAccount).where(
                AuthAccount.staff_subject == accounts["subjects"][EXTRA_STAFF]
            )
        ).one()
        account.credential_version += 1
        db.flush()
        reset = _in_thread(reset_demo, results)
        _waiting_for_lock()
        assert reset.is_alive()
        db.commit()
        reset.join(60)
    finally:
        db.close()
    assert not reset.is_alive() and not isinstance(results[0], BaseException)

    with SessionLocal() as db:
        kept = db.get(AuthAccount, accounts["subjects"][EXTRA_STAFF])
        assert kept is not None and kept.credential_version == 2


def test_a_session_check_during_a_reset_waits_then_finds_no_session(
    accounts: dict[str, Any],
) -> None:
    results: list[object] = []
    connection = engine.connect()
    transaction = connection.begin()
    try:
        # What the reset does first
        auth_service.take_reset_gate(connection)
        check = _in_thread(lambda: _resolve(accounts["token"]), results)
        _waiting_for_lock()
        assert check.is_alive()
        connection.execute(text("DELETE FROM auth_session"))
        transaction.commit()
        check.join(30)
    finally:
        connection.close()

    assert results == [None]


def test_a_revoke_wins_over_a_concurrent_session_check(accounts: dict[str, Any]) -> None:
    """Logout (or a password change) locks the session row; a request checking the same
    session waits, then sees it revoked. It never writes the row back alive."""
    results: list[object] = []
    db = SessionLocal()
    try:
        auth_service.hold_auth_gate(db)
        db.execute(
            AuthSession.__table__.update()
            .where(AuthSession.token_hash == passwords.token_digest(accounts["token"]))
            .values(revoked_at=func.now())
        )
        check = _in_thread(lambda: _resolve(accounts["token"]), results)
        _waiting_for_lock()
        db.commit()
        check.join(30)
    finally:
        db.close()

    assert results == [None]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 1
        )  # only the extra person's session from the fixture
