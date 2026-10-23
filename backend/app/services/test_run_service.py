"""Test runs: time a person who plays the head nurse (round 6 PR EV5a, docs/workflow.md 6.35).

A run is a TEST_RUN_STARTED audit row (its id is the run's id) and, once closed, one
TEST_RUN_FINISHED row with the same entity_id. A run is open while it has no finished
row; that is read from the database, so it survives an API restart. Each clock advance
during a run is a TEST_RUN_CLOCK_ADVANCED row, so the KPI can take it out.

While a run is open, nothing may spoil it: a demo reset, freezing or unfreezing the
clock and starting another run are refused (409) instead of being found out later.
The only thing that cannot be refused is an API restart, which loses the scenario
clock: finishing such a run closes it as CLOCK_LOST without KPI.

The clock and this lock live in one API process (6.35.1): one worker only.
"""

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import exists, select, text
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.db.models import AuditLog, CandidatePlan, Shift, Staff, StaffingCase, StaffingEvent
from app.db.session import SessionLocal
from app.domain.enums import (
    ActorName,
    AuditAction,
    CheckInSource,
    EntityType,
    EventType,
)
from app.seed.reset import reset_demo
from app.seed.scenarios import cross_ward
from app.services import actor_service, audit_service, event_service, job_service
from app.services.test_run_kpi import KPI_COLUMNS, Advance, Row, compute

TESTER_CODE = re.compile(r"[A-Za-z0-9_-]{1,16}")
# The Golden Case leave that opens the case of every scenario (docs/workflow.md 10)
LEAVING_NURSE = 105
NIGHT_SHIFT = 1
SIMULATED_SOURCE = CheckInSource.SIMULATED.value
ABORTED = "ABORTED"
CLOCK_LOST = "CLOCK_LOST"
REASON_MAX_LENGTH = 100

_lock = threading.Lock()


class Scenario(StrEnum):
    GOLDEN = "golden"
    CROSS_WARD = "cross_ward"


