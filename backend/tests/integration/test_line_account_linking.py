"""Signed account linking and local administration, with no actual LINE traffic."""

import hashlib
from datetime import timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, Contact, LineAccountLinkCode, LineWebhookEvent, Staff
from app.domain.enums import AuditAction, StaffStatus
from app.integrations.line import client as adapter
from app.main import app
from app.services import (
    actor_service,
    audit_service,
    line_account_service,
    line_contact_service,
    outreach_service,
)
from app.services import line_delivery_service as delivery
from app.services import line_webhook_service as webhook
from tests.integration.case_rows import short_case
from tests.integration.test_line_messaging import signed


@pytest.fixture
def linked_client(production_seeded, monkeypatch):
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-signature-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-access-token"))
    monkeypatch.setattr(settings, "internal_job_secret", "test-admin-secret")
    monkeypatch.setattr(adapter, "push", Mock(return_value="200"))
    monkeypatch.setattr(adapter, "reply", Mock(return_value="200"))
    app.dependency_overrides[get_db] = lambda: production_seeded
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def issue(db, staff_id=201):
    result = line_account_service.issue_code(db, staff_id)
    db.commit()
    return result.code.get_secret_value()


def link_event(code, event_id="LINK1", uid="U201"):
    return {
        "type": "message",
        "webhookEventId": event_id,
        "source": {"type": "user", "userId": uid},
        "replyToken": "reply-test",
        "message": {"type": "text", "text": f"LINK {code}"},
    }


def post(client, item):
    body, headers = signed([item])
    return client.post("/line/webhook", content=body, headers=headers)


def audit_count(db, action):
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))


def code_row(db, raw):
    return db.scalar(
        select(LineAccountLinkCode)
        .where(LineAccountLinkCode.code_hash == hashlib.sha256(raw.encode()).hexdigest())
        .execution_options(populate_existing=True)
    )


def test_unbound_sender_links_once_with_code_and_transactional_audit(
    linked_client, production_seeded
):
    db = production_seeded
    raw = issue(db)
    row = code_row(db, raw)
    assert row.code_hash != raw and len(row.code_hash) == 64
    assert row.expires_at - row.created_at == timedelta(minutes=10)
    assert line_contact_service.staff_for_line_uid(db, "U201") is None
    assert post(linked_client, link_event(raw)).status_code == 200
    assert line_contact_service.staff_for_line_uid(db, "U201") == (
        201,
        actor_service.user_id(db, 201),
    )
    assert line_contact_service.line_uid_for_staff(db, 201) == "U201"
    assert code_row(db, raw).used_at == clock.now()
    assert db.get(LineWebhookEvent, "LINK1") is not None
    audit = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.LINE_ACCOUNT_LINKED))
    assert audit.actor_id == actor_service.user_id(db, 201)
    assert audit.case_id is None and audit.event_id is None
    assert set(audit.payload) == {"contact_id", "staff_id"}
    assert post(linked_client, link_event(raw)).status_code == 200
    assert audit_count(db, AuditAction.LINE_ACCOUNT_LINKED) == 1
    assert adapter.reply.call_count == 1


@pytest.mark.parametrize("age", [timedelta(seconds=600), timedelta(seconds=601)])
def test_code_deadline_is_inclusive(linked_client, production_seeded, age):
    db = production_seeded
    raw = issue(db)
    clock.advance(age)
    assert post(linked_client, link_event(raw)).status_code == 200
    assert code_row(db, raw).used_at is None
    assert db.scalar(select(func.count()).select_from(Contact)) == 0
    assert db.get(LineWebhookEvent, "LINK1") is not None
    assert audit_count(db, AuditAction.LINE_ACCOUNT_LINKED) == 0


def test_code_can_be_used_immediately_before_deadline(linked_client, production_seeded):
    raw = issue(production_seeded)
    clock.advance(timedelta(seconds=600, microseconds=-1))
    assert post(linked_client, link_event(raw)).status_code == 200
    assert code_row(production_seeded, raw).used_at is not None


