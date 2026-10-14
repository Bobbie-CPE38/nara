"""Real PostgreSQL connections: lock restart, delivery/response and duplicate job races."""

import threading
from datetime import timedelta
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, CandidateOutreach, LineWebhookEvent, Staff
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CandidateResponse, OutreachStatus
from app.integrations.line import client
from app.seed import load
from app.services import actor_service, hard_rule_service, outreach_service
from app.services import line_delivery_service as delivery
from app.services import line_webhook_service as webhook
from tests.integration.test_line_messaging import event, prepared


@pytest.fixture
def race_case(frozen_clock, restore_empty_database, monkeypatch):
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-signature-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-access-token"))
    monkeypatch.setattr(client, "reply", Mock(return_value="200"))
    monkeypatch.setattr(client, "push", Mock(return_value="200"))
    with SessionLocal() as db:
        load(db)
        case, items, row = prepared(db)
        return case.id, items[202].id, row.id, event(row)


def test_actual_lock_restart_keeps_the_webhook_id(race_case, monkeypatch):
    case_id, item_id, row_id, item = race_case
    original = hard_rule_service.lock_staff
    calls = 0

    def insert_offer_between_lock_and_recheck(db, staff_ids):
        nonlocal calls
        original(db, staff_ids)
        calls += 1
        if calls == 1:
            with SessionLocal() as other:
                other.add(
                    CandidateOutreach(
                        case_id=case_id,
                        candidate_item_id=item_id,
                        channel="LINE",
                        sent_at=clock.now(),
                        expires_at=clock.now() + timedelta(seconds=300),
                        status=OutreachStatus.SENT,
                    )
                )
                other.commit()

    monkeypatch.setattr(hard_rule_service, "lock_staff", insert_offer_between_lock_and_recheck)
    with SessionLocal() as db:
        webhook.process_event(db, item)
        assert calls >= 2
        assert db.get(LineWebhookEvent, "E1") is not None
        assert db.get(CandidateOutreach, row_id).status == OutreachStatus.ACCEPTED
        webhook.process_event(db, item)
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFER_ACCEPTED)
            )
            == 1
        )


def test_response_can_commit_while_http_send_waits(race_case, monkeypatch):
    _, _, row_id, _ = race_case
    started, release = threading.Event(), threading.Event()
    errors = []

    def slow_push(*args):
        started.set()
        assert release.wait(5)
        return "400"

    monkeypatch.setattr(client, "push", slow_push)

    def sender():
        try:
            with SessionLocal() as db:
                delivery.dispatch_pending(db)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=sender)
    thread.start()
    try:
        assert started.wait(5)
        with SessionLocal() as db:
            # A send does not hold STAFF locks across HTTP.
            db.execute(select(Staff).where(Staff.id == 201).with_for_update(nowait=True))
            db.rollback()
            outreach_service.record_response(
                db,
                staff_id=201,
                actor_id=actor_service.user_id(db, 201),
                outreach_id=row_id,
                response=CandidateResponse.ACCEPT,
            )
        # A second job cannot resend the leased offer either.
        with SessionLocal() as db:
            delivery.dispatch_pending(db)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    with SessionLocal() as db:
        assert db.get(CandidateOutreach, row_id).status == OutreachStatus.ACCEPTED
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFER_DELIVERY_FAILED)
            )
            == 0
        )


def test_two_jobs_send_one_claim(race_case, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []

    def slow_push(*args):
        calls.append(args)
        started.set()
        assert release.wait(5)
        return "200"

    monkeypatch.setattr(client, "push", slow_push)

    def sender():
        with SessionLocal() as db:
            delivery.dispatch_pending(db)

    thread = threading.Thread(target=sender)
    thread.start()
    try:
        assert started.wait(5)
        with SessionLocal() as db:
            delivery.dispatch_pending(db)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    assert len(calls) == 1


@pytest.mark.parametrize("blocked_method", ["push", "reply"])
def test_http_response_precedes_line_network_work(race_case, monkeypatch, blocked_method):
    import asyncio

    from app.main import app
    from tests.integration.test_line_messaging import signed

    _, _, _, item = race_case
    # An unsupported postback gets a reply and queues no new wave. Queue the
    # existing intent explicitly to exercise push with a fresh background Session.
    item["postback"]["data"] = "invalid"
    original = webhook.process_event

    def process_and_queue(db, incoming):
        original(db, incoming)
        delivery.dispatch_pending(db)

    monkeypatch.setattr(webhook, "process_event", process_and_queue)
    started, release, response_sent = threading.Event(), threading.Event(), threading.Event()
    errors, statuses = [], []

    def blocked(*args):
        started.set()
        assert release.wait(5)
        return "200"

    monkeypatch.setattr(client, blocked_method, blocked)
    body, headers = signed([item])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/line/webhook",
        "raw_path": b"/line/webhook",
        "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "server": ("test", 80),
        "client": ("test", 1),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            response_sent.set()

    def request():
        try:
            asyncio.run(app(scope, receive, send))
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=request)
    thread.start()
    try:
        assert started.wait(5)
        assert response_sent.is_set()
        assert statuses == [200]
        with SessionLocal() as db:
            assert db.get(LineWebhookEvent, "E1") is not None
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    with SessionLocal() as db:
        # The delivery result is visible through an independent DB connection.
        assert db.get(CandidateOutreach, race_case[2]).delivery_status == "ACCEPTED"