class TestRunOpenError(RuntimeError):
    """Another run is open: finish or abort it first (409)."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"Test run {run_id} is in progress: finish or abort it first")
        self.run_id = run_id


class TestRunNotFoundError(LookupError):
    """No run with this id (404)."""


class TestRunClosedError(RuntimeError):
    """The run is already finished or aborted (409)."""


@dataclass(frozen=True)
class StartResult:
    test_run_id: int
    scenario: Scenario
    started_at: datetime
    case_id: int | None


@dataclass(frozen=True)
class RunView:
    test_run_id: int
    tester_code: str
    scenario: str
    auto_nurses: bool
    started_at: datetime
    started_real_at: str | None
    open: bool
    # Open runs: seconds since the start on the scenario clock, if this API still has it
    elapsed_seconds: float | None
    invalid: bool | None
    reason: str | None
    advanced_seconds: float
    kpi: dict[str, Any] | None


def _finished_exists(run_id: Any) -> Any:
    finished = aliased(AuditLog)
    return exists().where(
        finished.action == AuditAction.TEST_RUN_FINISHED,
        finished.entity_type == EntityType.TEST_RUN,
        finished.entity_id == run_id,
    )


def open_run_id(db: Session) -> int | None:
    """The open run, or None. None as well before the first migration (no audit table)."""
    if db.scalar(text("SELECT to_regclass('public.audit_log')")) is None:
        return None
    return db.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.action == AuditAction.TEST_RUN_STARTED,
            AuditLog.entity_type == EntityType.TEST_RUN,
            ~_finished_exists(AuditLog.id),
        )
        .order_by(AuditLog.id.desc())
        .limit(1)
    )


@contextmanager
def no_open_run() -> Iterator[None]:
    """Hold the run lock and refuse while a run is open: around a demo reset and the
    clock buttons (6.35.2)."""
    with _lock:
        with SessionLocal() as db:
            run_id = open_run_id(db)
        if run_id is not None:
            raise TestRunOpenError(run_id)
        yield


def _system_actor(db: Session) -> int:
    return actor_service.component_id(db, ActorName.SYSTEM)


def _starter_actor(db: Session, staff_id: int | None) -> int:
    """The signed-in user who started or closed the run; SYSTEM in demo mode."""
    return _system_actor(db) if staff_id is None else actor_service.user_id(db, staff_id)


def start(
    *,
    tester_code: str,
    scenario: Scenario,
    auto_nurses: bool,
    staff_id: int | None,
) -> StartResult:
    """Reset, load the scenario, report the leave, start the scenario clock and open the case."""
    if not TESTER_CODE.fullmatch(tester_code):
        raise ValueError("tester_code must be 1-16 letters, digits, '_' or '-'")
    with _lock:
        with SessionLocal() as db:
            run_id = open_run_id(db)
        if run_id is not None:
            raise TestRunOpenError(run_id)
        demo_time = reset_demo(cross_ward.seed if scenario is Scenario.CROSS_WARD else None)
        real_start = datetime.now(clock.APP_TIMEZONE)
        with SessionLocal() as db:
            reporter = db.get(Staff, LEAVING_NURSE)
            assert reporter is not None, "the Golden Case seeds the leaving nurse"
            outcome = event_service.receive_event(
                db,
                staff_id=reporter.id,
                actor_id=_system_actor(db),
                role_id=reporter.role_id,
                event_type=EventType.STAFF_UNAVAILABLE,
                shift_id=NIGHT_SHIFT,
                source=SIMULATED_SOURCE,
            )
            audit_service.log(
                db,
                case_id=None,
                event_id=outcome.event_id,
                actor_id=_starter_actor(db, staff_id),
                action=AuditAction.TEST_RUN_STARTED,
                entity_type=EntityType.TEST_RUN,
                entity_id=None,
                payload={
                    "tester_code": tester_code,
                    "scenario": scenario.value,
                    "auto_nurses": auto_nurses,
                    "scenario_start": demo_time.isoformat(),
                    "started_real_at": real_start.isoformat(),
                    "event_id": outcome.event_id,
                },
            )
            started = db.scalars(
                select(AuditLog)
                .where(AuditLog.action == AuditAction.TEST_RUN_STARTED)
                .order_by(AuditLog.id.desc())
                .limit(1)
            ).one()
            started.entity_id = started.id
            run_id = started.id
            db.commit()
            clock.run_from(demo_time, run_id)
            # The Golden Case's window closes at once: open the case now, not at the next tick
            job_service.run_due_work(db)
            case_id = db.scalar(
                select(StaffingEvent.case_id).where(StaffingEvent.id == outcome.event_id)
            )
    return StartResult(test_run_id=run_id, scenario=scenario, started_at=demo_time, case_id=case_id)


def advance(db: Session, delta: timedelta) -> datetime:
    """Move the demo clock; during a run, record the move for the KPI (6.35.1). Commits.

    RuntimeError when the clock follows real time, like clock.advance().
    """
    with _lock:
        before = clock.now()
        after = clock.advance(delta)
        run_id = clock.test_run_id()
        if run_id is not None:
            audit_service.log(
                db,
                case_id=None,
                actor_id=_system_actor(db),
                action=AuditAction.TEST_RUN_CLOCK_ADVANCED,
                entity_type=EntityType.TEST_RUN,
                entity_id=run_id,
                payload={
                    "seconds": delta.total_seconds(),
                    "before": before.isoformat(),
                    "after": after.isoformat(),
                },
            )
            db.commit()
        return after


def _started_row(db: Session, run_id: int) -> AuditLog:
    row = db.scalars(
        select(AuditLog).where(
            AuditLog.id == run_id,
            AuditLog.action == AuditAction.TEST_RUN_STARTED,
            AuditLog.entity_type == EntityType.TEST_RUN,
        )
    ).one_or_none()
    if row is None:
        raise TestRunNotFoundError(f"No test run {run_id}")
    if db.scalar(select(_finished_exists(run_id))):
        raise TestRunClosedError(f"Test run {run_id} is already closed")
    return row


def _run_case(db: Session, started: AuditLog) -> StaffingCase | None:
    event_id = started.payload.get("event_id")
    case_id = db.scalar(select(StaffingEvent.case_id).where(StaffingEvent.id == event_id))
    return None if case_id is None else db.get(StaffingCase, case_id)


def _advances(db: Session, run_id: int) -> list[Advance]:
    rows = db.scalars(
        select(AuditLog).where(
            AuditLog.action == AuditAction.TEST_RUN_CLOCK_ADVANCED,
            AuditLog.entity_id == run_id,
        )
    )
    return [
        Advance(
            before=datetime.fromisoformat(row.payload["before"]),
            after=datetime.fromisoformat(row.payload["after"]),
            seconds=float(row.payload["seconds"]),
        )
        for row in rows
    ]


def kpi_of(db: Session, started: AuditLog) -> dict[str, Any]:
    """Read the KPI of an open run from the audit log of its case (6.35.4)."""
    case = _run_case(db, started)
    if case is None:
        return compute(
            [],
            [],
            required_replacement_time=None,
            skipped_by_plan=0,
            filled_from_other_ward=None,
        )
    event_ids = select(StaffingEvent.id).where(StaffingEvent.case_id == case.id)
    audit_rows = list(
        db.scalars(
            select(AuditLog)
            .where((AuditLog.case_id == case.id) | AuditLog.event_id.in_(event_ids))
            .order_by(AuditLog.created_at, AuditLog.id)
        )
    )
    rows = [Row(action=row.action, at=row.created_at, payload=row.payload) for row in audit_rows]
    first_plan = next((row for row in rows if row.action == AuditAction.SOLVER_EXECUTED), None)
    skipped = 0
    if first_plan is not None:
        plan = db.get(CandidatePlan, first_plan.payload["plan_id"])
        skipped = len((plan.input_snapshot or {}).get("skipped", [])) if plan else 0
    fill = next(
        (
            row
            for row in rows
            if row.action
            in (
                AuditAction.ASSIGNMENT_CREATED,
                AuditAction.ASSIGNMENT_TRANSFERRED,
                AuditAction.MANUAL_ASSIGNMENT_CREATED,
            )
        ),
        None,
    )
    other_ward: bool | None = None
    if fill is not None and "staff_id" in fill.payload:
        home_ward = db.scalar(
            select(Staff.home_ward_id).where(Staff.id == fill.payload["staff_id"])
        )
        shift_ward = db.scalar(select(Shift.ward_id).where(Shift.id == case.shift_id))
        other_ward = home_ward != shift_ward
    return compute(
        rows,
        _advances(db, started.id),
        required_replacement_time=case.required_replacement_time,
        skipped_by_plan=skipped,
        filled_from_other_ward=other_ward,
    )


def _close(db: Session, started: AuditLog, payload: dict[str, Any], staff_id: int | None) -> None:
    case = _run_case(db, started)
    audit_service.log(
        db,
        case_id=None if case is None else case.id,
        actor_id=_starter_actor(db, staff_id),
        action=AuditAction.TEST_RUN_FINISHED,
        entity_type=EntityType.TEST_RUN,
        entity_id=started.id,
        payload=payload,
    )
    db.commit()


def finish(db: Session, run_id: int, *, staff_id: int | None) -> dict[str, Any]:
    """Freeze the clock and store the KPI; CLOCK_LOST without KPI after an API restart."""
    with _lock:
        started = _started_row(db, run_id)
        if clock.test_run_id() != run_id:
            payload: dict[str, Any] = {"invalid": True, "reason": CLOCK_LOST}
        else:
            clock.freeze_now()
            payload = {
                "invalid": False,
                "advanced_seconds": sum(move.seconds for move in _advances(db, run_id)),
                **kpi_of(db, started),
            }
        _close(db, started, payload, staff_id)
        return payload


def abort(db: Session, run_id: int, *, reason: str | None, staff_id: int | None) -> dict[str, Any]:
    """Close the run without KPI; freeze the clock if it is still this run's."""
    if reason is not None and len(reason) > REASON_MAX_LENGTH:
        raise ValueError(f"reason must be at most {REASON_MAX_LENGTH} characters")
    with _lock:
        started = _started_row(db, run_id)
        if clock.test_run_id() == run_id:
            clock.freeze_now()
        payload: dict[str, Any] = {"invalid": True, "reason": reason or ABORTED}
        _close(db, started, payload, staff_id)
        return payload