@pytest.mark.parametrize("text", ["LINK", "LINK bad", "LINK " + "a" * 32 + " extra"])
def test_invalid_link_is_terminal_without_consumption(linked_client, production_seeded, text):
    raw = issue(production_seeded)
    item = link_event(raw)
    item["message"]["text"] = text
    assert post(linked_client, item).status_code == 200
    assert code_row(production_seeded, raw).used_at is None
    assert production_seeded.get(LineWebhookEvent, "LINK1") is not None
    assert audit_count(production_seeded, AuditAction.LINE_ACCOUNT_LINKED) == 0


@pytest.mark.parametrize(
    "source", [{}, {"type": "group", "userId": "U201"}, {"type": "user", "userId": ""}]
)
def test_link_requires_signed_one_to_one_sender(linked_client, production_seeded, source):
    raw = issue(production_seeded)
    item = link_event(raw)
    item["source"] = source
    assert post(linked_client, item).status_code == 200
    assert code_row(production_seeded, raw).used_at is None


def test_wrong_signature_does_not_link_or_dedup(linked_client, production_seeded):
    raw = issue(production_seeded)
    body, headers = signed([link_event(raw)])
    headers["x-line-signature"] = "invalid"
    assert linked_client.post("/line/webhook", content=body, headers=headers).status_code == 401
    assert code_row(production_seeded, raw).used_at is None
    assert production_seeded.get(LineWebhookEvent, "LINK1") is None


def test_used_code_cannot_bind_another_sender(linked_client, production_seeded):
    raw = issue(production_seeded)
    assert post(linked_client, link_event(raw)).status_code == 200
    assert post(linked_client, link_event(raw, "LINK2", "U-other")).status_code == 200
    assert line_contact_service.line_uid_for_staff(production_seeded, 201) == "U201"
    assert audit_count(production_seeded, AuditAction.LINE_ACCOUNT_LINKED) == 1


def test_uid_and_staff_cannot_be_overwritten_and_refused_code_remains_usable(
    linked_client, production_seeded
):
    db = production_seeded
    first, spare, other = issue(db), issue(db), issue(db, 202)
    assert post(linked_client, link_event(first)).status_code == 200
    assert post(linked_client, link_event(spare, "SPARE", "U-new")).status_code == 200
    assert code_row(db, spare).used_at is None
    assert post(linked_client, link_event(other, "OTHER", "U201")).status_code == 200
    assert code_row(db, other).used_at is None
    assert post(linked_client, link_event(other, "OTHER2", "U202")).status_code == 200
    assert line_contact_service.line_uid_for_staff(db, 201) == "U201"
    assert line_contact_service.line_uid_for_staff(db, 202) == "U202"


def test_inactive_staff_cannot_link(linked_client, production_seeded):
    db = production_seeded
    raw = issue(db)
    db.get(Staff, 201).status = StaffStatus.INACTIVE
    db.commit()
    assert post(linked_client, link_event(raw)).status_code == 200
    assert code_row(db, raw).used_at is None


@pytest.mark.parametrize("fail_at", ["audit", "dedup"])
def test_failed_link_rolls_back_contact_code_audit_and_dedup(
    linked_client, production_seeded, monkeypatch, fail_at
):
    db = production_seeded
    raw = issue(db)
    target, name = (audit_service, "log") if fail_at == "audit" else (webhook, "_remember")
    original = getattr(target, name)
    monkeypatch.setattr(target, name, Mock(side_effect=RuntimeError("test failure")))
    assert post(linked_client, link_event(raw)).status_code == 503
    assert code_row(db, raw).used_at is None
    assert db.scalar(select(func.count()).select_from(Contact)) == 0
    assert audit_count(db, AuditAction.LINE_ACCOUNT_LINKED) == 0
    assert db.get(LineWebhookEvent, "LINK1") is None
    monkeypatch.setattr(target, name, original)
    assert post(linked_client, link_event(raw)).status_code == 200
    assert audit_count(db, AuditAction.LINE_ACCOUNT_LINKED) == 1


