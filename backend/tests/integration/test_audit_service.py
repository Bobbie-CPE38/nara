"""audit_service.log() against a real PostgreSQL: row contents, no commit, enum-only input."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Actor, AuditLog, Shift, StaffingCase, StaffingEvent
from app.domain.enums import (
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
)
from app.seed import load
from app.services import audit_service

DEMO_NOW = datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE)


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_time(DEMO_NOW)
    yield
    clock.reset()


@pytest.fixture
def seeded(db: Session) -> Session:
    load(db)
    return db


@pytest.fixture
def orchestrator_id(seeded: Session) -> int:
    actor_id = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.WORKFLOW_ORCHESTRATOR.value)
    )
    assert actor_id is not None
    return actor_id


@pytest.fixture
def case(seeded: Session) -> StaffingCase:
    shift = seeded.scalars(select(Shift).order_by(Shift.id)).first()
    assert shift is not None
    event = StaffingEvent(
        event_type=EventType.PATIENT_SURGE,
        shift_id=shift.id,
        occurred_at=DEMO_NOW,
        status=EventStatus.PROCESSED,
    )
    seeded.add(event)
    seeded.flush()
    row = StaffingCase(
        event_id=event.id,
        shift_id=shift.id,
        status=CaseStatus.OPEN,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    seeded.add(row)
    seeded.flush()
    return row


def _audit_rows(db: Session) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id)))


def test_log_writes_one_row(seeded: Session, orchestrator_id: int, case: StaffingCase) -> None:
    payload: dict[str, Any] = {"from": "OPEN", "to": "ASSESSING"}
    audit_service.log(
        seeded,
        case_id=case.id,
        actor_id=orchestrator_id,
        action=AuditAction.CASE_STATUS_CHANGED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload=payload,
    )
    seeded.expire_all()

    [row] = _audit_rows(seeded)
    assert row.case_id == case.id
    assert row.actor_id == orchestrator_id
    assert row.action is AuditAction.CASE_STATUS_CHANGED
    assert row.entity_type is EntityType.STAFFING_CASES
    assert row.entity_id == case.id
    assert row.payload == payload
    assert row.created_at == DEMO_NOW


def test_log_accepts_missing_case_and_entity(seeded: Session, orchestrator_id: int) -> None:
    # EVENT_IGNORED has no case; composite keys have no single entity_id
    audit_service.log(
        seeded,
        case_id=None,
        actor_id=orchestrator_id,
        action=AuditAction.EVENT_IGNORED,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=None,
        payload={},
    )

    [row] = _audit_rows(seeded)
    assert row.case_id is None
    assert row.entity_id is None


def test_log_never_commits(seeded: Session, orchestrator_id: int) -> None:
    with mock.patch.object(seeded, "commit", side_effect=AssertionError("log() committed")):
        audit_service.log(
            seeded,
            case_id=None,
            actor_id=orchestrator_id,
            action=AuditAction.EVENT_RECEIVED,
            entity_type=EntityType.STAFFING_EVENTS,
            entity_id=None,
            payload={},
        )
    assert len(_audit_rows(seeded)) == 1

    # Rolling back the caller's transaction discards the row with the rest of the work
    seeded.rollback()
    assert seeded.scalar(select(func.count()).select_from(AuditLog)) == 0


def _kwargs(actor_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        "case_id": None,
        "actor_id": actor_id,
        "action": AuditAction.CASE_OPENED,
        "entity_type": EntityType.STAFFING_CASES,
        "entity_id": None,
        "payload": {},
    } | overrides


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "CASE_OPENED"},
        {"entity_type": "STAFFING_CASES"},
        {"payload": None},
    ],
    ids=["action", "entity_type", "payload"],
)
def test_log_rejects_wrong_types(
    seeded: Session, orchestrator_id: int, overrides: dict[str, Any]
) -> None:
    with pytest.raises(TypeError):
        audit_service.log(seeded, **_kwargs(orchestrator_id, **overrides))
    assert _audit_rows(seeded) == []


def test_log_rejects_raw_datetime_in_payload(seeded: Session, orchestrator_id: int) -> None:
    # Callers must send .isoformat() so every audit timestamp has one format
    kwargs = _kwargs(orchestrator_id, payload={"start_at": DEMO_NOW})
    with pytest.raises((TypeError, StatementError)) as exc, seeded.begin_nested():
        audit_service.log(seeded, **kwargs)
    cause = exc.value.orig if isinstance(exc.value, StatementError) else exc.value
    assert isinstance(cause, TypeError)
    assert _audit_rows(seeded) == []


def test_log_rejects_password_hash_in_payload(seeded: Session, orchestrator_id: int) -> None:
    kwargs = _kwargs(orchestrator_id, payload={"staff_id": 1, "password_hash": "!"})
    with pytest.raises(ValueError, match="password_hash"):
        audit_service.log(seeded, **kwargs)
    assert _audit_rows(seeded) == []


def test_log_fails_at_call_site_for_unknown_actor(seeded: Session) -> None:
    with pytest.raises(IntegrityError):
        audit_service.log(
            seeded,
            case_id=None,
            actor_id=999_999,
            action=AuditAction.EVENT_RECEIVED,
            entity_type=EntityType.STAFFING_EVENTS,
            entity_id=None,
            payload={},
        )
