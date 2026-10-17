"""PR S: snapshot reuse, explicit requests, shared quota and durable background work."""

import threading
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, CaseSummary, LlmCallLog, LlmDailyUsage, Shift, StaffingCase
from app.db.session import SessionLocal
from app.domain.enums import CaseStatus, ExplanationStatus, LlmCallStatus, LlmWorkType
from app.integrations.llm import fake
from app.main import app
from app.services import case_summary_service as service
from app.services import explanation_service, llm_service
from tests.integration.case_rows import short_case


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 4)
    monkeypatch.setattr(settings, "llm_max_retries", 1)


@pytest.fixture
def case(seeded):
    case, _ = short_case(seeded)
    seeded.commit()
    return case


@pytest.fixture
def client(seeded):
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def ask(client, case):
    return client.post(f"/cases/{case.id}/summary")


def current(client, case):
    return client.get(f"/cases/{case.id}").json()["summary"]["current"]


def rows(db):
    db.expire_all()
    return list(db.scalars(select(CaseSummary).order_by(CaseSummary.id)))


def test_reads_queue_nothing_and_time_alone_never_changes_the_snapshot(
    client, seeded, case, llm_on
):
    before = service.build_payload(seeded, case)
    assert current(client, case)["status"] == "NOT_REQUESTED"
    clock.advance(timedelta(days=60))
    seeded.expire_all()
    assert before == service.build_payload(seeded, case)
    assert service.run_pending(seeded) == 0
    assert rows(seeded) == []


def test_request_is_idempotent_and_a_ready_result_is_cached_when_llm_is_off(
    client, seeded, case, llm_on, monkeypatch
):
    audit_count = seeded.scalar(select(func.count()).select_from(AuditLog))
    assert ask(client, case).json()["current"]["status"] == "PENDING"
    assert ask(client, case).json()["current"]["status"] == "PENDING"
    assert len(rows(seeded)) == 1 and rows(seeded)[0].attempts == 0
    assert seeded.scalar(select(func.count()).select_from(LlmCallLog)) == 0
    assert service.run_pending(seeded) == 1
    ready = current(client, case)
    assert ready["status"] == "READY" and ready["text"].startswith("[fake]")
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 0)
    assert ask(client, case).json()["current"] == ready
    assert len(rows(seeded)) == 1
    assert seeded.scalar(select(func.count()).select_from(AuditLog)) == audit_count
    log = seeded.scalars(select(LlmCallLog)).one()
    assert (log.work_type, log.subject_id, log.case_id, log.attempt) == (
        LlmWorkType.CASE_SUMMARY,
        rows(seeded)[0].id,
        case.id,
        1,
    )
    assert log.plan_id is None and log.explanation_id is None


def test_changed_snapshot_keeps_the_old_text_as_stale_and_then_history(
    client, seeded, case, llm_on
):
    ask(client, case)
    service.run_pending(seeded)
    first = current(client, case)
    case.status = CaseStatus.MANUAL_HANDOFF
    seeded.commit()
    stale = current(client, case)
    assert stale["stale"] is True and stale["summary_id"] == first["summary_id"]
    assert stale["text"] == first["text"] and stale["can_request"] is True
    ask(client, case)
    service.run_pending(seeded)
    summary = client.get(f"/cases/{case.id}").json()["summary"]
    assert summary["current"]["stale"] is False
    assert summary["current"]["summary_id"] != first["summary_id"]
    assert [r["summary_id"] for r in summary["history"]] == [first["summary_id"]]
    assert rows(seeded)[0].text == first["text"]


def test_pending_worker_uses_the_frozen_snapshot_after_case_changes(
    client, seeded, case, llm_on, monkeypatch
):
    ask(client, case)
    frozen = rows(seeded)[0].input_payload
    case.status = CaseStatus.FAILED
    seeded.commit()
    captured = []

    def provider(request):
        assert not seeded.in_transaction()
        captured.append(request.payload)
        return fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", provider)
    service.run_pending(seeded)
    assert captured == [frozen]
    assert current(client, case)["stale"] is True
    assert seeded.get(StaffingCase, case.id).status == CaseStatus.FAILED


def test_no_identity_or_free_text_in_payload(client, seeded, case, llm_on):
    payload = service.build_payload(seeded, case)
    serialized = explanation_service.canonical_json(payload)
    for forbidden in ("staff_id", "first_name", "last_name", "line_uid", "Pimchanok", "reason"):
        assert forbidden not in serialized
    assert "assessed_gap" in payload and "roster" in payload


