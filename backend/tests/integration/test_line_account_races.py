"""Real PostgreSQL connections enforce single-use codes and single UID ownership."""

import threading
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuditLog, Contact, LineAccountLinkCode, LineWebhookEvent
from app.db.session import SessionLocal
from app.domain.enums import AuditAction
from app.integrations.line import client
from app.seed import load
from app.services import audit_service, line_account_service, line_webhook_service
from tests.integration.test_line_account_linking import issue, link_event


@pytest.fixture
def committed_codes(frozen_clock, restore_empty_database, monkeypatch):
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-signature-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-access-token"))
    monkeypatch.setattr(client, "reply", Mock(return_value="200"))
    with SessionLocal() as db:
        load(db)
        return issue(db), issue(db, 202)


def run_events(items):
    barrier = threading.Barrier(2)
    errors = []

    def worker(item):
        try:
            with SessionLocal() as db:
                db.execute(text("SET LOCAL statement_timeout = '5s'"))
                barrier.wait(timeout=5)
                line_webhook_service.process_event(db, item)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(item,)) for item in items]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert all(not thread.is_alive() for thread in threads)
    assert not errors


@pytest.mark.parametrize("same_event", [True, False])
def test_same_code_is_consumed_once_across_connections(committed_codes, same_event):
    raw, _ = committed_codes
    items = [
        link_event(raw, "E1", "U201"),
        link_event(raw, "E1" if same_event else "E2", "U201" if same_event else "U-other"),
    ]
    run_events(items)
    with SessionLocal() as db:
        assert (
            db.scalar(select(func.count()).select_from(Contact).where(Contact.staff_id == 201)) == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(LineAccountLinkCode)
                .where(LineAccountLinkCode.used_at.is_not(None))
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.LINE_ACCOUNT_LINKED)
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(LineWebhookEvent)) == (
            1 if same_event else 2
        )
    assert client.reply.call_count == (1 if same_event else 2)


def test_two_staff_race_one_uid_and_unique_failure_keeps_losing_code_unused(
    committed_codes, monkeypatch
):
    first, second = committed_codes
    both_saw_no_owner = threading.Barrier(2)
    original = Session.scalar

    def force_unique_race(self, statement, *args, **kwargs):
        result = original(self, statement, *args, **kwargs)
        # Both connections see the UID unused before either insert. This forces
        # the loser through the database uniqueness violation, not just precheck.
        query = str(statement)
        if query.startswith("SELECT contacts.id") and "contacts.line_uid =" in query:
            assert result is None
            both_saw_no_owner.wait(timeout=5)
        return result

    monkeypatch.setattr(Session, "scalar", force_unique_race)
    run_events([link_event(first, "E1", "U-shared"), link_event(second, "E2", "U-shared")])
    monkeypatch.setattr(Session, "scalar", original)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Contact)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(LineAccountLinkCode)
                .where(LineAccountLinkCode.used_at.is_not(None))
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.LINE_ACCOUNT_LINKED)
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(LineWebhookEvent)) == 2
        unused = db.scalar(
            select(LineAccountLinkCode.code_hash).where(LineAccountLinkCode.used_at.is_(None))
        )
        losing = first if line_account_service.hash_code(first) == unused else second
        line_webhook_service.process_event(db, link_event(losing, "E3", "U-second-account"))
        assert db.scalar(select(func.count()).select_from(Contact)) == 2


def test_unlink_waits_for_link_without_deadlock(committed_codes, monkeypatch):
    raw, _ = committed_codes
    linked, release, unlink_started = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original = audit_service.log

    def pause_before_commit(db, **kwargs):
        original(db, **kwargs)
        if kwargs["action"] == AuditAction.LINE_ACCOUNT_LINKED:
            linked.set()
            assert release.wait(5)

    monkeypatch.setattr(audit_service, "log", pause_before_commit)

    def link():
        try:
            with SessionLocal() as db:
                db.execute(text("SET LOCAL statement_timeout = '5s'"))
                line_webhook_service.process_event(db, link_event(raw))
        except Exception as error:
            errors.append(error)

    def unlink():
        try:
            with SessionLocal() as db:
                db.execute(text("SET LOCAL statement_timeout = '5s'"))
                unlink_started.set()
                line_account_service.unlink(db, 201)
                db.commit()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=link)
    second = threading.Thread(target=unlink)
    first.start()
    try:
        assert linked.wait(5)
        second.start()
        assert unlink_started.wait(5)
    finally:
        release.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
    assert not first.is_alive() and not second.is_alive() and not errors
    with SessionLocal() as db:
        assert db.scalar(select(Contact.line_uid).where(Contact.staff_id == 201)) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.LINE_ACCOUNT_LINKED)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.LINE_ACCOUNT_UNLINKED)
            )
            == 1
        )
        assert db.get(LineWebhookEvent, "LINK1") is not None
