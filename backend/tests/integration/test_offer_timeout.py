"""PR O: backend-clock expiry, recovery sweep and independent PostgreSQL workers."""

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateOutreach,
    OutreachPolicy,
    StaffingCase,
)
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CandidateResponse, CaseStatus, OutreachStatus
from app.main import app
from app.seed import load
from app.services import (
    actor_service,
    audit_service,
    availability_service,
    case_facts_service,
    hard_rule_service,
    job_service,
    offer_timeout_service,
    outreach_service,
)
from app.workflow.handlers import contact_candidate
from tests.integration.case_rows import make_case, make_plan, offer, record_gap, short_case
from tests.integration.conftest import DEMO_NOW


def setup_wave(db):
    case, items = short_case(db, status=CaseStatus.OUTREACH)
    contact_candidate.handle(db, case)
    case.status = CaseStatus.WAITING_RESPONSE
    db.commit()
    rows = list(
        db.scalars(
            select(CandidateOutreach)
            .where(CandidateOutreach.case_id == case.id)
            .order_by(CandidateOutreach.id)
        )
    )
    db.commit()  # End the fixture's read savepoint before HTTP child sessions commit.
    return case, rows


@pytest.fixture
def client(production_seeded):
    def request_db():
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def answer(client, row, response="ACCEPT", staff=201):
    return client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": str(staff)},
        json={"outreach_id": row.id, "response": response},
    )


def test_expiry_is_a_wave_snapshot_not_a_live_policy_value(production_seeded):
    db = production_seeded
    policy = db.get(OutreachPolicy, 1)
    policy.offer_timeout_seconds = 120
    case, rows = setup_wave(db)
    assert len(rows) == 2 and {row.expires_at for row in rows} == {
        DEMO_NOW + timedelta(seconds=120)
    }
    policy.offer_timeout_seconds = 600
    db.commit()
    assert {row.expires_at for row in rows} == {DEMO_NOW + timedelta(seconds=120)}
    clock.advance(timedelta(seconds=120))
    result = job_service.run_due_work(db)
    assert result.timed_out_outreach_ids == [row.id for row in rows]
    new = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case.id, CandidateOutreach.status == OutreachStatus.SENT
        )
    ).one()
    assert new.expires_at == clock.now() + timedelta(seconds=600)


@pytest.mark.parametrize("response", ["ACCEPT", "REJECT"])
def test_deadline_is_exclusive_and_late_answer_is_read_only_before_job(
    client,
    production_seeded,
    response,
):
    db = production_seeded
    case, rows = setup_wave(db)
    clock.advance(timedelta(seconds=300))
    before = db.scalar(select(func.count()).select_from(AuditLog))
    assert answer(client, rows[0], response).status_code == 409
    db.expire_all()
    assert rows[0].status == OutreachStatus.SENT and rows[0].response_at is None
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    visible = client.get(
        "/demo/line-sim/offers?staff_id=201", headers={"X-Demo-User": "201"}
    ).json()[0]
    assert visible["blocked_reason"] == "OFFER_EXPIRED"
    assert not visible["can_accept"] and not visible["can_reject"]
    assert visible["expires_at"] == (DEMO_NOW + timedelta(seconds=300)).isoformat()
    assert not case_facts_service.has_open_offer(db, case.id)


def test_answer_one_microsecond_before_expiry_succeeds(client, production_seeded):
    _, rows = setup_wave(production_seeded)
    clock.advance(timedelta(seconds=300, microseconds=-1))
    assert answer(client, rows[0]).status_code == 200


