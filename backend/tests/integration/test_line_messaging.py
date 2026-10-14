"""Real LINE via deterministic HTTP adapter doubles, without secrets or internet."""

import base64
import hashlib
import hmac
import json
import threading
from datetime import timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, CandidateOutreach, Contact, LineWebhookEvent, StaffingCase
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CaseStatus, OutreachStatus
from app.integrations.line import client as adapter
from app.main import app
from app.seed import load
from app.services import line_delivery_service as delivery
from app.services import line_webhook_service as webhook
from app.services import outreach_service
from tests.integration.case_rows import short_case


@pytest.fixture
def real_line(monkeypatch):
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-signature-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-access-token"))
    push, reply = Mock(return_value="200"), Mock(return_value="200")
    monkeypatch.setattr(adapter, "push", push)
    monkeypatch.setattr(adapter, "reply", reply)
    return push, reply


def prepared(db):
    case, items = short_case(db)
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.flush()
    row = outreach_service.send_offer(db, case, [items[201]])[0]
    db.commit()
    return case, items, row


def event(row, event_id="E1", response="ACCEPT", uid="U201"):
    return {
        "type": "postback",
        "webhookEventId": event_id,
        "source": {"type": "user", "userId": uid},
        "replyToken": "reply-test",
        "postback": {"data": f"outreach_id={row.id}&response={response}"},
    }


def signed(events):
    body = json.dumps({"events": events}).encode()
    signature = base64.b64encode(
        hmac.new(b"test-signature-secret", body, hashlib.sha256).digest()
    ).decode()
    return body, {"x-line-signature": signature, "Content-Type": "application/json"}


@pytest.fixture
def http_client(production_seeded):
    app.dependency_overrides[get_db] = lambda: production_seeded
    with TestClient(app) as result:
        yield result
    app.dependency_overrides.clear()


@pytest.mark.parametrize("signature", [None, "invalid"])
def test_signature_is_checked_before_json_or_database(
    real_line, http_client, production_seeded, signature
):
    headers = {} if signature is None else {"x-line-signature": signature}
    assert (
        http_client.post("/line/webhook", content=b"not JSON", headers=headers).status_code == 401
    )
    assert production_seeded.scalar(select(func.count()).select_from(LineWebhookEvent)) == 0


def test_signed_verification_empty_events(real_line, http_client):
    body, headers = signed([])
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200


@pytest.mark.parametrize("response", ["ACCEPT", "REJECT"])
def test_webhook_response_and_duplicate_have_one_effect(
    real_line, http_client, production_seeded, response
):
    db = production_seeded
    _, _, row = prepared(db)
    body, headers = signed([event(row, response=response)])
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    count = db.scalar(select(func.count()).select_from(AuditLog))
    assert db.get(LineWebhookEvent, "E1") is not None
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count
    assert real_line[1].call_count == 1


@pytest.mark.parametrize(
    "uid,data",
    [("unknown", None), ("U202", None), ("U201", "outreach_id=1&response=ACCEPT&staff_id=202")],
)
def test_unbound_wrong_owner_and_malformed_actions_are_acknowledged(
    real_line, http_client, production_seeded, uid, data
):
    db = production_seeded
    _, _, row = prepared(db)
    db.add(Contact(staff_id=202, line_uid="U202", is_active=True))
    db.commit()
    item = event(row, uid=uid)
    if data:
        item["postback"]["data"] = data
    body, headers = signed([item])
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.SENT
    assert db.get(LineWebhookEvent, "E1") is not None


def test_expired_response_is_terminal_with_explanation(real_line, http_client, production_seeded):
    db = production_seeded
    _, _, row = prepared(db)
    clock.advance(timedelta(seconds=300))
    body, headers = signed([event(row)])
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    assert "หมดเวลา" in real_line[1].call_args.args[1]
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.SENT


def test_unexpected_failure_rolls_back_event_and_response(
    real_line, http_client, production_seeded, monkeypatch
):
    db = production_seeded
    _, _, row = prepared(db)

    def broken(*args, **kwargs):
        kwargs["after_lock"](args[0])
        raise RuntimeError("test fault")

    monkeypatch.setattr(outreach_service, "record_response", broken)
    body, headers = signed([event(row)])
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 503
    assert db.get(LineWebhookEvent, "E1") is None
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.SENT


def test_each_event_commits_independently(real_line, http_client, production_seeded, monkeypatch):
    db = production_seeded
    _, _, row = prepared(db)
    body, headers = signed([event(row), event(row, event_id="E2", response="REJECT")])
    original = webhook.process_event

    def fail_second(session, item):
        if item["webhookEventId"] == "E2":
            raise RuntimeError("temporary failure")
        original(session, item)

    monkeypatch.setattr(webhook, "process_event", fail_second)
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 503
    assert db.get(LineWebhookEvent, "E1") is not None
    assert db.get(LineWebhookEvent, "E2") is None
    monkeypatch.setattr(webhook, "process_event", original)
    assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    assert db.get(LineWebhookEvent, "E2") is not None
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.OFFER_ACCEPTED)
        )
        == 1
    )


