"""Signed REGISTER and public signup: real PostgreSQL, fake LINE transport only."""

import hashlib
import re
from datetime import timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.dependencies import SESSION_COOKIE, get_db
from app.api.rate_limit import limiter
from app.core import auth_clock, clock, passwords
from app.core.config import settings
from app.db.models import (
    Actor,
    AuthAccount,
    AuthRegistrationCode,
    AuthSession,
    Contact,
    LineWebhookEvent,
    Staff,
)
from app.domain.enums import StaffStatus
from app.integrations.line import client as adapter
from app.main import app
from app.services import auth_service, line_account_service, registration_service
from app.services import line_webhook_service as webhook
from tests.integration.test_line_messaging import signed

PASSWORD = "my own new password"
ORIGIN = settings.cors_origins[0]


@pytest.fixture(autouse=True)
def fresh_registration_limits():
    limiter.clear()
    registration_service.issue_limiter.clear()
    yield
    limiter.clear()
    registration_service.issue_limiter.clear()


@pytest.fixture
def db(production_seeded):
    production_seeded.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    production_seeded.commit()
    return production_seeded


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "session")
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-signature-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-access-token"))
    monkeypatch.setattr(adapter, "reply", Mock(return_value="200"))
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def event(event_id="R1", uid="U201", text="REGISTER", source_type="user"):
    return {
        "type": "message",
        "webhookEventId": event_id,
        "source": {"type": source_type, "userId": uid},
        "replyToken": "reply-test",
        "message": {"type": "text", "text": text},
    }


def post_event(client, item):
    body, headers = signed([item])
    return client.post("/line/webhook", content=body, headers=headers)


def issue(client, event_id="R1"):
    assert post_event(client, event(event_id)).status_code == 200
    return re.search(r"\n([A-Za-z0-9_-]{32})\n", adapter.reply.call_args.args[1])[1]


def signup(client, code, **extra):
    return client.post("/auth/register", json={"code": code, "password": PASSWORD, **extra})


def row(db, code):
    return db.scalar(
        select(AuthRegistrationCode)
        .where(AuthRegistrationCode.code_hash == registration_service.code_digest(code))
        .execution_options(populate_existing=True)
    )


def test_register_then_login_uses_bound_identity_without_automatic_session(client, db):
    raw = issue(client)
    code = row(db, raw)
    assert code.expires_at - code.created_at == timedelta(seconds=600)
    assert code.code_hash != hashlib.sha256(raw.encode()).hexdigest()
    assert code.line_uid_hash != "U201"
    assert raw not in repr(code) and raw not in repr(
        registration_service.RegistrationCode(SecretStr(raw), code.expires_at)
    )
    response = signup(client, raw)
    assert response.status_code == 201 and response.json() == {"staff_id": 201}
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers and SESSION_COOKIE not in client.cookies
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    assert row(db, raw).used_at is not None
    account = db.get(AuthAccount, code.staff_subject)
    assert passwords.verify_password(account.password_hash, PASSWORD)
    assert not account.must_change_password
    assert (
        client.post("/auth/login", json={"staff_id": 201, "password": PASSWORD}).status_code == 200
    )
    assert client.get("/auth/me").json()["staff_id"] == 201
    assert signup(client, raw).json() == {"detail": "AUTH_INVALID_REGISTRATION"}


def test_duplicate_webhook_does_not_issue_or_reply_twice(client, db):
    raw = issue(client)
    assert post_event(client, event()).status_code == 200
    assert adapter.reply.call_count == 1
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 1
    assert signup(client, raw).status_code == 201


def test_new_register_invalidates_previous_code(client, db):
    first, second = issue(client), issue(client, "R2")
    assert row(db, first).revoked_at is not None
    assert signup(client, first).status_code == 400
    assert signup(client, second).status_code == 201


@pytest.mark.parametrize("text", ["register", "ReGiStEr\t\r\n"])
def test_command_case_and_ascii_whitespace(client, text):
    assert post_event(client, event(text=text)).status_code == 200
    assert re.search(r"\n[A-Za-z0-9_-]{32}\n", adapter.reply.call_args.args[1])


@pytest.mark.parametrize(
    "change", ["group", "room", "unbound", "inactive", "contact", "actor", "extra"]
)
def test_only_active_personal_binding_can_issue(client, db, change):
    item = event()
    if change in ("group", "room"):
        item["source"]["type"] = change
    elif change == "unbound":
        item["source"]["userId"] = "U-other"
    elif change == "inactive":
        db.get(Staff, 201).status = StaffStatus.INACTIVE
    elif change == "contact":
        db.scalar(select(Contact)).is_active = False
    elif change == "actor":
        db.execute(delete(Actor).where(Actor.staff_id == 201))
    else:
        item["message"]["text"] = "REGISTER 900"
    db.commit()
    assert post_event(client, item).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0


def test_invalid_signature_never_issues_or_remembers(client, db):
    body, headers = signed([event()])
    headers["x-line-signature"] = "invalid"
    assert client.post("/line/webhook", content=body, headers=headers).status_code == 401
    assert db.get(LineWebhookEvent, "R1") is None
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0


@pytest.mark.parametrize("disabled", [False, True])
def test_existing_account_is_never_replaced(client, db, disabled):
    auth_service.create_account(db, 201, PASSWORD)
    if disabled:
        auth_service.set_disabled(db, 201, True)
    assert post_event(client, event()).status_code == 200
    assert "มีบัญชีเว็บแล้ว" in adapter.reply.call_args.args[1]
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0