def test_job_expires_whole_wave_audits_once_and_moves_to_next_wave(production_seeded):
    db = production_seeded
    case, rows = setup_wave(db)
    clock.advance(timedelta(seconds=299))
    assert job_service.run_due_work(db).timed_out_outreach_ids == []
    clock.advance(timedelta(seconds=1))
    assert job_service.run_due_work(db).timed_out_outreach_ids == [row.id for row in rows]
    audits = list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )
    actions = [row.action for row in audits]
    assert actions.count(AuditAction.OFFER_TIMEOUT) == 2
    assert actions[-3:] == [
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.OFFER_SENT,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    for row in rows:
        db.refresh(row)
        assert row.status == OutreachStatus.TIMEOUT and row.response_at is None
    before = len(audits)
    assert job_service.run_due_work(db).timed_out_outreach_ids == []
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    clock.advance(timedelta(seconds=300))
    assert len(job_service.run_due_work(db).timed_out_outreach_ids) == 1
    db.refresh(case)
    assert case.status == CaseStatus.MANUAL_HANDOFF


def test_accepted_reserve_and_pending_approval_do_not_time_out(client, production_seeded):
    db = production_seeded
    case, rows = setup_wave(db)
    assert answer(client, rows[0]).status_code == 200
    assert answer(client, rows[1], staff=202).status_code == 200
    count = db.scalar(select(func.count()).select_from(AuditLog))
    clock.advance(timedelta(seconds=300))
    work = job_service.run_due_work(db)
    assert work.timed_out_outreach_ids == work.recovered_case_ids == []
    db.expire_all()
    assert case.status == CaseStatus.WAITING_APPROVAL
    assert all(row.status == OutreachStatus.ACCEPTED for row in rows)
    assert db.scalars(select(ApprovalRequest)).one().is_pending
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count


@pytest.mark.parametrize("stopped", [CaseStatus.FAILED, CaseStatus.MANUAL_HANDOFF])
def test_expiry_cleans_sent_history_on_stopped_case_without_reopening_it(
    production_seeded, stopped
):
    db = production_seeded
    case, rows = setup_wave(db)
    case.status = stopped
    db.commit()
    clock.advance(timedelta(seconds=300))
    assert job_service.run_due_work(db).timed_out_outreach_ids == [row.id for row in rows]
    db.refresh(case)
    assert case.status == stopped


def test_recovery_restores_missed_accept_notification_without_cancelling_paused_offer(
    client, production_seeded
):
    db = production_seeded
    own, rows = setup_wave(db)
    # Separate case with its own recorded gap and a remaining candidate.
    other = make_case(db)
    record_gap(db, other)
    items = make_plan(db, other, (201, 202))
    paused = offer(db, other, items[201])
    db.commit()
    with patch.object(outreach_service, "recompute_affected_cases"):
        assert answer(client, rows[0]).status_code == 200
    assert other.status == CaseStatus.WAITING_RESPONSE
    work = job_service.run_due_work(db)
    assert other.id in work.recovered_case_ids
    db.refresh(paused)
    assert paused.status == OutreachStatus.SENT
    fresh = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == other.id,
            CandidateOutreach.candidate_item_id == items[202].id,
        )
    ).one()
    assert fresh.status == OutreachStatus.SENT


def test_paused_only_case_waits_until_deadline_then_hands_off(client, production_seeded):
    db = production_seeded
    _, rows = setup_wave(db)
    other = make_case(db)
    record_gap(db, other)
    item = make_plan(db, other, (201,))[201]
    paused = offer(db, other, item)
    db.commit()
    assert answer(client, rows[0]).status_code == 200
    assert other.id not in job_service.run_due_work(db).recovered_case_ids
    clock.advance(timedelta(seconds=300))
    work = job_service.run_due_work(db)
    assert paused.id in work.timed_out_outreach_ids
    db.refresh(other)
    assert other.status == CaseStatus.MANUAL_HANDOFF


def test_no_offer_recovery_retries_sending_without_repeating_contacted_staff(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    offer(db, case, items[201], OutreachStatus.CANCELLED)
    db.commit()
    assert case.id in job_service.run_due_work(db).recovered_case_ids
    sent = list(
        db.scalars(
            select(CandidateOutreach).where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.status == OutreachStatus.SENT,
            )
        )
    )
    assert {row.candidate_item_id for row in sent} == {items[202].id, items[203].id}


