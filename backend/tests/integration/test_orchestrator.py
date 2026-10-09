"""The orchestrator against the seeded PostgreSQL: transitions, audit rows, commit and D11."""

import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.base import Base
from app.db.models import Actor, AuditLog, Role, StaffingCase, StaffingEvent
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
)
from app.domain.workflow.transitions import InvalidTransitionError
from app.seed import load
from app.services import actor_service, audit_service
from app.services.actor_service import ActorNotFoundError
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
LEAVING_STAFF_ID = 105
ACCEPTING_STAFF_ID = 201

CaseFactory = Callable[..., StaffingCase]


def _make_case(db: Session, status: CaseStatus) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=SHIFT_ID,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=SHIFT_ID,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


@pytest.fixture
def make_case(seeded: Session) -> CaseFactory:
    def factory(status: CaseStatus = CaseStatus.OPEN) -> StaffingCase:
        return _make_case(seeded, status)

    return factory


def _audit(db: Session, case: StaffingCase) -> list[AuditLog]:
    # Ordered by id: the frozen demo clock gives every row the same created_at
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


def _status_changes(db: Session, case: StaffingCase) -> list[tuple[str, str]]:
    return [
        (row.payload["from"], row.payload["to"])
        for row in _audit(db, case)
        if row.action is AuditAction.CASE_STATUS_CHANGED
    ]


def _status(db: Session, case: StaffingCase) -> CaseStatus:
    db.expire_all()
    return case.status


def _use_handler(
    monkeypatch: pytest.MonkeyPatch, status: CaseStatus, handler: orchestrator.Handler
) -> None:
    monkeypatch.setitem(orchestrator.HANDLERS, status, handler)


# --------------------------------------------------------------------------- #
# Golden path
# --------------------------------------------------------------------------- #
def test_every_automatic_status_has_exactly_one_handler() -> None:
    automatic = set(CaseStatus) - WAITING_CASE_STATUSES - AUTOMATION_STOPPED_STATUSES

    assert set(orchestrator.HANDLERS) == automatic


def test_advance_runs_an_open_case_to_waiting_response(
    seeded: Session, make_case: CaseFactory
) -> None:
    """The step 3 done condition: OPEN stops at WAITING_RESPONSE with 4 status changes."""
    case = make_case()

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.WAITING_RESPONSE
    assert _status_changes(seeded, case) == [
        ("OPEN", "ASSESSING"),
        ("ASSESSING", "OPTIMIZING"),
        ("OPTIMIZING", "OUTREACH"),
        ("OUTREACH", "WAITING_RESPONSE"),
    ]


def test_status_change_audit_row_follows_the_contract(
    seeded: Session, make_case: CaseFactory
) -> None:
    case = make_case()
    orchestrator_actor = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.WORKFLOW_ORCHESTRATOR.value)
    )

    orchestrator.advance(seeded, case.id)

    for row in _audit(seeded, case):
        assert row.action is AuditAction.CASE_STATUS_CHANGED
        assert row.actor_id == orchestrator_actor
        assert row.entity_type is EntityType.STAFFING_CASES
        assert row.entity_id == case.id
        assert set(row.payload) == {"from", "to"}


def test_full_golden_path_through_both_wait_points(seeded: Session, make_case: CaseFactory) -> None:
    case = make_case()

    orchestrator.advance(seeded, case.id)
    orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)
    assert _status(seeded, case) is CaseStatus.WAITING_APPROVAL
    orchestrator.resume(seeded, case.id, CaseStatus.EXECUTING)

    assert _status(seeded, case) is CaseStatus.RESOLVED
    assert _status_changes(seeded, case) == [
        ("OPEN", "ASSESSING"),
        ("ASSESSING", "OPTIMIZING"),
        ("OPTIMIZING", "OUTREACH"),
        ("OUTREACH", "WAITING_RESPONSE"),
        ("WAITING_RESPONSE", "SAFETY_VALIDATION"),
        ("SAFETY_VALIDATION", "WAITING_APPROVAL"),
        ("WAITING_APPROVAL", "EXECUTING"),
        ("EXECUTING", "RESOLVED"),
    ]


def test_status_change_updates_updated_at(seeded: Session, make_case: CaseFactory) -> None:
    case = make_case()
    later = clock.advance(timedelta(minutes=3))

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.created_at == DEMO_NOW
    assert case.updated_at == later