def list_runs(db: Session) -> list[RunView]:
    """Every run in start order, closed ones with their KPI or why they are invalid."""
    started_rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.action == AuditAction.TEST_RUN_STARTED,
            AuditLog.entity_type == EntityType.TEST_RUN,
        )
        .order_by(AuditLog.id)
    ).all()
    finished = {
        row.entity_id: row
        for row in db.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.TEST_RUN_FINISHED,
                AuditLog.entity_type == EntityType.TEST_RUN,
            )
        )
    }
    views = []
    for started in started_rows:
        closed = finished.get(started.id)
        payload = started.payload
        owned = closed is None and clock.test_run_id() == started.id
        result = closed.payload if closed is not None else {}
        views.append(
            RunView(
                test_run_id=started.id,
                tester_code=payload.get("tester_code", ""),
                scenario=payload.get("scenario", ""),
                auto_nurses=bool(payload.get("auto_nurses")),
                started_at=started.created_at.astimezone(clock.APP_TIMEZONE),
                started_real_at=payload.get("started_real_at"),
                open=closed is None,
                elapsed_seconds=(clock.now() - started.created_at).total_seconds()
                if owned
                else None,
                invalid=None if closed is None else bool(result.get("invalid")),
                reason=result.get("reason"),
                advanced_seconds=float(result.get("advanced_seconds", 0))
                if closed is not None
                else (clock.advanced_seconds() if owned else 0.0),
                kpi=None
                if closed is None or result.get("invalid")
                else {name: result.get(name) for name in KPI_COLUMNS},
            )
        )
    return views


CSV_COLUMNS = (
    "test_run_id",
    "tester_code",
    "scenario",
    "auto_nurses",
    "started_real_at",
    "advanced_seconds",
    "invalid",
    "reason",
    *KPI_COLUMNS,
)


def csv_rows(db: Session) -> list[dict[str, Any]]:
    """One row per closed run, in the CSV_COLUMNS order (6.35.2)."""
    rows = []
    for run in list_runs(db):
        if run.open:
            continue
        row: dict[str, Any] = {
            "test_run_id": run.test_run_id,
            "tester_code": run.tester_code,
            "scenario": run.scenario,
            "auto_nurses": run.auto_nurses,
            "started_real_at": run.started_real_at,
            "advanced_seconds": run.advanced_seconds,
            "invalid": run.invalid,
            "reason": run.reason,
        }
        row |= {name: (run.kpi or {}).get(name) for name in KPI_COLUMNS}
        rows.append(row)
    return rows