def test_demo_clock_and_internal_job_share_timeout_processing(
    client, production_seeded, monkeypatch
):
    from app.core.config import settings

    db = production_seeded
    case, rows = setup_wave(db)
    response = client.post("/demo/clock/advance", json={"seconds": 300})
    assert response.status_code == 200
    assert response.json()["closed_windows"] == []
    db.expire_all()
    assert all(row.status == OutreachStatus.TIMEOUT for row in rows)
    clock.advance(timedelta(seconds=300))
    monkeypatch.setattr(settings, "internal_job_secret", "test-only-job-secret")
    response = client.post(
        "/internal/merge-windows/close-due", headers={"X-Internal-Secret": "test-only-job-secret"}
    )
    assert response.status_code == 200
    db.refresh(case)
    assert case.status == CaseStatus.MANUAL_HANDOFF


def test_timeout_audit_failure_rolls_back_case_and_recovers_on_next_tick(production_seeded):
    db = production_seeded
    case, rows = setup_wave(db)
    clock.advance(timedelta(seconds=300))
    real_log = audit_service.log

    def fail_timeout(*args, **kwargs):
        if kwargs["action"] == AuditAction.OFFER_TIMEOUT:
            raise RuntimeError("audit unavailable")
        return real_log(*args, **kwargs)

    with patch.object(audit_service, "log", side_effect=fail_timeout):
        work = job_service.run_due_work(db)
    assert work.timed_out_outreach_ids == [] and case.id not in work.recovered_case_ids
    db.expire_all()
    assert all(row.status == OutreachStatus.SENT for row in rows)
    assert job_service.run_due_work(db).timed_out_outreach_ids == [row.id for row in rows]


def test_expiry_releases_offer_cap_before_the_next_job_tick(production_seeded):
    db = production_seeded
    db.get(OutreachPolicy, 1).maximum_concurrent_offers_per_staff = 1
    _, rows = setup_wave(db)
    assert availability_service.staff_at_offer_limit(db, [201]) == {201}
    clock.advance(timedelta(seconds=300))
    assert availability_service.staff_at_offer_limit(db, [201]) == set()
    assert rows[0].status == OutreachStatus.SENT  # Read paths never write TIMEOUT.


@pytest.fixture
def committed_wave(frozen_clock, restore_empty_database):
    with SessionLocal() as db:
        load(db)
        case, rows = setup_wave(db)
        ids = (case.id, [row.id for row in rows])
    yield ids


@pytest.mark.parametrize("accept_race", [False, True])
def test_two_jobs_or_response_racing_expiry_never_duplicate_outcomes(committed_wave, accept_race):
    case_id, offer_ids = committed_wave
    clock.advance(timedelta(seconds=300))
    barrier = threading.Barrier(2, timeout=10)
    errors = []
    outcomes = []

    def run(answering):
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                if answering:
                    try:
                        outreach_service.record_response(
                            db,
                            staff_id=201,
                            actor_id=actor_service.user_id(db, 201),
                            outreach_id=offer_ids[0],
                            response=CandidateResponse.ACCEPT,
                        )
                        outcomes.append("accepted")
                    except outreach_service.OpenOfferConflictError:
                        db.rollback()
                        outcomes.append("conflict")
                else:
                    job_service.run_due_work(db)
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(answering,), daemon=True)
        for answering in (False, accept_race)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    if accept_race:
        assert outcomes == ["conflict"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFER_TIMEOUT)
            )
            == 2
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(CandidateOutreach)
                .where(
                    CandidateOutreach.case_id == case_id,
                    CandidateOutreach.status == OutreachStatus.SENT,
                )
            )
            == 1
        )


def test_recovery_does_not_recompute_healthy_waiting_approval(production_seeded):
    from tests.integration.case_rows import approval

    db = production_seeded
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    offer(db, case, items[201], OutreachStatus.ACCEPTED)
    approval(db, case, items[201])
    db.commit()
    clock.advance(timedelta(seconds=300))
    with patch.object(outreach_service, "lock_case_for_outreach") as lock:
        work = job_service.run_due_work(db)
    lock.assert_not_called()
    assert work.timed_out_outreach_ids == work.recovered_case_ids == []
    assert case.status == CaseStatus.WAITING_APPROVAL


def test_recovery_unblocks_stale_waiting_approval_after_cancelled_acceptance(production_seeded):
    from tests.integration.case_rows import approval

    db = production_seeded
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    stale = offer(db, case, items[201], OutreachStatus.ACCEPTED)
    request = approval(db, case, items[201])
    stale.status = OutreachStatus.CANCELLED
    db.commit()
    assert case.id in job_service.run_due_work(db).recovered_case_ids
    db.refresh(case)
    assert case.status == CaseStatus.WAITING_RESPONSE
    assert request.is_pending  # No fake approval decision; inactive history is preserved.