def test_a_round_commits_exactly_once(seeded: Session, make_case: CaseFactory) -> None:
    case = make_case()

    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        orchestrator.advance(seeded, case.id)

    assert commit.call_count == 1


@pytest.mark.parametrize(
    "status",
    sorted(WAITING_CASE_STATUSES | AUTOMATION_STOPPED_STATUSES),
)
def test_advance_does_nothing_at_a_wait_point_or_stopped_status(
    seeded: Session, make_case: CaseFactory, status: CaseStatus
) -> None:
    case = make_case(status)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is status
    assert _audit(seeded, case) == []


def test_unknown_case_raises(seeded: Session) -> None:
    with pytest.raises(orchestrator.CaseNotFoundError, match="999999"):
        orchestrator.advance(seeded, 999_999)


# --------------------------------------------------------------------------- #
# resume(): leaving a wait point
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("status", "next_status"),
    [
        # Not at a wait point
        (CaseStatus.OPEN, CaseStatus.ASSESSING),
        (CaseStatus.EXECUTING, CaseStatus.RESOLVED),
        (CaseStatus.RESOLVED, CaseStatus.FAILED),
        # At a wait point, but not an allowed transition
        (CaseStatus.WAITING_RESPONSE, CaseStatus.EXECUTING),
        (CaseStatus.WAITING_APPROVAL, CaseStatus.SAFETY_VALIDATION),
        (CaseStatus.WAITING_RESPONSE, CaseStatus.WAITING_RESPONSE),
        # FAILED is an allowed transition, but only the orchestrator's D11 path sets it
        (CaseStatus.WAITING_RESPONSE, CaseStatus.FAILED),
        (CaseStatus.WAITING_APPROVAL, CaseStatus.FAILED),
    ],
)
def test_resume_rejects_an_invalid_request_without_touching_the_case(
    seeded: Session, make_case: CaseFactory, status: CaseStatus, next_status: CaseStatus
) -> None:
    case = make_case(status)

    with pytest.raises(InvalidTransitionError):
        orchestrator.resume(seeded, case.id, next_status)

    assert _status(seeded, case) is status
    assert _audit(seeded, case) == []


def test_a_repeated_resume_is_rejected_and_does_not_fail_the_case(
    seeded: Session, make_case: CaseFactory
) -> None:
    """A second ACCEPT arrives after the case already moved on."""
    case = make_case(CaseStatus.WAITING_RESPONSE)
    orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)

    with pytest.raises(InvalidTransitionError):
        orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)

    assert _status(seeded, case) is CaseStatus.WAITING_APPROVAL


