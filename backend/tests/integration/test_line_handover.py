"""H2: durable delivery without workflow side effects and bound LINE check-in."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core import clock
from app.db.models import Attendance, AuditLog, Contact, LineWebhookEvent, Shift, StructuredHandover
from app.domain.enums import AuditAction, CaseStatus, RosterStatus
from app.services import attendance_service, handover_service
from app.services import line_delivery_service as delivery
from tests.integration import test_line_messaging as line_tests
from tests.integration.test_handover import created

real_line = line_tests.real_line
http_client = line_tests.http_client
signed = line_tests.signed


def ready(db):
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.flush()
    case, roster, handover = created(db)
    # Resolved cases must still deliver their assignment notification.
    case.status = CaseStatus.RESOLVED
    db.commit()
    return case, roster, handover


def test_intent_is_atomic_and_never_sends_before_commit(production_seeded, real_line):
    db = production_seeded
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.flush()
    case, roster, handover = created(db)
    db.flush()
    assert handover.delivery_status == "PENDING"
    assert handover.delivery_attempts == 0
    payload, key = handover.delivery_payload, handover.delivery_retry_key
    real_line[0].assert_not_called()
    handover_service.ensure(db, case=case, assignment=roster, actor_id=1)
    assert handover.delivery_payload == payload and handover.delivery_retry_key == key
    db.rollback()
    assert db.scalar(select(func.count()).select_from(StructuredHandover)) == 0
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()


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
def test_result_never_changes_assignment_or_case(
    production_seeded, real_line, result, expected, attempts
):
    db = production_seeded
    case, roster, handover = ready(db)
    real_line[0].return_value = result
    before = db.scalar(select(func.count()).select_from(AuditLog))
    for _ in range(3):
        delivery.dispatch_pending(db)
        clock.advance(timedelta(seconds=30))
    db.refresh(handover)
    assert handover.delivery_status == expected
    assert handover.delivery_attempts == attempts
    assert real_line[0].call_count == attempts
    assert roster.status == RosterStatus.ASSIGNED and case.status == CaseStatus.RESOLVED
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    calls = real_line[0].call_args_list
    assert all(c == calls[0] for c in calls)
    assert calls[0].args[0]["to"] == "U201"
    instructions = calls[0].args[0]["messages"][1]["template"]["text"]
    assert "กดได้ตั้งแต่ 09/10/2026 22:00:00 น." in instructions
    assert "ถึงก่อน 10/10/2026 07:00:00 น." in instructions
    assert len(instructions) <= 160
    assert (
        calls[0].args[0]["messages"][1]["template"]["actions"][0]["data"]
        == f"action=CHECK_IN&shift_id={roster.shift_id}"
    )


@pytest.mark.parametrize("result", ["401", "403", "429"])
def test_config_and_rate_limits_do_not_consume_attempts(production_seeded, real_line, result):
    db = production_seeded
    _, _, handover = ready(db)
    real_line[0].return_value = result
    delivery.dispatch_pending(db)
    assert handover.delivery_status == "PENDING" and handover.delivery_attempts == 0
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 1
    clock.advance(timedelta(seconds=30))
    real_line[0].return_value = "200"
    delivery.dispatch_pending(db)
    assert handover.delivery_status == "ACCEPTED" and handover.delivery_attempts == 1


def test_crash_recovery_reuses_lease_body_and_retry_key(production_seeded, real_line):
    db = production_seeded
    _, _, row = ready(db)
    claim = delivery._claim_handover(db, row.id)
    assert claim is not None
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()
    clock.advance(timedelta(seconds=60))
    delivery.dispatch_pending(db)
    real_line[0].assert_called_once_with(claim.payload, claim.retry_key)
    assert row.delivery_status == "ACCEPTED"
    # A stale worker may not overwrite the newer claim's result.
    delivery._finish_handover(db, claim, "400")
    assert row.delivery_status == "ACCEPTED"


@pytest.mark.parametrize("change", ["cancel", "end", "unlink", "rebind"])
def test_recheck_before_retry_cancels_stale_messages(production_seeded, real_line, change):
    db = production_seeded
    _, roster, row = ready(db)
    real_line[0].return_value = "500"
    delivery.dispatch_pending(db)
    if change == "cancel":
        roster.status = RosterStatus.CANCELLED
    elif change == "end":
        roster.actual_end_at = clock.now()
    else:
        contact = db.scalars(select(Contact).where(Contact.line_uid == "U201")).one()
        contact.is_active = False
        if change == "rebind":
            db.add(Contact(staff_id=201, line_uid="Unew", is_active=True))
    db.commit()
    clock.advance(timedelta(seconds=30))
    delivery.dispatch_pending(db)
    assert real_line[0].call_count == 1
    assert row.delivery_status == ("CANCELLED" if change in {"cancel", "end"} else "NO_CONTACT")
    assert row.delivery_payload["to"] == "U201"


def test_unbound_snapshot_is_terminal_without_payload_or_attempt(production_seeded, real_line):
    db = production_seeded
    _, _, row = created(db)
    db.commit()
    assert row.delivery_status == "NO_CONTACT"
    assert row.delivery_payload is None and row.delivery_retry_key is None
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()
    assert row.delivery_attempts == 0


def checkin_event(*, text="CHECKIN 1", data=None, uid="U101", event_id="checkin-1", source="user"):
    event = {
        "type": "message",
        "webhookEventId": event_id,
        "source": {"type": source, "userId": uid},
        "replyToken": "reply-checkin",
        "message": {"type": "text", "text": text},
    }
    if data is not None:
        event.update(type="postback", postback={"data": data})
    return event


def bind(db):
    db.add(Contact(staff_id=101, line_uid="U101", is_active=True))
    db.commit()
    shift = db.get(Shift, 1)
    clock.set_time(shift.start_at)
    return shift


def send(http_client, event):
    body, headers = signed([event])
    return http_client.post("/line/webhook", content=body, headers=headers)


@pytest.mark.parametrize("data", [None, "action=CHECK_IN&shift_id=1"])
def test_checkin_uses_bound_identity_and_dedups(production_seeded, real_line, http_client, data):
    db = production_seeded
    bind(db)
    event = checkin_event(text="checkin\n1", data=data)
    assert send(http_client, event).status_code == 200
    event["webhookEventId"] = "second-event"
    assert send(http_client, event).status_code == 200
    assert send(http_client, event).status_code == 200
    rows = list(db.scalars(select(Attendance).where(Attendance.shift_id == 1)))
    assert len(rows) == 1 and rows[0].staff_id == 101
    logs = list(
        db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.ATTENDANCE_CHECKED_IN))
    )
    assert len(logs) == 1 and logs[0].payload["source"] == "SELF"
    assert real_line[1].call_count == 2
    assert "ทันเวลา" in real_line[1].call_args.args[1]


@pytest.mark.parametrize(
    "delta,accepted,on_time",
    [
        (-3601, False, None),
        (-3600, True, True),
        (900, True, True),
        (901, True, False),
        (8 * 3600, False, None),
    ],
)
def test_checkin_boundaries_match_web(
    production_seeded, real_line, http_client, delta, accepted, on_time
):
    db = production_seeded
    shift = bind(db)
    clock.set_time(shift.start_at + timedelta(seconds=delta))
    assert send(http_client, checkin_event()).status_code == 200
    row = db.scalar(select(Attendance).where(Attendance.shift_id == 1))
    assert (row is not None) == accepted
    if accepted:
        assert ("ทันเวลา" if on_time else "มาสาย") in real_line[1].call_args.args[1]
    assert db.get(LineWebhookEvent, "checkin-1") is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"uid": "unknown"},
        {"source": "group"},
        {"text": "CHECKIN 1 102"},
        {"text": "CHECKIN 9223372036854775808"},
        {"text": "CHECKIN 2"},
        {"data": "action=CHECK_IN&shift_id=1&staff_id=102"},
        {"data": "action=CHECK_IN&shift_id=1&shift_id=2"},
    ],
)
def test_refused_commands_are_terminal_without_attendance(
    production_seeded, real_line, http_client, kwargs
):
    db = production_seeded
    bind(db)
    assert send(http_client, checkin_event(**kwargs)).status_code == 200
    assert (
        db.scalar(
            select(func.count()).select_from(Attendance).where(Attendance.shift_id.is_not(None))
        )
        == 0
    )
    assert db.get(LineWebhookEvent, "checkin-1") is not None


def test_checkin_failure_rolls_back_dedup_and_attendance(
    production_seeded, real_line, http_client, monkeypatch
):
    db = production_seeded
    bind(db)
    original = attendance_service.record

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("after attendance flush")

    monkeypatch.setattr(attendance_service, "record", fail)
    assert send(http_client, checkin_event()).status_code == 503
    assert db.get(LineWebhookEvent, "checkin-1") is None
    assert (
        db.scalar(select(func.count()).select_from(Attendance).where(Attendance.shift_id == 1)) == 0
    )
    real_line[1].assert_not_called()
    monkeypatch.setattr(attendance_service, "record", original)
    assert send(http_client, checkin_event()).status_code == 200


def test_repeat_checkin_after_end_returns_original_attendance(
    production_seeded, real_line, http_client
):
    db = production_seeded
    shift = bind(db)
    assert send(http_client, checkin_event()).status_code == 200
    original_time = db.scalar(select(Attendance.check_in_at).where(Attendance.shift_id == 1))
    clock.set_time(shift.end_at)
    assert send(http_client, checkin_event(event_id="after-end")).status_code == 200
    assert (
        db.scalar(select(Attendance.check_in_at).where(Attendance.shift_id == 1)) == original_time
    )
    assert "ทันเวลา" in real_line[1].call_args.args[1]


def test_accepted_payload_is_not_sent_again(production_seeded, real_line):
    db = production_seeded
    _, _, row = ready(db)
    original = row.delivery_payload
    delivery.dispatch_pending(db)
    delivery.dispatch_pending(db)
    assert row.delivery_payload == original
    real_line[0].assert_called_once_with(original, row.delivery_retry_key)


def test_network_releases_locks_and_two_workers_send_once(
    frozen_clock, restore_empty_database, real_line, monkeypatch
):
    import threading

    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.integrations.line import client
    from app.seed import load

    with SessionLocal() as db:
        load(db)
        case, roster, row = ready(db)
        row_id, roster_id = row.id, roster.id
    entered, release = threading.Event(), threading.Event()
    calls, errors = [], []

    def slow_push(*args):
        calls.append(args)
        entered.set()
        assert release.wait(5)
        return "200"

    monkeypatch.setattr(client, "push", slow_push)

    def worker():
        try:
            with SessionLocal() as db:
                delivery.dispatch_pending(db)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(5)
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '1s'"))
            # Both workflow rows are writable while the network is blocked.
            db.execute(text("SELECT id FROM shift WHERE id=1 FOR UPDATE"))
            db.execute(
                text("UPDATE roster_assignment SET status='CANCELLED' WHERE id=:id"),
                {"id": roster_id},
            )
            db.commit()
            delivery.dispatch_pending(db)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.get(StructuredHandover, row_id).delivery_status == "CANCELLED"


def test_simulation_snapshots_are_not_backfilled(production_seeded, real_line, monkeypatch):
    from app.core.config import settings

    db = production_seeded
    monkeypatch.setattr(settings, "line_mode", "simulation")
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.flush()
    case, roster, row = created(db)
    db.commit()
    assert row.delivery_status is None
    monkeypatch.setattr(settings, "line_mode", "real")
    handover_service.ensure(db, case=case, assignment=roster, actor_id=1)
    db.commit()
    delivery.dispatch_pending(db)
    real_line[0].assert_not_called()
    assert row.delivery_status is None


@pytest.mark.parametrize("same_event", [True, False])
def test_two_connections_check_in_once(frozen_clock, restore_empty_database, real_line, same_event):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.db.session import SessionLocal
    from app.seed import load
    from app.services import line_webhook_service

    with SessionLocal() as db:
        load(db)
        bind(db)
    barrier = threading.Barrier(2)

    def check(index):
        with SessionLocal() as db:
            barrier.wait(timeout=5)
            line_webhook_service.process_event(
                db, checkin_event(event_id="shared" if same_event else f"check-{index}")
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(check, i) for i in range(2)]
        for future in futures:
            future.result(timeout=10)
    with SessionLocal() as db:
        assert (
            db.scalar(select(func.count()).select_from(Attendance).where(Attendance.shift_id == 1))
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.ATTENDANCE_CHECKED_IN)
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(LineWebhookEvent)) == (
            1 if same_event else 2
        )