def test_recovery_failure_does_not_starve_other_cases_and_retries_next_tick(production_seeded):
    db = production_seeded
    first, _ = short_case(db)
    second = make_case(db)
    record_gap(db, second)
    make_plan(db, second, (202,))
    db.commit()
    real_lock = outreach_service.lock_case_for_outreach

    def fail_first(db, case_id):
        if case_id == first.id:
            raise RuntimeError("temporary failure")
        return real_lock(db, case_id)

    with patch.object(outreach_service, "lock_case_for_outreach", side_effect=fail_first):
        work = job_service.run_due_work(db)
    assert first.id not in work.recovered_case_ids and second.id in work.recovered_case_ids
    assert first.id in job_service.run_due_work(db).recovered_case_ids


def test_due_timeouts_release_queued_window_in_same_tick(client, production_seeded):
    db = production_seeded
    first = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert first.status_code == 201
    queued = client.post(
        "/events",
        headers={"X-Demo-User": "104"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert queued.status_code == 201 and queued.json()["event_status"] == "RECEIVED"
    assert client.post("/demo/clock/advance", json={"seconds": 300}).json()["closed_windows"] == []
    closed = client.post("/demo/clock/advance", json={"seconds": 300})
    assert closed.status_code == 200
    window = closed.json()["closed_windows"][0]
    assert window["event_ids"] == [queued.json()["event_id"]]
    assert window["case_id"] != first.json()["case_id"]
    assert db.get(StaffingCase, first.json()["case_id"]).status == CaseStatus.MANUAL_HANDOFF
    fresh = list(
        db.scalars(select(CandidateOutreach).where(CandidateOutreach.case_id == window["case_id"]))
    )
    assert len(fresh) == 3 and all(row.status == OutreachStatus.SENT for row in fresh)
    assert {row.expires_at for row in fresh} == {clock.now() + timedelta(seconds=300)}


def test_accept_checked_before_deadline_survives_job_waiting_for_its_commit(
    committed_wave, monkeypatch
):
    case_id, ids = committed_wave
    clock.advance(timedelta(seconds=300, microseconds=-1))
    accepted = threading.Event()
    release = threading.Event()
    job_waiting = threading.Event()
    errors = []
    real_log = audit_service.log
    real_lock = outreach_service.lock_case_for_outreach

    def log(*args, **kwargs):
        real_log(*args, **kwargs)
        if kwargs["action"] == AuditAction.OFFER_ACCEPTED:
            accepted.set()
            assert release.wait(5)

    def lock(db, case_id):
        if threading.current_thread().name == "expiry-waiting":
            job_waiting.set()
        return real_lock(db, case_id)

    monkeypatch.setattr(audit_service, "log", log)
    monkeypatch.setattr(outreach_service, "lock_case_for_outreach", lock)

    def run(answering):
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                if answering:
                    outreach_service.record_response(
                        db,
                        staff_id=201,
                        actor_id=actor_service.user_id(db, 201),
                        outreach_id=ids[0],
                        response=CandidateResponse.ACCEPT,
                    )
                else:
                    job_service.run_due_work(db)
        except Exception as error:
            errors.append(error)

    response_thread = threading.Thread(target=run, args=(True,), daemon=True)
    job_thread = threading.Thread(target=run, args=(False,), name="expiry-waiting", daemon=True)
    response_thread.start()
    try:
        assert accepted.wait(5)
        clock.advance(timedelta(microseconds=1))
        job_thread.start()
        assert job_waiting.wait(5)
    finally:
        release.set()
        response_thread.join(15)
        if job_thread.ident is not None:
            job_thread.join(15)
    assert not response_thread.is_alive() and not job_thread.is_alive()
    assert not errors, errors
    with SessionLocal() as db:
        assert db.get(CandidateOutreach, ids[0]).status == OutreachStatus.ACCEPTED
        assert db.get(CandidateOutreach, ids[1]).status == OutreachStatus.TIMEOUT
        assert db.get(StaffingCase, case_id).status == CaseStatus.WAITING_APPROVAL
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFER_TIMEOUT)
            )
            == 1
        )


