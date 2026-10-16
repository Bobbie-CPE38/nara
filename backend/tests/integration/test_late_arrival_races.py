"""Late check-in against concurrent work, on two connections (docs/workflow.md, 6.11 and 6.24).

Committed data and the real handlers: the Golden Case night shift (id 1) with staff
101-105, where 101 never came. What is under test is the lock order and the retry of
check_in(), so the sessions here are real SessionLocal sessions and not a test transaction.
"""

import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from app.db.base import Base
from app.db.models import (
    Attendance,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    RosterAssignment,
    StaffingCase,
    StaffUnavailability,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorName,
    AuditAction,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    Channel,
    CheckInSource,
    OutreachStatus,
    RosterStatus,
)
from app.main import app
from app.seed import load
from app.seed.scenarios import merge_gap
from app.services import (
    actor_service,
    attendance_service,
    merge_window_service,
    no_show_service,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.no_show_rows import DEADLINE, NIGHT_SHIFT, START, at, check_in_everyone

SECOND = timedelta(seconds=1)
WINDOW = timedelta(seconds=merge_gap.MERGE_WINDOW_SECONDS)


def wipe() -> None:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest.fixture
def waiting_no_show(frozen_clock: datetime) -> Iterator[None]:
    """101 is missing and the 10 minute window of the NO_SHOW event is still open."""
    with SessionLocal.begin() as db:
        load(db)
        merge_gap.seed(db)
        check_in_everyone(db, except_staff=(101,))
    at(DEADLINE + SECOND)
    with SessionLocal() as db:
        assert len(no_show_service.detect_due_no_shows(db)) == 1
    try:
        yield
    finally:
        wipe()


@pytest.fixture
def case_without_101(frozen_clock: datetime) -> Iterator[int]:
    """Stage 2 is done: 101's row is cancelled and a real case waits with its offers."""
    with SessionLocal.begin() as db:
        load(db)
        check_in_everyone(db, except_staff=(101,))
    at(DEADLINE + SECOND)
    with SessionLocal() as db:
        assert len(no_show_service.detect_due_no_shows(db)) == 1
    with SessionLocal() as db:
        case = db.scalars(select(StaffingCase)).one()
        assert case.status == CaseStatus.WAITING_RESPONSE
        case_id = case.id
    try:
        yield case_id
    finally:
        wipe()


def run_together(*jobs: Callable[[], Any]) -> list[Exception]:
    """Start every job at the same moment on its own thread and collect what they raise."""
    barrier = threading.Barrier(len(jobs), timeout=10)
    errors: list[Exception] = []

    def run(job: Callable[[], Any]) -> None:
        try:
            barrier.wait()
            job()
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    return errors


def check_in_101() -> attendance_service.CheckInResult:
    with SessionLocal() as db:
        return attendance_service.check_in(
            db,
            staff_id=101,
            shift_id=NIGHT_SHIFT,
            source=CheckInSource.SIMULATED,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        )


def close_windows() -> None:
    with SessionLocal() as db:
        merge_window_service.close_due_windows(db)


# ---- the check-in against the job --------------------------------------------------------------


def test_a_check_in_racing_the_window_close_leaves_one_consistent_outcome(
    waiting_no_show: None,
) -> None:
    at(DEADLINE + SECOND + WINDOW)
    errors = run_together(check_in_101, close_windows)
    assert errors == []

    with SessionLocal() as db:
        attendance = db.scalars(select(Attendance).where(Attendance.staff_id == 101)).one()
        arrival = attendance.check_in_at
        original, restored = db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.staff_id == 101)
            .order_by(RosterAssignment.id)
        ).all()
        assert (original.status, restored.status) == (RosterStatus.CANCELLED, RosterStatus.ASSIGNED)
        assert restored.actual_start_at == arrival
        absence = db.scalars(select(StaffUnavailability)).one()
        assert (absence.reason, absence.end_at) == (AvailabilityReason.NO_SHOW, arrival)
        created = db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.UNAVAILABILITY_CREATED)
        )
        assert created == 1
        # The close came first (a case opened and the arrival is credited to it), or the
        # check-in did and the person was back before the case could open: never both, never neither
        cases = db.scalar(select(func.count()).select_from(StaffingCase))
        credited = db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.UNAVAILABILITY_UPDATED)
        )
        assert (cases, credited) in {(0, 0), (1, 1)}


def test_a_check_in_after_the_window_closed_is_credited_to_the_case_it_opened(
    waiting_no_show: None,
) -> None:
    at(DEADLINE + SECOND + WINDOW)
    close_windows()
    check_in_101()

    with SessionLocal() as db:
        case = db.scalars(select(StaffingCase)).one()
        credited = db.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.UNAVAILABILITY_UPDATED)
        ).one()
        assert credited.case_id == case.id
        assert case.status in {CaseStatus.RESOLVED, CaseStatus.WAITING_RESPONSE}


# ---- the check-in against a new offer ----------------------------------------------------------


