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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import exists, select, text, update
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.db.models import (
    AuditLog,
    CandidatePlan,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    Ward,
)
from app.db.session import SessionLocal
from app.domain.enums import (
    ActorName,
    AuditAction,
    CheckInSource,
    EntityType,
    EventType,
)
from app.seed.large_demo import WARD_BASE
from app.seed.reset import reset_demo
from app.seed.scenarios import cross_ward
from app.services import (
    actor_service,
    attendance_service,
    audit_service,
    event_service,
    job_service,
    simulated_replies_service,
)
from app.services.test_run_kpi import KPI_COLUMNS, Advance, Row, compute

TESTER_CODE = re.compile(r"[A-Za-z0-9_-]{1,16}")
# The Golden Case leave that opens the case of most scenarios (docs/workflow.md 10)
LEAVING_NURSE = 105
NIGHT_SHIFT = 1
SIMULATED_SOURCE = CheckInSource.SIMULATED.value
ABORTED = "ABORTED"
CLOCK_LOST = "CLOCK_LOST"
# The clock or the first job round failed after the run was written (6.35.2)
START_FAILED = "START_FAILED"
# Finished before the run had a case: in no_show, before the system found the NO_SHOW
NO_CASE = "NO_CASE"
# A test run's clock moves one job round at a time (the job's default interval), and in
# all at most two hours, when the run's shift starts (6.35.1)
SCENARIO_STEP_SECONDS = 30
SCENARIO_MAX_ADVANCE_SECONDS = 2 * 60 * 60
REASON_MAX_LENGTH = 100

_lock = threading.Lock()


class Scenario(StrEnum):
    GOLDEN = "golden"
    CROSS_WARD = "cross_ward"
    # Round 6 PR EV7 (docs/workflow.md 6.37.10)
    SURGE = "surge"
    NO_SHOW = "no_show"
    HANDOFF = "handoff"
    SUPERVISOR = "supervisor"


# A surge on the ICU night shift: 10 patients become 14, so at 2 per nurse it needs 7, two
# more than its 5 (6.37.10)
SURGE_PATIENTS = 14
SURGE_REPORTER = 900
# no_show: 104 never checks in. The run starts a minute before the grace period of the
# night shift ends, so the system finds the NO_SHOW and opens the case by itself
NO_SHOW_NURSE = 104
NO_SHOW_START = timedelta(hours=2, minutes=14)


class TestRunOpenError(RuntimeError):
    """Another run is open: finish or abort it first (409)."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"Test run {run_id} is in progress: finish or abort it first")
        self.run_id = run_id


class TestRunNotFoundError(LookupError):
    """No run with this id (404)."""


class TestRunClosedError(RuntimeError):
    """The run is already finished or aborted (409)."""


class AdvanceLimitError(ValueError):
    """The move would take a test run's clock past SCENARIO_MAX_ADVANCE_SECONDS in all (422)."""


class PartialAdvanceError(RuntimeError):
    """The clock left its mode after some steps were already moved and committed (409)."""


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
    # Open runs: seconds since the start on the scenario clock, if this API still has it.
    # System time: it includes advanced_seconds, so it is not the tester's time (the KPI
    # subtracts the advances, 6.35.4)
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


def _load_scenario(scenario: Scenario) -> Callable[[Session], None]:
    """The rows a run adds after the demo seed (6.35.3).

    The large demo profile stays (its people keep their accounts), but its wards are
    paused for the run: the pool takes free people only from active wards, so the
    scripted people are the only candidates and every cross-ward one needs both wards.
    The next plain reset loads the profile active again.
    """

    def load(db: Session) -> None:
        db.execute(update(Ward).where(Ward.id > WARD_BASE).values(is_active=False))
        if scenario is Scenario.CROSS_WARD:
            cross_ward.seed(db)
        if scenario is Scenario.NO_SHOW:
            _everyone_but_one_checks_in(db)

    return load


def _everyone_but_one_checks_in(db: Session) -> None:
    """no_show: every nurse of the night shift arrives on time but NO_SHOW_NURSE."""
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None, "the Golden Case seeds the night shift"
    rows = db.scalars(
        select(RosterAssignment)
        .where(RosterAssignment.shift_id == NIGHT_SHIFT, RosterAssignment.staff_id != NO_SHOW_NURSE)
        .order_by(RosterAssignment.id)
    ).all()
    actor_id = _system_actor(db)
    for roster in rows:
        attendance_service.record(
            db,
            roster=roster,
            shift=shift,
            check_in_at=attendance_service.required_arrival_at(roster, shift),
            source=CheckInSource.SIMULATED,
            actor_id=actor_id,
        )


