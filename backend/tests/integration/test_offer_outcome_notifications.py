"""Issue 98: final outcomes, durable delivery, and replies to expired buttons."""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core import clock
from app.core.config import settings
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    Contact,
    OfferOutcomeNotification,
    Shift,
    Staff,
    StaffingCase,
    StructuredHandover,
)
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CaseStatus, EntityType, OutreachStatus
from app.seed import load
from app.services import (
    actor_service,
    approval_service,
    approval_timeout_service,
    audit_service,
    offer_outcome_service,
    offer_timeout_service,
    outreach_service,
    roster_service,
)
from app.services import line_delivery_service as delivery
from app.services import line_webhook_service as webhook
from tests.integration import test_line_messaging as line_tests
from tests.integration.case_rows import approval, offer, short_case
from tests.integration.test_approval_timeout import decide, pending
from tests.integration.test_line_messaging import event

real_line = line_tests.real_line


def notification(db, outreach_id):
    return db.scalars(
        select(OfferOutcomeNotification)
        .where(
            OfferOutcomeNotification.outreach_id == outreach_id,
            OfferOutcomeNotification.kind == "FINAL",
        )
        .execution_options(populate_existing=True)
    ).one()


def bind(db, staff_id=201):
    db.add(Contact(staff_id=staff_id, line_uid=f"U{staff_id}", is_active=True))
    db.flush()


def log_outcome(db, case, row, action=AuditAction.APPROVAL_REJECTED, payload=None):
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.user_id(db, 900),
        action=action,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=row.id,
        payload=payload if payload is not None else {"outreach_id": row.id},
    )


def cancelled(db, *, bound=True, action=AuditAction.APPROVAL_REJECTED, payload=None):
    case, items = short_case(db)
    if bound:
        bind(db)
    row = offer(db, case, items[201], OutreachStatus.CANCELLED)
    log_outcome(db, case, row, action, payload)
    db.commit()
    return case, items, row, notification(db, row.id)


@pytest.mark.parametrize(
    "action,reason",
    list(offer_outcome_service.DIRECT_REASONS.items()),
)
def test_authoritative_outcomes_have_distinct_safe_messages(
    production_seeded, real_line, action, reason
):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    shift = db.get(Shift, case.shift_id)
    # Partial and overnight covers must not be labelled as the whole shift.
    items[201].cover_start_at = shift.start_at + timedelta(hours=2)
    items[201].cover_end_at = shift.end_at
    row = offer(
        db,
        case,
        items[201],
        OutreachStatus.TIMEOUT if reason == "OFFER_TIMEOUT" else OutreachStatus.CANCELLED,
    )
    log_outcome(db, case, row, action, {"outreach_id": row.id, "reason": "private internal detail"})
    out = notification(db, row.id)
    assert out.reason == reason
    assert "10/10/2026" in out.message and "01:00" in out.message and "07:00" in out.message
    assert "หอ ICU" in out.message and f"#{row.id}" in out.message
    assert "คุณไม่ได้รับมอบหมายให้เข้าเวรจากข้อเสนอนี้" in out.message
    assert "private internal detail" not in out.message
    assert out.delivery_status == "PENDING"
    real_line[0].assert_not_called()
    db.commit()
    delivery.dispatch_pending(db)
    real_line[0].assert_called_once_with(out.delivery_payload, out.delivery_retry_key)
    assert out.delivery_status == "ACCEPTED"


@pytest.mark.parametrize("action,reason", list(offer_outcome_service.LIST_REASONS.items()))
def test_batch_cancellations_notify_each_offer_once(production_seeded, real_line, action, reason):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    bind(db, 202)
    rows = [offer(db, case, items[s], OutreachStatus.CANCELLED) for s in (201, 202)]
    payload = {"cancelled_outreach_ids": [r.id for r in rows]}
    for _ in range(2):
        log_outcome(db, case, rows[0], action, payload)
    db.commit()
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 2
    assert [r.reason for r in db.scalars(select(OfferOutcomeNotification))] == [reason, reason]


@pytest.mark.parametrize(
    "action,reason",
    [
        (AuditAction.OFFER_CANCELLED_NOT_NEEDED, "NO_LONGER_NEEDED"),
        (AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT, "CONFLICTING_ASSIGNMENT"),
    ],
)
def test_singular_cancellation_audits_are_supported(production_seeded, real_line, action, reason):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    row = offer(db, case, items[201], OutreachStatus.CANCELLED)
    log_outcome(db, case, row, action, {"cancelled_outreach_id": row.id})
    assert notification(db, row.id).reason == reason


