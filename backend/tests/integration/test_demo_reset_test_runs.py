"""A demo reset keeps the results of test runs (round 6 PR EV5a, docs/workflow.md 6.35.2).

Each test run starts with a reset, so without this every run would erase the one
before. These tests commit, like test_demo_reset.
"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Actor, AuditLog, StaffingEvent
from app.db.session import SessionLocal
from app.domain.enums import ActorName, ActorType, AuditAction, EntityType
from app.seed import reset as reset_module
from app.seed.reset import IdentityConflictError, reset_demo
from app.services import actor_service, audit_service
from tests.integration.case_rows import make_case

pytestmark = pytest.mark.usefixtures("restore_empty_database")


def _run_rows(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == EntityType.TEST_RUN)
            .order_by(AuditLog.id)
        )
    )


def _actor_name(db: Session, row: AuditLog) -> str:
    actor = db.get(Actor, row.actor_id)
    assert actor is not None
    return actor.name


def _write_run(db: Session, *, actor_id: int | None = None) -> dict[str, Any]:
    """A finished run whose rows point at a case and an event, like a real one."""
    case = make_case(db)
    event_id = db.scalar(select(StaffingEvent.id).where(StaffingEvent.case_id == case.id))
    system = actor_service.component_id(db, ActorName.SYSTEM)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id or system,
        action=AuditAction.TEST_RUN_STARTED,
        entity_type=EntityType.TEST_RUN,
        entity_id=None,
        payload={"tester_code": "T01"},
    )
    started = _run_rows(db)[-1]
    started.entity_id = started.id
    audit_service.log(
        db,
        case_id=None,
        event_id=event_id,
        actor_id=actor_service.user_id(db, 900),
        action=AuditAction.TEST_RUN_FINISHED,
        entity_type=EntityType.TEST_RUN,
        entity_id=started.id,
        payload={"time_to_fill_s": 300},
    )
    db.commit()
    return {"run_id": started.id, "case_id": case.id, "event_id": event_id}


def test_a_reset_keeps_the_rows_with_their_ids_and_actors() -> None:
    reset_demo()
    with SessionLocal() as db:
        run = _write_run(db)
        before = [(row.id, row.action, _actor_name(db, row)) for row in _run_rows(db)]

    reset_demo()

    with SessionLocal() as db:
        rows = _run_rows(db)
        assert [(row.id, row.action, _actor_name(db, row)) for row in rows] == before
        assert all(row.case_id is None and row.event_id is None for row in rows)
        assert all(row.entity_id == run["run_id"] for row in rows)
        started, finished = rows
        assert started.payload == {"tester_code": "T01", "original_case_id": run["case_id"]}
        assert finished.payload == {"time_to_fill_s": 300, "original_event_id": run["event_id"]}


def test_a_second_reset_keeps_the_original_ids_and_new_rows_follow() -> None:
    reset_demo()
    with SessionLocal() as db:
        run = _write_run(db)

    reset_demo()
    reset_demo()

    with SessionLocal() as db:
        kept = _run_rows(db)
        assert kept[0].payload["original_case_id"] == run["case_id"]
        # A new run after the resets gets a higher id than every kept row
        newer = _write_run(db)
        assert newer["run_id"] > max(row.id for row in kept)


def test_a_failed_reset_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_demo()
    with SessionLocal() as db:
        run = _write_run(db)

    def broken(db: Session, **kwargs: object) -> None:
        raise RuntimeError("seed failed")

    monkeypatch.setattr(reset_module, "load", broken)
    with pytest.raises(RuntimeError, match="seed failed"):
        reset_demo()

    with SessionLocal() as db:
        started = _run_rows(db)[0]
        assert started.case_id == run["case_id"]
        assert "original_case_id" not in started.payload


def test_a_row_whose_actor_is_gone_fails_the_whole_reset() -> None:
    reset_demo()
    with SessionLocal() as db:
        ghost = Actor(name="ghost_component", actor_type=ActorType.COMPONENT)
        db.add(ghost)
        db.flush()
        run = _write_run(db, actor_id=ghost.id)

    with pytest.raises(IdentityConflictError):
        reset_demo()

    with SessionLocal() as db:
        assert _run_rows(db)[0].case_id == run["case_id"]