def _open_the_case(db: Session, scenario: Scenario) -> int | None:
    """The event that starts the run, or None when the system finds it (no_show)."""
    if scenario is Scenario.NO_SHOW:
        return None
    if scenario is Scenario.SURGE:
        reporter = db.get(Staff, SURGE_REPORTER)
        assert reporter is not None, "the Golden Case seeds the ICU head nurse"
        return event_service.receive_event(
            db,
            staff_id=reporter.id,
            actor_id=_system_actor(db),
            role_id=reporter.role_id,
            event_type=EventType.PATIENT_SURGE,
            shift_id=NIGHT_SHIFT,
            patient_count=SURGE_PATIENTS,
            source=SIMULATED_SOURCE,
        ).event_id
    reporter = db.get(Staff, LEAVING_NURSE)
    assert reporter is not None, "the Golden Case seeds the leaving nurse"
    return event_service.receive_event(
        db,
        staff_id=reporter.id,
        actor_id=_system_actor(db),
        role_id=reporter.role_id,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        source=SIMULATED_SOURCE,
    ).event_id


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
        demo_time = reset_demo(_load_scenario(scenario))
        if scenario is Scenario.NO_SHOW:
            demo_time += NO_SHOW_START
            clock.set_time(demo_time)
        real_start = datetime.now(clock.APP_TIMEZONE)
        with SessionLocal() as db:
            event_id = _open_the_case(db, scenario)
            audit_service.log(
                db,
                case_id=None,
                event_id=event_id,
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
                    "event_id": event_id,
                    # A run without a starting event finds its case through the NO_SHOW of
                    # this nurse on this shift (simulated_replies_service.run_case_id)
                    "shift_id": NIGHT_SHIFT,
                    "no_show_staff_id": NO_SHOW_NURSE if event_id is None else None,
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
            try:
                clock.run_from(demo_time, run_id)
                # The Golden Case's window closes at once: open the case now, not at the
                # next tick
                job_service.run_due_work(db)
            except Exception:
                # Never leave an open run its starter has no id for
                db.rollback()
                clock.freeze_now()
                _close(db, started, {"invalid": True, "reason": START_FAILED}, staff_id)
                raise
            case_id = simulated_replies_service.run_case_id(db, started.payload)
    return StartResult(test_run_id=run_id, scenario=scenario, started_at=demo_time, case_id=case_id)


def advance_clock(db: Session, seconds: int) -> tuple[datetime, list[job_service.DueWork]]:
    """Move the demo clock and run the work that fell due, for POST /demo/clock/advance.

    A frozen clock moves in one jump. A test run's clock moves one job round at a time,
    with the due work after each step, as the job would while the time passed: one jump
    of 10 minutes would time the offers out before the scripted answers of 45 and 120
    seconds fall due. The whole move holds the run lock, so Finish, Abort and the other
    clock buttons wait until it ends instead of landing between two steps.

    RuntimeError when the clock follows real time; AdvanceLimitError past two hours of
    advances in a run; PartialAdvanceError if the clock leaves its mode mid-move.
    """
    with _lock:
        scenario = clock.mode() == clock.ClockMode.SCENARIO
        if scenario and clock.advanced_seconds() + seconds > SCENARIO_MAX_ADVANCE_SECONDS:
            raise AdvanceLimitError(
                f"A test run's clock is advanced at most {SCENARIO_MAX_ADVANCE_SECONDS} seconds"
                f" in all; {clock.advanced_seconds():.0f} are used"
            )
        step = SCENARIO_STEP_SECONDS if scenario else seconds
        works: list[job_service.DueWork] = []
        moved = 0
        now = clock.now()
        while moved < seconds:
            delta = min(step, seconds - moved)
            try:
                now = _advance_unlocked(db, timedelta(seconds=delta))
            except RuntimeError as error:
                if moved:
                    raise PartialAdvanceError(
                        f"The clock moved {moved} of {seconds} seconds, then left its mode: {error}"
                    ) from error
                raise
            moved += delta
            works.append(job_service.run_due_work(db))
        return now, works


def _advance_unlocked(db: Session, delta: timedelta) -> datetime:
    """Move the demo clock in one jump; during a run, record the move for the KPI (6.35.1).
    Commits. The caller holds the run lock. RuntimeError when the clock follows real time,
    like clock.advance()."""
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
    case_id = simulated_replies_service.run_case_id(db, started.payload)
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
        elif _run_case(db, started) is None:
            # No case, no KPI to read: say so instead of a row of empty times
            clock.freeze_now()
            payload = {"invalid": True, "reason": NO_CASE}
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


# A spreadsheet runs a cell that starts with one of these as a formula (CSV injection)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value: Any) -> Any:
    """Text that a spreadsheet would read as a formula gets a leading quote."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def csv_rows(db: Session) -> list[dict[str, Any]]:
    """One row per closed run, in the CSV_COLUMNS order (6.35.2). Text cells are escaped
    with csv_cell(): the abort reason is free text."""
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
        rows.append({name: csv_cell(value) for name, value in row.items()})
    return rows