def test_human_rejection_uses_real_decision_and_does_not_change_the_outcome(
    production_seeded, real_line
):
    db = production_seeded
    bind(db)
    case, _, row, request = pending(db)
    decide(db, request, approved=False)
    out = notification(db, row.id)
    assert out.reason == "APPROVAL_REJECTED"
    assert out.delivery_status == "ACCEPTED"
    assert row.status == OutreachStatus.CANCELLED
    assert request.is_approved is False
    delivery.dispatch_pending(db)
    assert sum(c.args[0] == out.delivery_payload for c in real_line[0].call_args_list) == 1


def test_approval_timeout_notifies_once_and_keeps_the_retry_rules(production_seeded, real_line):
    db = production_seeded
    bind(db)
    _, _, row, request = pending(db)
    clock.advance(timedelta(seconds=900))
    approval_timeout_service.expire_due_approvals(db)
    assert notification(db, row.id).reason == "APPROVAL_TIMEOUT"
    assert request.is_timed_out and row.status == OutreachStatus.CANCELLED
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 1


def test_timeout_push_and_expired_button_reply_both_work_before_and_after_job(
    production_seeded, real_line
):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    row = offer(db, case, items[201])
    db.commit()
    clock.advance(timedelta(seconds=300))
    webhook.process_event(db, event(row, event_id="before-job"))
    assert real_line[1].call_args.args[1] == "ข้อเสนอนี้หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้"
    assert row.status == OutreachStatus.SENT
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0
    offer_timeout_service.expire_due_offers(db)
    out = notification(db, row.id)
    assert out.reason == "OFFER_TIMEOUT" and out.delivery_status == "ACCEPTED"
    # A stopped case must not turn the expired-button reply into a generic error.
    case.status = CaseStatus.MANUAL_HANDOFF
    db.commit()
    webhook.process_event(db, event(row, event_id="after-job"))
    assert real_line[1].call_count == 2
    assert real_line[1].call_args.args[1] == "ข้อเสนอนี้หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้"
    assert sum(c.args[0] == out.delivery_payload for c in real_line[0].call_args_list) == 1


def test_own_rejection_does_not_add_a_final_push(production_seeded, real_line):
    db = production_seeded
    case, items = short_case(db)
    bind(db)
    row = offer(db, case, items[201])
    db.commit()
    webhook.process_event(db, event(row, response="REJECT"))
    assert "บันทึกการปฏิเสธ" in real_line[1].call_args.args[1]
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0


@pytest.mark.parametrize(
    "result,expected,attempts",
    [
        ("200", "ACCEPTED", 1),
        ("409", "ACCEPTED", 1),
        ("400", "FAILED", 1),
        ("500", "FAILED", 3),
        ("TIMEOUT", "FAILED", 3),
    ],
)
def test_delivery_result_only_changes_notification(
    production_seeded, real_line, result, expected, attempts
):
    db = production_seeded
    case, _, row, out = cancelled(db)
    original_status = case.status
    audits = db.scalar(select(func.count()).select_from(AuditLog))
    real_line[0].return_value = result
    for _ in range(3):
        delivery.dispatch_pending(db)
        clock.advance(timedelta(seconds=30))
    assert out.delivery_status == expected and out.delivery_attempts == attempts
    assert real_line[0].call_count == attempts
    assert all(c == real_line[0].call_args_list[0] for c in real_line[0].call_args_list)
    assert case.status == original_status and row.status == OutreachStatus.CANCELLED
    assert db.scalar(select(func.count()).select_from(AuditLog)) == audits


@pytest.mark.parametrize("result", ["401", "403", "429"])
def test_configuration_failures_defer_without_spending_attempts(
    production_seeded, real_line, result
):
    db = production_seeded
    _, _, _, out = cancelled(db)
    real_line[0].return_value = result
    delivery.dispatch_pending(db)
    assert out.delivery_status == "PENDING" and out.delivery_attempts == 0
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 1
    clock.advance(timedelta(seconds=30))
    real_line[0].return_value = "200"
    delivery.dispatch_pending(db)
    assert out.delivery_status == "ACCEPTED" and out.delivery_attempts == 1