def test_unlink_preserves_contact_and_revokes_old_codes_then_allows_relink(
    linked_client, production_seeded
):
    db = production_seeded
    raw, spare = issue(db), issue(db)
    db.add(Contact(staff_id=201, line_id="manual-display-id", is_active=True))
    db.commit()
    assert post(linked_client, link_event(raw)).status_code == 200
    contact = db.scalar(select(Contact).where(Contact.staff_id == 201))
    contact_id = contact.id
    response = linked_client.post(
        "/internal/line-accounts/201/unlink", headers={"X-Internal-Secret": "test-admin-secret"}
    )
    assert response.status_code == 200 and response.json()["unlinked_contacts"] == 1
    db.refresh(contact)
    assert contact.line_uid is None and contact.line_id == "manual-display-id" and contact.is_active
    assert code_row(db, spare).revoked_at == clock.now()
    assert post(linked_client, link_event(spare, "REVOKED")).status_code == 200
    assert code_row(db, spare).used_at is None
    assert audit_count(db, AuditAction.LINE_ACCOUNT_UNLINKED) == 1
    assert (
        linked_client.post(
            "/internal/line-accounts/201/unlink", headers={"X-Internal-Secret": "test-admin-secret"}
        ).status_code
        == 200
    )
    assert audit_count(db, AuditAction.LINE_ACCOUNT_UNLINKED) == 1
    new = issue(db)
    assert post(linked_client, link_event(new, "RELINK", "U-new")).status_code == 200
    assert line_contact_service.line_uid_for_staff(db, 201) == "U-new"
    assert db.scalar(select(Contact.id).where(Contact.staff_id == 201)) == contact_id


@pytest.mark.parametrize("operation", ["issue-code", "unlink"])
@pytest.mark.parametrize("secret", [None, "wrong-secret"])
def test_administrator_commands_require_internal_secret(
    linked_client, production_seeded, operation, secret
):
    headers = {} if secret is None else {"X-Internal-Secret": secret}
    assert (
        linked_client.post(f"/internal/line-accounts/201/{operation}", headers=headers).status_code
        == 401
    )
    assert production_seeded.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0


def test_issue_command_uses_backend_clock_and_no_cache(linked_client, production_seeded):
    response = linked_client.post(
        "/internal/line-accounts/201/issue-code", headers={"X-Internal-Secret": "test-admin-secret"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    row = code_row(production_seeded, response.json()["code"])
    assert row.created_at == clock.now()
    assert row.expires_at == clock.now() + timedelta(minutes=10)


def test_unlink_prevents_retry_to_immutable_old_recipient(linked_client, production_seeded):
    db = production_seeded
    raw = issue(db)
    assert post(linked_client, link_event(raw)).status_code == 200
    case, items = short_case(db)
    row = outreach_service.send_offer(db, case, [items[201]])[0]
    db.commit()
    payload = row.delivery_payload
    assert payload["to"] == "U201"
    line_account_service.unlink(db, 201)
    db.commit()
    # This fixture shares a request Session; remove its completed-request scheduler
    # to exercise the synchronous service/job path with the same transaction.
    db.info.pop("line_delivery_scheduler", None)
    delivery.dispatch_pending(db, case_id=case.id)
    db.refresh(row)
    assert row.status == "SENT" and row.delivery_status == "NO_CONTACT"
    assert row.delivery_attempts == 0 and row.delivery_payload == payload
    assert adapter.push.call_count == 0
    assert audit_count(db, AuditAction.OFFER_DELIVERY_FAILED) == 0


def test_unlink_audit_failure_rolls_back_binding_and_code_revocation(
    linked_client, production_seeded, monkeypatch
):
    db = production_seeded
    raw, spare = issue(db), issue(db)
    assert post(linked_client, link_event(raw)).status_code == 200
    monkeypatch.setattr(audit_service, "log", Mock(side_effect=RuntimeError("test failure")))
    with pytest.raises(RuntimeError), db.begin_nested():
        line_account_service.unlink(db, 201)
    assert line_contact_service.line_uid_for_staff(db, 201) == "U201"
    assert code_row(db, spare).revoked_at is None
    assert audit_count(db, AuditAction.LINE_ACCOUNT_UNLINKED) == 0


@pytest.mark.parametrize("staff_id", [99999, 203])
def test_issue_command_rejects_missing_or_inactive_staff(
    linked_client, production_seeded, staff_id
):
    if staff_id == 203:
        production_seeded.get(Staff, staff_id).status = StaffStatus.INACTIVE
        production_seeded.commit()
    response = linked_client.post(
        f"/internal/line-accounts/{staff_id}/issue-code",
        headers={"X-Internal-Secret": "test-admin-secret"},
    )
    assert response.status_code == 404
    assert production_seeded.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0