def test_wave_rollback_removes_intent_without_http(real_line, production_seeded):
    db = production_seeded
    case, items = short_case(db)
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    with pytest.raises(RuntimeError), db.begin_nested():
        outreach_service.send_offer(db, case, [items[201]])
        raise RuntimeError("wave failed")
    db.commit()
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 0
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0


def test_dedup_is_written_after_lock_restart(real_line, production_seeded, monkeypatch):
    db = production_seeded
    _, _, row = prepared(db)
    original = outreach_service.lock_case_for_outreach

    def restarted(session, case_id):
        session.rollback()
        assert session.get(LineWebhookEvent, "E1") is None
        return original(session, case_id)

    monkeypatch.setattr(outreach_service, "lock_case_for_outreach", restarted)
    webhook.process_event(db, event(row))
    assert db.get(LineWebhookEvent, "E1") is not None
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.ACCEPTED


def test_intent_is_atomic_and_restart_recovers_it(real_line, production_seeded):
    db = production_seeded
    _, _, row = prepared(db)
    assert real_line[0].call_count == 0
    original_payload, original_key = row.delivery_payload, row.delivery_retry_key
    delivery.dispatch_pending(db)
    assert real_line[0].call_args.args == (original_payload, original_key)
    assert db.get(CandidateOutreach, row.id).delivery_status == "ACCEPTED"


def test_claim_lease_prevents_duplicate_workers_and_recovers_crash(real_line, production_seeded):
    db = production_seeded
    _, _, row = prepared(db)
    claim = delivery._claim(db, row.id)
    assert claim is not None
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 0
    clock.advance(timedelta(seconds=60))
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 1
    assert real_line[0].call_args.args[1] == claim.retry_key


@pytest.mark.parametrize("result", ["200", "409"])
def test_line_acceptance_stops_retries(real_line, production_seeded, result):
    db = production_seeded
    _, _, row = prepared(db)
    real_line[0].return_value = result
    delivery.dispatch_pending(db)
    clock.advance(timedelta(seconds=30))
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 1
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.SENT


@pytest.mark.parametrize("result", ["429", "401", "403"])
def test_configuration_and_rate_errors_do_not_consume_attempts(
    real_line, production_seeded, result
):
    db = production_seeded
    _, _, row = prepared(db)
    real_line[0].return_value = result
    delivery.dispatch_pending(db)
    assert db.get(CandidateOutreach, row.id).delivery_attempts == 0
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.SENT
    real_line[0].return_value = "200"
    clock.advance(timedelta(seconds=30))
    delivery.dispatch_pending(db)
    assert db.get(CandidateOutreach, row.id).delivery_status == "ACCEPTED"


@pytest.mark.parametrize("result", ["500", "TIMEOUT", "400"])
def test_delivery_failure_has_one_audit_and_advances_case(real_line, production_seeded, result):
    db = production_seeded
    case, _, row = prepared(db)
    real_line[0].return_value = result
    attempts = 1 if result == "400" else 3
    for _ in range(attempts):
        delivery.dispatch_pending(db, case_id=case.id)
        clock.advance(timedelta(seconds=30))
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.FAILED
    audits = list(
        db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.OFFER_DELIVERY_FAILED))
    )
    assert len(audits) == 1
    assert audits[0].payload["attempts"] == attempts
    assert db.get(StaffingCase, case.id).status != CaseStatus.FAILED


@pytest.mark.parametrize(
    "status", [OutreachStatus.ACCEPTED, OutreachStatus.CANCELLED, OutreachStatus.TIMEOUT]
)
def test_answer_or_cancellation_during_send_is_never_overwritten(
    real_line, production_seeded, status
):
    db = production_seeded
    _, _, row = prepared(db)

    def concurrent_answer(*args):
        db.get(CandidateOutreach, row.id).status = status
        db.commit()
        return "400"

    real_line[0].side_effect = concurrent_answer
    delivery.dispatch_pending(db)
    assert db.get(CandidateOutreach, row.id).status == status
    assert db.get(CandidateOutreach, row.id).delivery_status == "CANCELLED"


def test_expired_and_stopped_intents_do_not_send(real_line, production_seeded):
    db = production_seeded
    case, _, row = prepared(db)
    case.status = CaseStatus.RESOLVED
    db.commit()
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 0
    assert db.get(CandidateOutreach, row.id).delivery_status == "CANCELLED"


def test_missing_credentials_fall_back_without_intent(production_seeded, monkeypatch):
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", None)
    monkeypatch.setattr(settings, "line_channel_access_token", None)
    _, _, row = prepared(production_seeded)
    assert row.delivery_status is None


def test_two_connections_process_same_webhook_once(real_line, frozen_clock, restore_empty_database):
    with SessionLocal() as db:
        load(db)
        _, _, row = prepared(db)
        item = event(row)
    barrier = threading.Barrier(2)
    errors = []

    def worker():
        try:
            with SessionLocal() as session:
                barrier.wait(timeout=5)
                webhook.process_event(session, item)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(LineWebhookEvent)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFER_ACCEPTED)
            )
            == 1
        )