def test_workflow_failure_preserves_timeout_and_fails_case(production_seeded):
    db = production_seeded
    case = make_case(db)
    item = make_plan(db, case, (201,))[201]
    row = offer(db, case, item)
    db.commit()  # Missing gap is a genuine D11 workflow fault, not a timeout failure.
    clock.advance(timedelta(seconds=300))
    work = job_service.run_due_work(db)
    assert work.timed_out_outreach_ids == [row.id]
    db.refresh(case)
    db.refresh(row)
    assert case.status == CaseStatus.FAILED and row.status == OutreachStatus.TIMEOUT
    assert (
        db.scalar(select(AuditLog.id).where(AuditLog.action == AuditAction.WORKFLOW_FAILED))
        is not None
    )


@pytest.mark.parametrize(
    "phase", [CaseStatus.OUTREACH, CaseStatus.EXECUTING, CaseStatus.SAFETY_VALIDATION]
)
def test_expiry_commits_for_non_waiting_case_without_retry_loop(production_seeded, phase):
    db = production_seeded
    case, rows = setup_wave(db)
    case.status = phase
    db.commit()
    clock.advance(timedelta(seconds=300))
    result = offer_timeout_service.expire_due_offers(db)
    assert result.outreach_ids == [row.id for row in rows]
    assert not result.failed_case_ids
    db.refresh(case)
    assert case.status == phase
    assert all(db.get(CandidateOutreach, row.id).status == OutreachStatus.TIMEOUT for row in rows)
    assert offer_timeout_service.expire_due_offers(db).outreach_ids == []


def test_healthy_response_wait_takes_no_workflow_locks(production_seeded):
    db = production_seeded
    setup_wave(db)
    with patch.object(outreach_service, "lock_case_for_outreach") as lock:
        assert offer_timeout_service.recover_waiting_cases(db, excluded_case_ids=set()) == []
    lock.assert_not_called()