def test_bangkok_snapshot_is_stable_across_db_timezones_and_local_times_pass_validation(
    client, seeded, case, llm_on, monkeypatch
):
    shift = seeded.get(Shift, case.shift_id)
    shift.start_at = datetime.fromisoformat("2026-10-17T16:00:00+00:00")
    shift.end_at = datetime.fromisoformat("2026-10-18T00:00:00+00:00")
    seeded.commit()
    seeded.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    seeded.expire_all()
    utc_connection_payload = service.build_payload(seeded, case)
    seeded.execute(text("SET LOCAL TIME ZONE 'Asia/Bangkok'"))
    seeded.expire_all()
    payload = service.build_payload(seeded, case)
    assert payload == utc_connection_payload
    assert payload["shift"]["start_at"] == "2026-10-17T23:00:00+07:00"
    assert payload["shift"]["end_at"] == "2026-10-18T07:00:00+07:00"
    for window in payload["roster"] + payload["assessed_gap"]["intervals"]:
        assert window["start_at"].endswith("+07:00")
        assert window["end_at"].endswith("+07:00")

    original_generate = fake.generate
    sentence = "เวรเริ่ม 23:00 ถึง 07:00 น. ตามเวลาประเทศไทย"

    def provider(request):
        assert "Asia/Bangkok (+07:00)" in request.system
        return replace(original_generate(request), text=sentence)

    monkeypatch.setattr(fake, "generate", provider)
    assert ask(client, case).status_code == 200
    assert service.run_pending(seeded) == 1
    ready = current(client, case)
    assert ready["status"] == "READY" and ready["text"] == sentence
    assert seeded.scalars(select(LlmCallLog)).one().status == LlmCallStatus.SUCCEEDED


@pytest.mark.parametrize(
    "setting, value, status, code",
    [
        ("llm_enabled", False, 409, "LLM_UNAVAILABLE"),
        ("llm_daily_call_cap", 0, 429, "LLM_QUOTA_EXHAUSTED"),
        ("llm_max_input_tokens", 1, 409, "LLM_UNAVAILABLE"),
    ],
)
def test_refused_request_creates_nothing(
    client, seeded, case, llm_on, monkeypatch, setting, value, status, code
):
    monkeypatch.setattr(settings, setting, value)
    response = ask(client, case)
    assert response.status_code == status and response.json()["detail"]["code"] == code
    assert rows(seeded) == []
    assert seeded.scalar(select(func.count()).select_from(LlmDailyUsage)) == 0
    assert seeded.scalar(select(func.count()).select_from(LlmCallLog)) == 0


def test_unknown_case_is_404(client, llm_on):
    response = client.post("/cases/999999/summary")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "CASE_NOT_FOUND"


def test_quota_is_rechecked_after_queueing_and_shared_with_rank_explanation(
    client, seeded, case, llm_on, monkeypatch
):
    from app.workflow.handlers import optimize

    optimize.handle(seeded, case)
    seeded.commit()
    monkeypatch.setattr(settings, "llm_daily_call_cap", 1)
    ask(client, case)
    assert client.post(f"/cases/{case.id}/explanation").status_code == 200
    assert explanation_service.run_pending(seeded) == 1
    assert service.run_pending(seeded) == 1
    assert current(client, case)["status"] == "QUOTA_EXHAUSTED"
    assert current(client, case)["request_blocked_reason"] == "QUOTA_EXHAUSTED"
    assert seeded.scalar(select(func.count()).select_from(LlmCallLog)) == 1
    monkeypatch.setattr(settings, "llm_daily_call_cap", 2)
    assert ask(client, case).status_code == 200
    service.run_pending(seeded)
    assert current(client, case)["status"] == "READY"
    assert rows(seeded)[0].attempts == 1


@pytest.mark.parametrize("failure", [LlmCallStatus.TIMEOUT, LlmCallStatus.CONFIG_ERROR])
def test_failure_is_retryable_by_user_without_resetting_attempts(
    client, seeded, case, llm_on, monkeypatch, failure
):
    def broken(request):
        return replace(fake.generate(request), status=failure, text=None)

    monkeypatch.setattr(llm_service, "generate_explanation", broken)
    ask(client, case)
    service.run_pending(seeded)
    used = rows(seeded)[0].attempts
    assert used == (2 if failure == LlmCallStatus.TIMEOUT else 1)
    assert current(client, case)["status"] == "UNAVAILABLE"
    assert service.run_pending(seeded) == 0
    monkeypatch.setattr(llm_service, "generate_explanation", fake.generate)
    assert ask(client, case).status_code == 200
    service.run_pending(seeded)
    assert rows(seeded)[0].attempts == used + 1
    assert current(client, case)["status"] == "READY"