def test_lease_recovery_uses_same_message_and_stale_worker_cannot_finish(
    production_seeded, real_line
):
    db = production_seeded
    _, _, _, out = cancelled(db)
    claim = delivery._claim_outcome(db, out.id)
    assert claim is not None
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()
    clock.advance(timedelta(seconds=60))
    delivery.dispatch_pending(db)
    real_line[0].assert_called_once_with(claim.payload, claim.retry_key)
    delivery._finish_outcome(db, claim, "400")
    assert out.delivery_status == "ACCEPTED"


@pytest.mark.parametrize("change", ["missing", "unlink", "rebind"])
def test_no_contact_is_terminal_and_never_redirects(production_seeded, real_line, change):
    db = production_seeded
    _, _, _, out = cancelled(db, bound=change != "missing")
    if change == "missing":
        assert out.delivery_payload is None and out.delivery_retry_key is None
    else:
        contact = db.scalars(select(Contact).where(Contact.line_uid == "U201")).one()
        contact.is_active = False
        if change == "rebind":
            db.add(Contact(staff_id=201, line_uid="Unew", is_active=True))
        db.commit()
    delivery.dispatch_pending(db)
    db.refresh(out)
    assert out.delivery_status == "NO_CONTACT" and out.delivery_attempts == 0
    real_line[0].assert_not_called()


def test_rollback_removes_outcome_and_simulation_does_not_backfill(
    production_seeded, real_line, monkeypatch
):
    db = production_seeded
    case, items = short_case(db)
    row = offer(db, case, items[201], OutreachStatus.CANCELLED)
    db.commit()
    log_outcome(db, case, row)
    assert notification(db, row.id)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0
    monkeypatch.setattr(settings, "line_mode", "simulation")
    log_outcome(db, case, row)
    db.commit()
    out = notification(db, row.id)
    assert out.delivery_status is None
    assert outreach_service.list_offers(db, staff_id=201)[0].final_outcome == "APPROVAL_REJECTED"
    monkeypatch.setattr(settings, "line_mode", "real")
    bind(db)
    db.commit()
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()


def test_execution_failure_rolls_back_assignment_but_keeps_safe_final_notice(
    production_seeded, real_line
):
    db = production_seeded
    bind(db)
    case, _, row, request = pending(db)
    db.execute(
        delete(AuditLog).where(
            AuditLog.case_id == case.id, AuditLog.action == AuditAction.CASE_OPENED
        )
    )
    db.commit()
    decide(db, request)
    assert case.status == CaseStatus.FAILED and request.is_approved is True
    assert db.scalar(select(func.count()).select_from(StructuredHandover)) == 0
    out = notification(db, row.id)
    assert out.reason == "EXECUTION_FAILED" and "ยังไม่สามารถยืนยัน" in out.message
    assert "ไม่ได้รับอนุมัติ" not in out.message
    assert out.delivery_status == "ACCEPTED"
    assert outreach_service.list_offers(db, staff_id=201)[0].final_outcome == "EXECUTION_FAILED"


def test_new_assignment_suppresses_a_stale_failure_before_retry(production_seeded, real_line):
    db = production_seeded
    case, items, row, out = cancelled(db)
    real_line[0].return_value = "500"
    delivery.dispatch_pending(db)
    # The same case subsequently confirms this person's assignment.
    request = approval(db, case, items[201], approved=True)
    roster_service.create_replacement(db, case, approval=request)
    db.commit()
    clock.advance(timedelta(seconds=30))
    # Handover success can be delivered, but no second failure message.
    delivery.dispatch_pending(db)
    assert sum(c.args[0] == out.delivery_payload for c in real_line[0].call_args_list) == 1
    assert out.delivery_status == "CANCELLED"


def test_two_wards_partial_approval_sends_nothing_either_rejection_sends_once(
    production_seeded, real_line
):
    from tests.integration.test_approval_two_wards import build

    db = production_seeded
    bind(db)
    request_id, source_headers, _ = build(db)
    request = db.get(ApprovalRequest, request_id)
    decide(db, request)
    assert request.is_pending
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0
    source_id = int(source_headers["X-Demo-User"])
    source = db.get(Staff, source_id)
    approval_service.decide(
        db,
        approval_id=request_id,
        staff_id=source_id,
        role_id=source.role_id,
        home_ward_id=source.home_ward_id,
        actor_id=actor_service.user_id(db, source_id),
        approved=False,
        reason="cannot release",
    )
    out = notification(db, request.outreach_id)
    assert out.reason == "APPROVAL_REJECTED" and out.delivery_status == "ACCEPTED"
    delivery.dispatch_pending(db)
    assert sum(c.args[0] == out.delivery_payload for c in real_line[0].call_args_list) == 1