def add_offer_from_another_connection() -> None:
    """What a wave of the case does between two lock steps of the check-in."""
    with SessionLocal.begin() as db:
        case = db.scalars(select(StaffingCase)).one()
        plan_id = db.scalars(
            select(CandidatePlan.id)
            .where(CandidatePlan.case_id == case.id)
            .order_by(CandidatePlan.id.desc())
        ).first()
        assert plan_id is not None
        item = CandidateItem(
            plan_id=plan_id,
            staff_id=105,
            rank=99,
            source=CandidateSource.SAME_WARD,
            proposed_shift_id=NIGHT_SHIFT,
        )
        db.add(item)
        db.flush()
        db.add(
            CandidateOutreach(
                case_id=case.id,
                candidate_item_id=item.id,
                channel=Channel.LINE,
                status=OutreachStatus.SENT,
                sent_at=DEMO_NOW,
                expires_at=START + timedelta(hours=2),
            )
        )


def offers_added_after_locking(times: int) -> Callable[..., set[int]]:
    """A stand-in for the offer lock step: lock, then let `times` new offers appear."""
    real = attendance_service._lock_unfinished_offers
    calls = {"count": 0}

    def locked_then_changed(db: Any, case_id: int) -> set[int]:
        offer_ids = real(db, case_id)
        calls["count"] += 1
        if calls["count"] <= times:
            add_offer_from_another_connection()
        return offer_ids

    locked_then_changed.calls = calls  # type: ignore[attr-defined]
    return locked_then_changed


def test_a_new_offer_between_the_lock_steps_makes_the_check_in_start_again_and_succeed(
    case_without_101: int,
) -> None:
    at(DEADLINE + timedelta(minutes=5))
    hook = offers_added_after_locking(times=1)
    with mock.patch.object(attendance_service, "_lock_unfinished_offers", hook):
        result = check_in_101()

    assert result.on_time is False
    assert hook.calls["count"] == 2  # type: ignore[attr-defined]
    with SessionLocal() as db:
        restored = db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.staff_id == 101, RosterAssignment.status == RosterStatus.ASSIGNED
            )
        ).one()
        assert restored.actual_start_at == result.check_in_at
        attended = db.scalar(
            select(func.count()).select_from(Attendance).where(Attendance.shift_id == NIGHT_SHIFT)
        )
        assert attended == 5
        # The offer that appeared meanwhile was seen by the second try and trimmed with the rest
        added = db.scalars(
            select(CandidateOutreach)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(CandidateItem.rank == 99)
        ).one()
        assert added.status == OutreachStatus.CANCELLED


def test_an_offer_inserted_right_after_the_offer_lock_query_makes_the_check_in_start_again(
    case_without_101: int,
) -> None:
    """The gap the helper itself has: between its lock query and anything after it."""
    at(DEADLINE + timedelta(minutes=5))
    lock_queries = {"count": 0}

    def after_execute(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        if "FROM candidate_outreach" in statement and "FOR NO KEY UPDATE" in statement:
            lock_queries["count"] += 1
            if lock_queries["count"] == 1:
                add_offer_from_another_connection()

    event.listen(engine, "after_cursor_execute", after_execute)
    try:
        result = check_in_101()
    finally:
        event.remove(engine, "after_cursor_execute", after_execute)

    # The first try saw an offer it had not locked and started again
    assert result.on_time is False
    assert lock_queries["count"] == 2
    with SessionLocal() as db:
        added = db.scalars(
            select(CandidateOutreach)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(CandidateItem.rank == 99)
        ).one()
        assert added.status == OutreachStatus.CANCELLED


def test_a_check_in_that_never_gets_a_stable_offer_set_fails_after_five_tries_and_writes_nothing(
    case_without_101: int,
) -> None:
    at(DEADLINE + timedelta(minutes=5))
    hook = offers_added_after_locking(times=100)
    with (
        mock.patch.object(attendance_service, "_lock_unfinished_offers", hook),
        pytest.raises(attendance_service.CheckInLockRetryError),
    ):
        check_in_101()

    assert hook.calls["count"] == attendance_service.CHECK_IN_LOCK_TRIES  # type: ignore[attr-defined]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Attendance).where(Attendance.staff_id == 101)
            )
            == 0
        )
        statuses = db.scalars(
            select(RosterAssignment.status).where(RosterAssignment.staff_id == 101)
        ).all()
        assert list(statuses) == [RosterStatus.CANCELLED]
        assert db.scalars(select(StaffUnavailability)).one().end_at is not None


def test_the_demo_route_answers_409_when_the_lock_retry_runs_out(case_without_101: int) -> None:
    at(DEADLINE + timedelta(minutes=5))
    hook = offers_added_after_locking(times=100)
    with (
        mock.patch.object(attendance_service, "_lock_unfinished_offers", hook),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(
            "/demo/attendance/check-in", json={"staff_id": 101, "shift_id": NIGHT_SHIFT}
        )

    assert response.status_code == 409
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Attendance).where(Attendance.staff_id == 101)
            )
            == 0
        )


def test_my_route_answers_409_when_the_lock_retry_runs_out(case_without_101: int) -> None:
    at(DEADLINE + timedelta(minutes=5))
    hook = offers_added_after_locking(times=100)
    with (
        mock.patch.object(attendance_service, "_lock_unfinished_offers", hook),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(
            "/me/attendance/check-in",
            headers={"X-Demo-User": "101"},
            json={"shift_id": NIGHT_SHIFT},
        )

    assert response.status_code == 409