def test_lifetime_limit_is_reported_before_daily_quota(client, seeded, case, llm_on, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 2)
    monkeypatch.setattr(
        llm_service,
        "generate_explanation",
        lambda req: replace(fake.generate(req), status=LlmCallStatus.TIMEOUT, text=None),
    )
    ask(client, case)
    service.run_pending(seeded)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 0)
    response = ask(client, case)
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "LLM_ATTEMPTS_EXHAUSTED"
    )
    assert rows(seeded)[0].attempts == 2


def test_invalid_output_is_not_ready_and_case_still_works(
    client, seeded, case, llm_on, monkeypatch
):
    # Exercise the actual output validator, not a replacement for the gateway.
    original = fake.generate
    monkeypatch.setattr(
        fake, "generate", lambda req: replace(original(req), text="ผู้สมัคร 987654321 คน")
    )
    ask(client, case)
    service.run_pending(seeded)
    assert (
        current(client, case)["status"] == "UNAVAILABLE" and current(client, case)["text"] is None
    )
    assert current(client, case)["request_blocked_reason"] == "INVALID_INPUT"
    assert seeded.get(StaffingCase, case.id).status == CaseStatus.WAITING_RESPONSE


def test_claim_survives_crash_and_stops_at_attempt_limit(client, seeded, case, llm_on):
    ask(client, case)
    claim = service._claim(seeded)
    row = seeded.get(CaseSummary, claim.summary_id)
    row.attempts = row.attempt_limit
    row.lease_until = clock.now() - timedelta(days=100)
    seeded.commit()
    assert service.run_pending(seeded) == 0
    assert rows(seeded)[0].failure_reason == "ATTEMPTS_EXHAUSTED"


def test_http_job_schedules_summary_worker_after_response(client, case, llm_on, monkeypatch):
    from app.services import job_service
    from app.services.job_service import DueWork

    worker = Mock()
    monkeypatch.setattr(settings, "internal_job_secret", "test-summary-job-secret")
    monkeypatch.setattr(job_service, "run_due_work", lambda db: DueWork(closed_windows=[]))
    monkeypatch.setattr(service, "run_pending_in_new_session", worker)
    response = client.post(
        "/internal/merge-windows/close-due",
        headers={"X-Internal-Secret": "test-summary-job-secret"},
    )
    assert response.status_code == 200
    worker.assert_called_once_with()


def test_two_connections_request_one_snapshot_and_two_workers_send_once(
    frozen_clock, restore_empty_database, llm_on, monkeypatch
):
    db = SessionLocal()
    from app.seed import load

    load(db)
    case, _ = short_case(db)
    db.commit()
    case_id = case.id
    barrier = threading.Barrier(2)
    errors = []

    def ask_once():
        try:
            with SessionLocal() as session:
                barrier.wait(timeout=5)
                service.request(session, case_id)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=ask_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads) and not errors
    assert len(rows(db)) == 1
    started, release = threading.Event(), threading.Event()
    calls = []

    def provider(request):
        calls.append(request.payload)
        started.set()
        assert release.wait(timeout=10)
        return fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", provider)

    def work():
        with SessionLocal() as session:
            service.run_pending(session)

    first = threading.Thread(target=work)
    first.start()
    assert started.wait(timeout=10)
    # No summary lock is held during network I/O and another worker skips the lease.
    with SessionLocal() as session:
        session.execute(text("SET lock_timeout = '500ms'"))
        session.execute(select(CaseSummary).with_for_update()).all()
        session.rollback()
        assert service.run_pending(session) == 0
    release.set()
    first.join(timeout=10)
    assert not first.is_alive() and len(calls) == 1
    assert rows(db)[0].status == ExplanationStatus.READY
    db.close()


def test_reset_during_summary_call_preserves_usage_and_discards_old_snapshot(
    frozen_clock, restore_empty_database, llm_on, monkeypatch
):
    from app.seed import load
    from app.seed.reset import reset_demo

    with SessionLocal() as db:
        load(db)
        case, _ = short_case(db)
        db.commit()
        service.request(db, case.id)
    started, release = threading.Event(), threading.Event()
    errors = []

    def provider(request):
        started.set()
        assert release.wait(timeout=15)
        return fake.generate(request)

    def work():
        try:
            with SessionLocal() as session:
                service.run_pending(session)
        except Exception as error:
            errors.append(error)

    monkeypatch.setattr(llm_service, "generate_explanation", provider)
    worker = threading.Thread(target=work)
    worker.start()
    assert started.wait(timeout=10)
    try:
        reset_demo()
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and not errors
    with SessionLocal() as db:
        assert rows(db) == []
        log = db.scalars(select(LlmCallLog)).one()
        assert log.work_type == LlmWorkType.CASE_SUMMARY
        assert log.detached_at is not None and log.subject_id is None and log.case_id is None
        assert log.status == LlmCallStatus.SUCCEEDED
        assert db.scalars(select(LlmDailyUsage.used)).one() == 1