def test_recovery_rechecks_after_lock_when_preview_is_stale(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    db.commit()
    real_lock = outreach_service.lock_case_for_outreach

    def became_healthy(db, case_id):
        # Simulate an offer committed between the unlocked hint and the lock.
        offer(db, case, items[201])
        db.commit()
        return real_lock(db, case_id)

    with (
        patch.object(outreach_service, "lock_case_for_outreach", side_effect=became_healthy),
        patch.object(offer_timeout_service.orchestrator, "recompute") as recompute,
    ):
        assert offer_timeout_service.recover_waiting_cases(db, excluded_case_ids=set()) == []
    recompute.assert_not_called()


def test_offer_lock_restarts_when_new_offer_appears(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    db.commit()
    real_lock_staff = hard_rule_service.lock_staff
    calls = 0

    def change_once(db, staff_ids):
        nonlocal calls
        calls += 1
        real_lock_staff(db, staff_ids)
        if calls == 1:
            # Deterministically inject the phantom at the exact race boundary.
            offer(db, case, items[201])

    with (
        patch.object(hard_rule_service, "lock_staff", side_effect=change_once),
        patch.object(db, "rollback", wraps=db.rollback) as rollback,
    ):
        locked = outreach_service.lock_case_for_outreach(db, case.id)
    assert locked.id == case.id and calls == 2
    rollback.assert_called_once()
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0


def test_offer_lock_exhaustion_is_retryable_and_rolls_back(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    db.commit()
    real_lock_staff = hard_rule_service.lock_staff

    def change_every_time(db, staff_ids):
        real_lock_staff(db, staff_ids)
        offer(db, case, items[201])

    with (
        patch.object(hard_rule_service, "lock_staff", side_effect=change_every_time) as lock,
        patch.object(db, "rollback", wraps=db.rollback) as rollback,
        pytest.raises(outreach_service.OutreachLockRetryError),
    ):
        outreach_service.lock_case_for_outreach(db, case.id)
    assert lock.call_count == rollback.call_count == 5
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0
    assert not issubclass(
        outreach_service.OutreachLockRetryError, outreach_service.OpenOfferConflictError
    )


def test_response_lock_retry_returns_503_not_offer_conflict(client, production_seeded):
    _, rows = setup_wave(production_seeded)
    with patch.object(
        outreach_service,
        "lock_case_for_outreach",
        side_effect=outreach_service.OutreachLockRetryError("Retry response"),
    ):
        result = answer(client, rows[0])
    assert result.status_code == 503
    assert result.headers["Retry-After"] == "1"
    assert result.json()["detail"] == "Retry response"


def test_repeated_failure_logging_is_bounded():
    offer_timeout_service._failure_counts.clear()
    try:
        with patch.object(offer_timeout_service.logger, "exception") as log:
            for _ in range(120):
                offer_timeout_service._log_failure("Recovery", 999, RuntimeError("retry"))
        assert log.call_count == 2
        assert offer_timeout_service._failure_counts[("Recovery", 999, RuntimeError)] == 120
    finally:
        offer_timeout_service._failure_counts.clear()


@pytest.mark.parametrize(
    "leaving,final_status",
    [
        ((104, 105), CaseStatus.MANUAL_HANDOFF),
        ((105,), CaseStatus.RESOLVED),
    ],
)
@pytest.mark.parametrize("elapsed", [300, 301])
def test_case_completion_preserves_overdue_sent_for_timeout_job(
    client, production_seeded, leaving, final_status, elapsed
):
    db = production_seeded
    case, items = short_case(db, *leaving)
    rows = [offer(db, case, items[staff]) for staff in (201, 202, 203)]
    db.commit()
    assert answer(client, rows[0]).status_code == 200
    request_id = db.scalars(
        select(ApprovalRequest.id).where(
            ApprovalRequest.candidate_item_id == rows[0].candidate_item_id
        )
    ).one()
    db.commit()
    # Advance only the clock: deliberately do NOT tick the job before approval.
    clock.advance(timedelta(seconds=elapsed))
    response = client.post(
        f"/approvals/{request_id}/decision", headers={"X-Demo-User": "900"}, json={"approved": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["case_status"] == final_status.value
    db.expire_all()
    assert rows[0].status == OutreachStatus.ACCEPTED
    assert [row.status for row in rows[1:]] == [OutreachStatus.SENT] * 2
    final_audit = db.scalars(
        select(AuditLog).where(
            AuditLog.case_id == case.id,
            AuditLog.action
            == (
                AuditAction.CASE_RESOLVED
                if final_status == CaseStatus.RESOLVED
                else AuditAction.MANUAL_HANDOFF
            ),
        )
    ).one()
    assert final_audit.payload["cancelled_outreach_ids"] == []
    db.commit()
    result = job_service.run_due_work(db)
    assert result.timed_out_outreach_ids == [row.id for row in rows[1:]]
    db.expire_all()
    assert case.status == final_status
    assert rows[0].status == OutreachStatus.ACCEPTED
    assert [row.status for row in rows[1:]] == [OutreachStatus.TIMEOUT] * 2
    audits = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.case_id == case.id, AuditLog.action == AuditAction.OFFER_TIMEOUT)
            .order_by(AuditLog.id)
        )
    )
    assert [audit.entity_id for audit in audits] == [row.id for row in rows[1:]]
    assert all(audit.payload["staff_id"] in {202, 203} for audit in audits)
    assert all(row.response_at is None for row in rows[1:])
    db.commit()
    assert job_service.run_due_work(db).timed_out_outreach_ids == []


def test_new_exception_type_is_logged_and_success_clears_all_types():
    offer_timeout_service._failure_counts.clear()
    try:
        with patch.object(offer_timeout_service.logger, "exception") as log:
            offer_timeout_service._log_failure("Recovery", 999, RuntimeError("first"))
            offer_timeout_service._log_failure("Recovery", 999, RuntimeError("repeat"))
            offer_timeout_service._log_failure("Recovery", 999, ValueError("new failure"))
        assert log.call_count == 2
        offer_timeout_service._clear_failures("Recovery", 999)
        assert offer_timeout_service._failure_counts == {}
    finally:
        offer_timeout_service._failure_counts.clear()