@pytest.mark.parametrize("seconds,status", [(599.999999, 201), (600, 400), (601, 400)])
def test_expiry_boundary_uses_real_time(client, db, monkeypatch, seconds, status):
    raw = issue(client)
    now = row(db, raw).created_at + timedelta(seconds=seconds)
    monkeypatch.setattr(auth_clock, "now", lambda: now)
    assert signup(client, raw).status_code == status


def test_demo_freeze_and_advance_do_not_expire_or_extend_code(client, db):
    raw = issue(client)
    clock.advance(timedelta(days=100))
    assert signup(client, raw).status_code == 201


@pytest.mark.parametrize(
    "change", ["unlink", "relink", "inactive", "contact", "uid", "actor", "provision"]
)
def test_binding_and_identity_are_rechecked_at_consumption(client, db, change):
    raw = issue(client)
    if change in ("unlink", "relink"):
        line_account_service.unlink(db, 201)
        db.commit()
        if change == "relink":
            link_code = line_account_service.issue_code(db, 201).code.get_secret_value()
            line_account_service.link(db, link_code, "U201")  # even the same UID must not revive it
    elif change == "inactive":
        db.get(Staff, 201).status = StaffStatus.INACTIVE
    elif change == "contact":
        db.scalar(select(Contact)).is_active = False
    elif change == "uid":
        db.scalar(select(Contact)).line_uid = "U-new"
    elif change == "actor":
        db.execute(delete(Actor).where(Actor.staff_id == 201))
    else:
        auth_service.create_account(db, 201, "administrator password")
    db.commit()
    assert signup(client, raw).json() == {"detail": "AUTH_INVALID_REGISTRATION"}
    assert row(db, raw).used_at is None


@pytest.mark.parametrize("code", ["", "bad", "a" * 32])
def test_unknown_code_is_generic(client, code):
    assert signup(client, code).json() == {"detail": "AUTH_INVALID_REGISTRATION"}


@pytest.mark.parametrize("field", ["staff_id", "actor_id", "role", "ward"])
def test_cannot_choose_identity_or_role(client, db, field):
    raw = issue(client)
    response = signup(client, raw, **{field: 900})
    assert response.status_code == 422
    assert raw not in response.text and PASSWORD not in response.text
    assert row(db, raw).used_at is None


def test_origin_is_required_and_errors_never_echo_password_or_code(client, db):
    raw = issue(client)
    client.headers.pop("Origin")
    assert signup(client, raw).json() == {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    response = client.post(
        "/auth/register", headers={"Origin": ORIGIN}, json={"code": raw, "password": "s3cr3tAbc"}
    )
    assert (
        response.status_code == 422
        and "s3cr3tAbc" not in response.text
        and raw not in response.text
    )
    assert row(db, raw).used_at is None


def test_rate_limit_precedes_hash_and_failed_attempts_count(client, monkeypatch):
    raw = issue(client)
    for _ in range(5):
        assert signup(client, "bad").status_code == 400
    hash_mock = Mock(side_effect=AssertionError("must not hash"))
    monkeypatch.setattr(passwords, "hash_password", hash_mock)
    response = signup(client, raw)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert not hash_mock.called


def test_subject_limit_spans_ips(client):
    raw = issue(client)
    # A known but revoked code resolves to the same subject, independent of client IP.
    issue(client, "R2")
    for i in range(6):
        with TestClient(
            app,
            base_url="https://testserver",
            headers={"Origin": ORIGIN},
            client=(f"127.0.0.{i + 1}", 50000),
        ) as other:
            response = signup(other, raw)
        assert response.status_code == (400 if i < 5 else 429)


def test_issuance_limit_five_per_subject_and_denial_keeps_last_code(client, db):
    for i in range(5):
        raw = issue(client, f"R{i}")
    assert post_event(client, event("R6")).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 5
    assert row(db, raw).revoked_at is None
    assert signup(client, raw).status_code == 201


def test_dedup_failure_rolls_back_issuance_and_can_retry(client, db, monkeypatch):
    original = webhook._remember
    monkeypatch.setattr(webhook, "_remember", Mock(side_effect=RuntimeError("failed")))
    assert post_event(client, event()).status_code == 503
    assert db.get(LineWebhookEvent, "R1") is None
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0
    assert adapter.reply.call_count == 0
    monkeypatch.setattr(webhook, "_remember", original)
    assert post_event(client, event()).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 1


def test_reply_failure_keeps_code_and_next_command_replaces_it(client, db):
    adapter.reply.side_effect = RuntimeError("transport failed")
    assert post_event(client, event()).status_code == 200
    first = db.scalar(select(AuthRegistrationCode))
    assert first is not None and db.get(LineWebhookEvent, "R1") is not None
    adapter.reply.side_effect = None
    second = issue(client, "R2")
    db.refresh(first)
    assert first.revoked_at is not None and signup(client, second).status_code == 201


def test_link_and_register_codes_are_not_interchangeable(client, db):
    register_code = issue(client)
    link_code = line_account_service.issue_code(db, 202).code.get_secret_value()
    db.commit()
    assert signup(client, link_code).status_code == 400
    assert post_event(client, event("WRONG-LINK", text=f"LINK {register_code}")).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0
    assert row(db, register_code).used_at is None
