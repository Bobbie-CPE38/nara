"""Reserve acknowledgement/promotion and automatic timeout through real HTTP queues."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import clock
from app.core.config import settings
from app.db.models import ApprovalRequest, OfferOutcomeNotification
from app.db.session import SessionLocal
from app.main import app
from app.seed import load
from app.services import line_delivery_service as delivery
from app.services import line_webhook_service as webhook
from app.services import outreach_service
from tests.integration import test_line_messaging as line_tests
from tests.integration.case_rows import offer, short_case
from tests.integration.test_approval_timeout import accept, decide
from tests.integration.test_offer_outcome_notifications import bind

real_line = line_tests.real_line


def reserve(db):
    case, items = short_case(db)
    bind(db)
    first = offer(db, case, items[202])
    second = offer(db, case, items[201])
    db.commit()
    accept(db, first, staff=202)
    webhook.process_event(db, line_tests.event(second))
    request = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == first.id)
    ).one()
    return case, first, second, request


def promotion(db, offer_id):
    return db.scalars(
        select(OfferOutcomeNotification).where(
            OfferOutcomeNotification.outreach_id == offer_id,
            OfferOutcomeNotification.kind == "RESERVE_PROMOTED",
        )
    ).one()


def test_acknowledgement_reports_actual_reserve_not_solver_rank(production_seeded, real_line):
    db = production_seeded
    _, _, second, _ = reserve(db)
    assert second.accepted_as_reserve
    assert real_line[1].call_args.args[1] == (
        "บันทึกการตอบรับแล้ว ขณะนี้คุณเป็นตัวสำรอง กรุณารอการยืนยันก่อนเข้าเวร"
    )
    assert (
        db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.outreach_id == second.id))
        is None
    )
    # Redelivery neither repeats the acknowledgement nor sends a promotion.
    webhook.process_event(db, line_tests.event(second))
    assert real_line[1].call_count == 1
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0


def test_first_acceptance_is_not_called_a_reserve(production_seeded, real_line):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    row = offer(db, case, items[201])
    db.commit()
    webhook.process_event(db, line_tests.event(row))
    assert not row.accepted_as_reserve
    assert "ตัวสำรอง" not in real_line[1].call_args.args[1]
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0


def test_promotion_pushes_once_then_can_have_a_separate_final_outcome(production_seeded, real_line):
    db = production_seeded
    _, _, second, request = reserve(db)
    decide(db, request, approved=False)
    notice = promotion(db, second.id)
    assert notice.delivery_status == "ACCEPTED"
    assert "ได้รับเลือกจากรายชื่อตัวสำรองแล้ว" in notice.message
    assert "กำลังรอหัวหน้าอนุมัติ" in notice.message
    assert "ยังไม่ยืนยันให้เข้าเวร" in notice.message
    assert "หอ ICU" in notice.message and f"#{second.id}" in notice.message
    mine = outreach_service.list_offers(db, staff_id=201)
    assert len(mine) == 1 and mine[0].final_outcome is None  # Progress is not a failure.
    promoted_request = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == second.id)
    ).one()
    delivery.dispatch_pending(db)
    assert sum(c.args[0] == notice.delivery_payload for c in real_line[0].call_args_list) == 1
    decide(db, promoted_request, approved=False)
    outcomes = list(
        db.scalars(
            select(OfferOutcomeNotification)
            .where(OfferOutcomeNotification.outreach_id == second.id)
            .order_by(OfferOutcomeNotification.id)
        )
    )
    assert [(n.kind, n.reason) for n in outcomes] == [
        ("RESERVE_PROMOTED", "RESERVE_PROMOTED"),
        ("FINAL", "APPROVAL_REJECTED"),
    ]
    mine = outreach_service.list_offers(db, staff_id=201)
    assert len(mine) == 1 and mine[0].final_outcome == "APPROVAL_REJECTED"


@pytest.mark.parametrize("decided", [True, False])
def test_promotion_retry_does_not_contradict_decision_or_expired_approval(
    production_seeded, real_line, decided
):
    db = production_seeded
    _, _, second, request = reserve(db)
    real_line[0].return_value = "500"
    decide(db, request, approved=False)
    notice = promotion(db, second.id)
    assert notice.delivery_status == "PENDING"
    my_request = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == second.id)
    ).one()
    if decided:
        real_line[0].return_value = "200"
        decide(db, my_request, approved=True)
    else:
        clock.advance(timedelta(seconds=900))
    clock.advance(timedelta(seconds=30))
    delivery.dispatch_pending(db)
    assert notice.delivery_status == "CANCELLED"
    assert sum(c.args[0] == notice.delivery_payload for c in real_line[0].call_args_list) == 1


@pytest.mark.parametrize("route", ["/demo/clock/advance", "/internal/merge-windows/close-due"])
@pytest.mark.parametrize("first_result", ["200", "TIMEOUT"])
def test_expiry_http_route_pushes_automatically_without_any_offer_button(
    frozen_clock, restore_empty_database, real_line, monkeypatch, route, first_result
):
    monkeypatch.setattr(settings, "internal_job_secret", "test-job-secret")
    real_line[0].side_effect = [first_result, "200"]
    with SessionLocal() as db:
        load(db)
        case, items = short_case(db)
        bind(db)
        row = offer(db, case, items[201])
        db.commit()
        offer_id = row.id
    # The job sees time already at the deadline; it must not depend on a nurse
    # clicking a webhook button or reading an offer page to write/send expiry.
    if route.startswith("/internal"):
        clock.advance(timedelta(seconds=300))
    with TestClient(app) as client:
        response = client.post(
            route,
            json={"seconds": 300} if route.startswith("/demo") else None,
            headers={"X-Internal-Secret": "test-job-secret"},
        )
        assert response.status_code == 200, response.text
        if first_result == "TIMEOUT":
            # Recovery needs only another clock/job tick, never a nurse's click.
            clock.advance(timedelta(seconds=30))
            retry = client.post(
                "/internal/merge-windows/close-due",
                headers={"X-Internal-Secret": "test-job-secret"},
            )
            assert retry.status_code == 200
    with SessionLocal() as db:
        notice = db.scalars(
            select(OfferOutcomeNotification).where(
                OfferOutcomeNotification.outreach_id == offer_id,
                OfferOutcomeNotification.kind == "FINAL",
            )
        ).one()
        assert notice.reason == "OFFER_TIMEOUT" and notice.delivery_status == "ACCEPTED"
        assert sum(c.args[0] == notice.delivery_payload for c in real_line[0].call_args_list) == (
            2 if first_result == "TIMEOUT" else 1
        )
        # The separate expired-button reply is still available after that push.
        webhook.process_event(
            db, line_tests.event(db.get(type(row), offer_id), event_id="late-click")
        )
        assert (
            real_line[1].call_args.args[1].removeprefix("ข้อเสนอนี้")
            == "หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้"
        )
