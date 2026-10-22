"""Independent connections: one account, reset gate, rollback and unlink races."""

import threading
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select, text

from app.core import passwords
from app.db.models import AuthAccount, AuthRegistrationCode, AuthSession, Contact
from app.db.session import SessionLocal
from app.seed import reset as reset_module
from app.seed.reset import reset_demo
from app.services import auth_service, line_account_service, registration_service
from app.services import line_webhook_service as webhook
from tests.integration.test_registration import PASSWORD, event


@pytest.fixture
def code(restore_empty_database):
    registration_service.issue_limiter.clear()
    reset_demo()
    with SessionLocal() as db:
        db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
        db.commit()
        result = registration_service.issue(db, "U201")
        db.commit()
        return result.code.get_secret_value()


def register(raw):
    with SessionLocal() as db:
        db.execute(text("SET LOCAL statement_timeout='8s'"))
        try:
            staff_id = registration_service.register(db, raw, PASSWORD)
            db.commit()
            return staff_id
        except registration_service.RegistrationError:
            db.rollback()
            return "refused"


def race(*actions):
    barrier = threading.Barrier(len(actions))
    results = []

    def worker(action):
        try:
            barrier.wait(5)
            results.append(action())
        except BaseException as error:
            results.append(error)

    threads = [threading.Thread(target=worker, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert all(not t.is_alive() for t in threads)
    assert not [r for r in results if isinstance(r, BaseException)], results
    return results


def test_two_consumers_create_exactly_one_account(code):
    assert sorted(race(lambda: register(code), lambda: register(code)), key=str) == [201, "refused"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthAccount)) == 1
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert db.scalar(select(AuthRegistrationCode.used_at)) is not None


def test_registration_races_administrator_provisioning(code):
    def provision():
        with SessionLocal() as db:
            try:
                auth_service.create_account(db, 201, PASSWORD)
                return "admin"
            except auth_service.AccountError:
                return "refused"

    results = race(lambda: register(code), provision)
    assert results.count("refused") == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthAccount)) == 1


def test_parallel_register_events_leave_one_active_code(code, monkeypatch):
    monkeypatch.setattr(webhook.client, "reply", Mock(return_value="200"))

    def issue(number):
        with SessionLocal() as db:
            webhook.process_event(db, event(f"R{number}"))

    race(lambda: issue(1), lambda: issue(2))
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthRegistrationCode)
                .where(
                    AuthRegistrationCode.used_at.is_(None),
                    AuthRegistrationCode.revoked_at.is_(None),
                )
            )
            == 1
        )
    assert webhook.client.reply.call_count == 2


def test_duplicate_parallel_register_event_replies_once(code, monkeypatch):
    monkeypatch.setattr(webhook.client, "reply", Mock(return_value="200"))

    def issue():
        with SessionLocal() as db:
            webhook.process_event(db, event())

    race(issue, issue)
    # One old code from fixture plus one committed command; the losing transaction rolls back.
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 2
    assert webhook.client.reply.call_count == 1


def test_unlink_waits_for_signup_and_keeps_created_web_account(code, monkeypatch):
    entered, release, unlink_started = threading.Event(), threading.Event(), threading.Event()
    original = passwords.hash_password
    results = []

    def pause(password):
        entered.set()
        assert release.wait(5)
        return original(password)

    monkeypatch.setattr(passwords, "hash_password", pause)

    def signup():
        results.append(register(code))

    def unlink():
        with SessionLocal() as db:
            unlink_started.set()
            line_account_service.unlink(db, 201)
            db.commit()

    first = threading.Thread(target=signup)
    second = threading.Thread(target=unlink)
    first.start()
    try:
        assert entered.wait(5)
        second.start()
        assert unlink_started.wait(5)
    finally:
        release.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
    assert not first.is_alive() and not second.is_alive() and results == [201]
    with SessionLocal() as db:
        assert db.scalar(select(Contact.line_uid)) is None
        assert auth_service.login(db, 201, PASSWORD) is not None


def test_failed_account_insert_rolls_back_code_consumption(code, monkeypatch):
    original = SessionLocal.class_.flush

    def fail_flush(db, *args, **kwargs):
        if any(isinstance(obj, AuthAccount) for obj in db.new):
            raise RuntimeError("insert failed")
        return original(db, *args, **kwargs)

    monkeypatch.setattr(SessionLocal.class_, "flush", fail_flush)
    with pytest.raises(RuntimeError, match="insert failed"):
        register(code)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0
        assert db.scalar(select(AuthRegistrationCode.used_at)) is None
    monkeypatch.setattr(SessionLocal.class_, "flush", original)
    assert register(code) == 201


def test_reset_discards_codes_but_keeps_created_account_and_invalidates_session(code):
    assert register(code) == 201
    with SessionLocal() as db:
        token, user = auth_service.login(db, 201, PASSWORD)
        subject = user.staff.auth_subject
    reset_demo()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0
        assert auth_service.resolve(db, token) is None
        login = auth_service.login(db, 201, PASSWORD)
        assert login is not None and login[1].staff.auth_subject == subject
    assert register(code) == "refused"


def test_failed_reset_restores_signup_code(code, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("seed failed")

    monkeypatch.setattr(reset_module, "load", broken)
    with pytest.raises(RuntimeError, match="seed failed"):
        reset_demo()
    assert register(code) == 201


def test_reset_clears_unused_code(code):
    reset_demo()
    assert register(code) == "refused"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0


def test_reset_gate_blocks_registration_until_code_is_invalidated(code):
    results = []
    with SessionLocal() as db:
        auth_service.take_reset_gate(db.connection())

        def signup():
            results.append(register(code))

        worker = threading.Thread(target=signup)
        worker.start()
        # No table access before the shared gate; simulate reset's deletion while holding exclusive.
        db.execute(text("DELETE FROM auth_registration_code"))
        db.commit()
        worker.join(10)
    assert not worker.is_alive() and results == ["refused"]