def test_two_workers_send_once_and_release_workflow_locks(
    frozen_clock, restore_empty_database, real_line
):
    with SessionLocal() as db:
        load(db)
        case, _, row, out = cancelled(db)
        case_id, oid = case.id, out.id
    started, release = threading.Event(), threading.Event()
    calls, errors = [], []

    def blocked(payload, retry_key):
        calls.append((payload, retry_key))
        started.set()
        assert release.wait(10)
        return "200"

    real_line[0].side_effect = blocked

    def sender():
        try:
            with SessionLocal() as db:
                delivery.dispatch_pending(db)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=sender)
    thread.start()
    try:
        assert started.wait(10)
        with SessionLocal() as db:
            db.execute(
                select(StaffingCase).where(StaffingCase.id == case_id).with_for_update(nowait=True)
            )
            db.rollback()
            delivery.dispatch_pending(db)
    finally:
        release.set()
        thread.join(15)
    assert not thread.is_alive() and not errors and len(calls) == 1
    with SessionLocal() as db:
        assert db.get(OfferOutcomeNotification, oid).delivery_status == "ACCEPTED"


def test_resolved_case_notifies_reserve_and_keeps_success_handover(production_seeded, real_line):
    from tests.integration.test_approval_timeout import accept

    db = production_seeded
    case, items = short_case(db)
    bind(db)
    bind(db, 202)
    first = offer(db, case, items[201])
    reserve = offer(db, case, items[202])
    db.commit()
    accept(db, first)
    accept(db, reserve, staff=202)
    request = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == first.id)
    ).one()
    decide(db, request)
    assert case.status == CaseStatus.RESOLVED
    assert first.status == OutreachStatus.ACCEPTED and reserve.status == OutreachStatus.CANCELLED
    assert (
        db.scalar(
            select(OfferOutcomeNotification.id).where(
                OfferOutcomeNotification.outreach_id == first.id
            )
        )
        is None
    )
    out = notification(db, reserve.id)
    assert out.reason == "CASE_RESOLVED" and out.delivery_status == "ACCEPTED"
    handover = db.scalars(select(StructuredHandover)).one()
    assert handover.incoming_staff_id == 201 and handover.delivery_status == "ACCEPTED"


def test_failed_transfer_notifies_after_both_wards_without_failing_case(
    production_seeded, real_line
):
    from app.db.models import CandidateItem, RosterAssignment
    from app.domain.enums import RosterStatus
    from tests.integration.test_approval_two_wards import build

    db = production_seeded
    bind(db)
    request_id, source_headers, _ = build(db)
    request = db.get(ApprovalRequest, request_id)
    item = db.get(CandidateItem, request.candidate_item_id)
    source_row = db.get(RosterAssignment, item.source_assignment_id)
    source_row.status = RosterStatus.CANCELLED
    db.commit()
    decide(db, request)
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0
    source = db.get(Staff, int(source_headers["X-Demo-User"]))
    approval_service.decide(
        db,
        approval_id=request_id,
        staff_id=source.id,
        role_id=source.role_id,
        home_ward_id=source.home_ward_id,
        actor_id=actor_service.user_id(db, source.id),
        approved=True,
    )
    out = notification(db, request.outreach_id)
    assert out.reason == "TRANSFER_CHECK_FAILED" and out.delivery_status == "ACCEPTED"
    assert db.get(StaffingCase, request.case_id).status != CaseStatus.FAILED


def test_success_committed_during_network_suppresses_the_finish(production_seeded, real_line):
    db = production_seeded
    case, items, _, out = cancelled(db)
    claim = delivery._claim_outcome(db, out.id)
    assert claim is not None
    request = approval(db, case, items[201], approved=True)
    roster_service.create_replacement(db, case, approval=request)
    db.commit()
    delivery._finish_outcome(db, claim, "500")
    assert out.delivery_status == "CANCELLED"  # No retry after the race.


def test_other_case_assignment_does_not_hide_this_outcome(production_seeded, real_line):
    db = production_seeded
    _, _, _, out = cancelled(db)
    other_case, other_items = short_case(db)
    request = approval(db, other_case, other_items[201], approved=True)
    roster_service.create_replacement(db, other_case, approval=request)
    db.commit()
    delivery.dispatch_pending(db)
    assert out.delivery_status == "ACCEPTED"
    assert any(c.args[0] == out.delivery_payload for c in real_line[0].call_args_list)