# --------------------------------------------------------------------------- #
# D11: a failing round
# --------------------------------------------------------------------------- #
def test_handler_exception_rolls_back_the_round_and_fails_the_case(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case()

    def failing_optimize(db: Session, case: StaffingCase) -> HandlerResult:
        db.add(Role(name="WRITTEN_BEFORE_THE_ERROR"))
        db.flush()
        raise RuntimeError("solver crashed")

    _use_handler(monkeypatch, CaseStatus.OPTIMIZING, failing_optimize)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.FAILED
    # The two changes made earlier in the same round were rolled back with it
    assert _status_changes(seeded, case) == [("OPEN", "FAILED")]
    assert seeded.scalar(select(Role).where(Role.name == "WRITTEN_BEFORE_THE_ERROR")) is None
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload == {
        "from": "OPEN",
        "failed_at": "OPTIMIZING",
        "error_type": "RuntimeError",
    }


def test_failure_keeps_the_callers_earlier_work(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """event_service writes the event, the case and its audit rows before advance()."""
    case = make_case()
    actor_id = seeded.scalar(select(Actor.id).where(Actor.staff_id == LEAVING_STAFF_ID))
    assert actor_id is not None
    audit_service.log(
        seeded,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.CASE_OPENED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={"event_id": case.event_id},
    )

    def failing_intake(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("boom")

    _use_handler(monkeypatch, CaseStatus.OPEN, failing_intake)

    orchestrator.advance(seeded, case.id)

    assert [row.action for row in _audit(seeded, case)] == [
        AuditAction.CASE_OPENED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.WORKFLOW_FAILED,
    ]
    assert seeded.get(StaffingEvent, case.event_id) is not None


def test_database_error_inside_a_handler_still_records_the_failure(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audit_service.log() flushes, so a bad actor_id breaks the transaction mid-round."""
    case = make_case()

    def handler_with_bad_audit(db: Session, case: StaffingCase) -> HandlerResult:
        audit_service.log(
            db,
            case_id=case.id,
            actor_id=999_999,
            action=AuditAction.GAP_ASSESSED,
            entity_type=EntityType.STAFFING_GAP,
            entity_id=None,
            payload={},
        )
        return HandlerResult(next_status=CaseStatus.OPTIMIZING)

    _use_handler(monkeypatch, CaseStatus.ASSESSING, handler_with_bad_audit)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.FAILED
    failure = _audit(seeded, case)[-1]
    assert failure.payload["failed_at"] == "ASSESSING"
    assert failure.payload["error_type"] == IntegrityError.__name__


def test_failure_after_a_wait_point_keeps_the_resume_transition(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The candidate did accept: that stays on the timeline even though safety crashed."""
    case = make_case(CaseStatus.WAITING_RESPONSE)

    def failing_safety(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("rule engine down")

    _use_handler(monkeypatch, CaseStatus.SAFETY_VALIDATION, failing_safety)

    orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)

    assert _status(seeded, case) is CaseStatus.FAILED
    assert _status_changes(seeded, case) == [
        ("WAITING_RESPONSE", "SAFETY_VALIDATION"),
        ("SAFETY_VALIDATION", "FAILED"),
    ]


def _returns(**result: Any) -> orchestrator.Handler:
    def handler(db: Session, case: StaffingCase) -> HandlerResult:
        return HandlerResult(**result)

    return handler


def _sets_status_itself(db: Session, case: StaffingCase) -> HandlerResult:
    case.status = CaseStatus.ASSESSING
    return HandlerResult(next_status=CaseStatus.ASSESSING)


@pytest.mark.parametrize(
    ("handler", "error_type"),
    [
        (_returns(next_status=CaseStatus.RESOLVED), "InvalidTransitionError"),
        (_returns(next_status=CaseStatus.OPEN), "InvalidTransitionError"),
        (_returns(next_status=CaseStatus.ASSESSING, wait=True), "WorkflowError"),
        (_sets_status_itself, "WorkflowError"),
        (_returns(next_status=CaseStatus.FAILED), "WorkflowError"),
    ],
    ids=[
        "skips_states",
        "same_state",
        "wait_without_wait_point",
        "changes_status_itself",
        "returns_failed_instead_of_raising",
    ],
)
def test_handler_that_breaks_the_contract_fails_the_case(
    seeded: Session,
    make_case: CaseFactory,
    monkeypatch: pytest.MonkeyPatch,
    handler: orchestrator.Handler,
    error_type: str,
) -> None:
    case = make_case()
    _use_handler(monkeypatch, CaseStatus.OPEN, handler)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.FAILED
    assert _audit(seeded, case)[-1].payload["error_type"] == error_type


def test_wait_point_without_the_wait_flag_fails_the_case(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(CaseStatus.OUTREACH)
    _use_handler(
        monkeypatch, CaseStatus.OUTREACH, _returns(next_status=CaseStatus.WAITING_RESPONSE)
    )

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.FAILED
    assert _audit(seeded, case)[-1].payload["error_type"] == "WorkflowError"


def test_missing_handler_fails_the_case(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case()
    monkeypatch.delitem(orchestrator.HANDLERS, CaseStatus.ASSESSING)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.FAILED
    assert _audit(seeded, case)[-1].payload["failed_at"] == "ASSESSING"


def test_failure_payload_never_carries_the_error_text(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case()

    def leaking_handler(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("password_hash=secret patient=John")

    _use_handler(monkeypatch, CaseStatus.OPEN, leaking_handler)

    orchestrator.advance(seeded, case.id)

    assert "secret" not in str(_audit(seeded, case)[-1].payload)


# --------------------------------------------------------------------------- #
# Production session settings (autoflush off)
# --------------------------------------------------------------------------- #
def test_golden_path_with_production_session_settings(production_seeded: Session) -> None:
    db = production_seeded
    assert db.autoflush is False
    case = _make_case(db, CaseStatus.OPEN)

    orchestrator.advance(db, case.id)
    orchestrator.resume(db, case.id, CaseStatus.SAFETY_VALIDATION)
    orchestrator.resume(db, case.id, CaseStatus.EXECUTING)

    assert _status(db, case) is CaseStatus.RESOLVED
    assert len(_status_changes(db, case)) == 8


def test_failure_with_production_session_settings(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = production_seeded
    case = _make_case(db, CaseStatus.OPEN)

    def failing_optimize(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("solver crashed")

    _use_handler(monkeypatch, CaseStatus.OPTIMIZING, failing_optimize)

    orchestrator.advance(db, case.id)

    assert _status(db, case) is CaseStatus.FAILED
    assert _status_changes(db, case) == [("OPEN", "FAILED")]


def test_callers_unflushed_change_survives_with_production_session_settings(
    production_seeded: Session,
) -> None:
    """advance() flushes before it re-reads the case, so a pending edit is not overwritten."""
    db = production_seeded
    case = _make_case(db, CaseStatus.OPEN)
    new_time = DEMO_NOW + timedelta(hours=5)
    case.required_replacement_time = new_time  # not flushed: autoflush is off

    orchestrator.advance(db, case.id)

    assert _status(db, case) is CaseStatus.WAITING_RESPONSE
    assert case.required_replacement_time == new_time


# --------------------------------------------------------------------------- #
# When the failure itself cannot be recorded
# --------------------------------------------------------------------------- #
def test_error_escapes_and_nothing_is_committed_when_failed_cannot_be_written(
    seeded: Session, make_case: CaseFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the orchestrator actor no audit row can be written, not even WORKFLOW_FAILED."""
    case = make_case()

    def failing_intake(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("boom")

    def no_orchestrator_actor(db: Session, name: ActorName) -> int:
        raise ActorNotFoundError(f"No actor named {name.value!r}")

    _use_handler(monkeypatch, CaseStatus.OPEN, failing_intake)
    monkeypatch.setattr(orchestrator.actor_service, "component_id", no_orchestrator_actor)

    with (
        mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit,
        pytest.raises(ActorNotFoundError),
    ):
        orchestrator.advance(seeded, case.id)

    assert commit.call_count == 0


# --------------------------------------------------------------------------- #
# Two real connections on the same case
# --------------------------------------------------------------------------- #
@pytest.fixture
def committed_waiting_case(frozen_clock: datetime) -> Iterator[int]:
    """A committed case at WAITING_RESPONSE, visible to separate connections.

    The other tests share one rolled-back connection, which cannot show a lock
    conflict. This one commits, so it empties every table again afterwards.
    """
    with SessionLocal.begin() as db:
        load(db)
        case_id = _make_case(db, CaseStatus.WAITING_RESPONSE).id
    try:
        yield case_id
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_two_requests_that_wrote_audit_rows_do_not_deadlock_on_resume(
    committed_waiting_case: int,
) -> None:
    """Regression: an audit insert holds KEY SHARE on the case through its foreign key.

    With FOR UPDATE both requests held that lock and then waited for each other,
    and one died with a deadlock instead of InvalidTransitionError.
    """
    case_id = committed_waiting_case
    both_hold_key_share = threading.Barrier(2, timeout=10)
    outcomes: list[str] = []

    def accept_offer() -> None:
        try:
            with SessionLocal() as db:
                audit_service.log(
                    db,
                    case_id=case_id,
                    actor_id=actor_service.user_id(db, ACCEPTING_STAFF_ID),
                    action=AuditAction.OFFER_ACCEPTED,
                    entity_type=EntityType.CANDIDATE_OUTREACH,
                    entity_id=None,
                    payload={"staff_id": ACCEPTING_STAFF_ID},
                )
                both_hold_key_share.wait()
                orchestrator.resume(db, case_id, CaseStatus.SAFETY_VALIDATION)
            outcomes.append("ok")
        except Exception as error:
            outcomes.append(type(error).__name__)

    threads = [threading.Thread(target=accept_offer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["InvalidTransitionError", "ok"]
    with SessionLocal() as db:
        case = db.get(StaffingCase, case_id)
        assert case is not None
        assert case.status is CaseStatus.WAITING_APPROVAL
        actions = [row.action for row in _audit(db, case)]
    # The rejected request rolled back, so its OFFER_ACCEPTED row is gone too
    assert actions.count(AuditAction.OFFER_ACCEPTED) == 1
    assert actions.count(AuditAction.CASE_STATUS_CHANGED) == 2
