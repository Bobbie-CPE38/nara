"""Personal non-command messages are acknowledged, never interpreted or persisted."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.db.models import LineWebhookEvent
from app.db.session import SessionLocal
from app.services import line_webhook_service as webhook
from tests.integration import test_line_messaging as line_tests
from tests.integration.test_line_messaging import prepared, signed

http_client = line_tests.http_client
real_line = line_tests.real_line

GUIDANCE = (
    "หากต้องการตอบข้อเสนอเข้าเวร กรุณากดปุ่มในข้อความข้อเสนอที่ยังตอบได้ เพื่อบันทึกคำตอบ "
    "การพิมพ์แชตยังไม่ถือเป็นการตอบข้อเสนอค่ะ"
)


def message(text="รับเวรครับ", event_id="guidance-1"):
    return {
        "type": "message",
        "webhookEventId": event_id,
        "source": {"type": "user", "userId": "U201"},
        "replyToken": "guidance-reply",
        "message": {"type": "text", "text": text},
    }


def snapshot(db):
    # Every table except the dedup ledger must stay byte-for-byte unchanged.
    from app.db.base import Base

    return {
        table.name: list(db.execute(select(table).order_by(*table.primary_key.columns)).mappings())
        for table in Base.metadata.sorted_tables
        if table.name != "line_webhook_event"
    }


@pytest.mark.parametrize(
    "text", ["รับเวรครับ", "ไม่สะดวก", "accept all offers", "LINKED", "CHECKINNING"]
)
def test_message_only_replies_without_business_writes_or_text_storage(
    production_seeded,
    real_line,
    http_client,
    monkeypatch,
    caplog,
    text,
):
    db = production_seeded
    prepared(db)
    before = snapshot(db)
    forbidden = Mock(side_effect=AssertionError("Free text must not call business/LLM handlers"))
    monkeypatch.setattr(webhook.outreach_service, "record_response", forbidden)
    from app.services import llm_service

    monkeypatch.setattr(llm_service, "generate_explanation", forbidden)
    item = message(text)
    body, headers = signed([item])
    for _ in range(2):
        assert http_client.post("/line/webhook", content=body, headers=headers).status_code == 200
    real_line[1].assert_called_once_with("guidance-reply", GUIDANCE)
    forbidden.assert_not_called()
    assert snapshot(db) == before
    assert db.get(LineWebhookEvent, item["webhookEventId"]) is not None
    assert text not in caplog.text


@pytest.mark.parametrize("kind", ["image", "sticker"])
def test_non_text_personal_messages_receive_guidance(production_seeded, real_line, kind):
    prepared(production_seeded)
    item = message()
    item["message"] = {"type": kind}
    webhook.process_event(production_seeded, item)
    real_line[1].assert_called_once_with("guidance-reply", GUIDANCE)


@pytest.mark.parametrize(
    "source",
    [
        {"type": "group", "groupId": "test-group", "userId": "U201"},
        {"type": "room", "roomId": "test-room", "userId": "U201"},
        {"type": "user"},
        {"type": "user", "userId": ""},
        None,
    ],
)
def test_no_guidance_outside_identified_personal_chat(production_seeded, real_line, source):
    item = message()
    item["source"] = source
    webhook.process_event(production_seeded, item)
    real_line[1].assert_not_called()
    assert production_seeded.get(LineWebhookEvent, item["webhookEventId"]) is not None


def test_unbound_user_is_told_to_link(production_seeded, real_line):
    webhook.process_event(production_seeded, message())
    real_line[1].assert_called_once_with("guidance-reply", webhook._LINK_GUIDANCE)


@pytest.mark.parametrize("kind", ["follow", "unfollow", "unsend"])
def test_non_message_events_are_still_silent(production_seeded, real_line, kind):
    item = message()
    item["type"] = kind
    webhook.process_event(production_seeded, item)
    real_line[1].assert_not_called()


def test_guidance_dedup_commits_before_reply_and_failure_is_not_replayed(
    frozen_clock, restore_empty_database, real_line
):
    item = message()
    committed = []

    def reply(token, text):
        with SessionLocal() as other:
            committed.append(other.get(LineWebhookEvent, item["webhookEventId"]) is not None)
        raise RuntimeError("Fake reply failure")

    real_line[1].side_effect = reply
    with SessionLocal() as db:
        webhook.process_event(db, item)
        webhook.process_event(db, item)
    assert committed == [True]
    assert real_line[1].call_count == 1


def test_simultaneous_redelivery_sends_one_reply(frozen_clock, restore_empty_database, real_line):
    barrier = threading.Barrier(2)

    def receive():
        with SessionLocal() as db:
            barrier.wait(timeout=5)
            webhook.process_event(db, message())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(receive) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    real_line[1].assert_called_once_with("guidance-reply", webhook._LINK_GUIDANCE)


@pytest.mark.parametrize("state", ["idle", "expired", "closed", "assigned", "waiting", "reserve"])
def test_guidance_tracks_only_the_bound_nurses_actionable_or_waiting_offers(
    production_seeded, real_line, state
):
    from datetime import timedelta

    from app.core import clock
    from app.domain.enums import CaseStatus, OutreachStatus
    from tests.integration.test_approval_timeout import accept, decide
    from tests.integration.test_line_reserve_notifications import reserve
    from tests.integration.test_offer_outcome_notifications import bind

    db = production_seeded
    expected = webhook._IDLE_GUIDANCE
    if state == "idle":
        bind(db)
        db.commit()
    elif state == "reserve":
        reserve(db)
        expected = webhook._WAITING_GUIDANCE
    else:
        case, _, row = prepared(db)
        if state == "expired":
            clock.advance(timedelta(seconds=300))
        elif state == "closed":
            row.status = OutreachStatus.ACCEPTED
            case.status = CaseStatus.UNRESOLVED
            db.commit()
        elif state in {"waiting", "assigned"}:
            accept(db, row)
            if state == "assigned":
                from app.db.models import ApprovalRequest

                request = db.scalars(
                    select(ApprovalRequest).where(ApprovalRequest.outreach_id == row.id)
                ).one()
                decide(db, request, approved=True)
            else:
                expected = webhook._WAITING_GUIDANCE
    real_line[1].reset_mock()
    before = snapshot(db)
    webhook.process_event(db, message("สวัสดี"))
    real_line[1].assert_called_once_with("guidance-reply", expected)
    assert snapshot(db) == before


def test_other_nurses_offer_does_not_change_guidance(production_seeded, real_line):
    from app.db.models import Contact

    db = production_seeded
    prepared(db)  # 201 has an active offer, 202 does not.
    db.add(Contact(staff_id=202, line_uid="U202", is_active=True))
    db.commit()
    item = message()
    item["source"]["userId"] = "U202"
    webhook.process_event(db, item)
    real_line[1].assert_called_once_with("guidance-reply", webhook._IDLE_GUIDANCE)
