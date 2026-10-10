"""POST /demo/reset rebuilds the Golden Case (docs/walking-skeleton.md step 2.3).

The reset commits to the test database, so every test here puts back the empty,
migrated schema that the other tests expect.
"""

import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from multiprocessing import get_context
from multiprocessing.queues import Queue
from queue import Empty
from threading import Barrier
from typing import Any, TypedDict, TypeVar, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, StaffSkill
from app.db.session import engine
from app.domain.enums import RosterStatus
from app.main import app

pytestmark = pytest.mark.usefixtures("restore_empty_database")

client = TestClient(app)

ICU_SKILL_ID = 1

T = TypeVar("T")


def roster(shift_id: int) -> dict[int, RosterStatus]:
    with Session(engine) as db:
        rows = db.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == shift_id))
        return {row.staff_id: row.status for row in rows}


def _child_main(outcome: "Queue[tuple[str, Any]]", target: Callable[[], Any]) -> None:
    try:
        outcome.put(("ok", target()))
    except BaseException:
        # Exceptions may not pickle, so the traceback travels as text
        outcome.put(("error", traceback.format_exc()))


def run_in_child_process(target: Callable[[], T], timeout: float = 60.0) -> T:
    """Run `target` in a separate process and return its result.

    A thread stuck in a reset cannot be stopped, so after a timeout it could start
    another reset while the cleanup fixture migrates the database. A process can be
    killed: on timeout the child is killed and joined before the test fails and the
    cleanup runs. `target` must be a module-level function so the child can import it.
    """
    # spawn, not fork: the parent holds open database connections and threads
    context = get_context("spawn")
    outcome: Queue[tuple[str, Any]] = context.Queue()
    child = context.Process(target=_child_main, args=(outcome, target), daemon=True)
    child.start()
    status, value = "timeout", None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, value = outcome.get(timeout=0.5)
            break
        except Empty:
            if not child.is_alive():
                # The result may have arrived just before the child exited
                try:
                    status, value = outcome.get(timeout=1)
                except Empty:
                    status, value = "crashed", f"exit code {child.exitcode}"
                break
    else:
        child.kill()
    child.join(timeout=10)
    if child.is_alive():
        child.kill()
        child.join()

    if status == "timeout":
        pytest.fail(f"Reset did not finish within {timeout:g}s; it may be deadlocked")
    if status != "ok":
        pytest.fail(f"Reset child process failed ({status}):\n{value}")
    return cast(T, value)


class SimultaneousResetOutcome(TypedDict):
    responses: list[tuple[int, dict[str, str]]]
    rosters: dict[int, dict[int, RosterStatus]]
    clock_frozen: bool
    clock_hour: int
    follow_up_status: int


def _simultaneous_resets() -> SimultaneousResetOutcome:
    """Runs in a child process: two resets at the same time, then one more."""
    start = Barrier(2)

    def request_reset(_: int) -> tuple[int, dict[str, str]]:
        # Separate clients simulate two browsers clicking Reset at the same time.
        with TestClient(app) as request_client:
            start.wait(timeout=5)
            response = request_client.post("/demo/reset")
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(request_reset, range(2)))
    rosters = {shift_id: roster(shift_id) for shift_id in (1, 2)}
    clock_frozen, clock_hour = clock.is_frozen(), clock.now().hour
    return {
        "responses": responses,
        "rosters": rosters,
        "clock_frozen": clock_frozen,
        "clock_hour": clock_hour,
        "follow_up_status": client.post("/demo/reset").status_code,
    }


def _failed_reset_then_reset() -> int:
    """Runs in a child process: a reset that raises, then a real one."""
    from app.seed import reset as reset_module

    def fail() -> datetime:
        raise RuntimeError("Reset failed")

    real_reset = reset_module._reset_demo
    reset_module._reset_demo = fail
    with pytest.raises(RuntimeError, match="Reset failed"):
        reset_module.reset_demo()
    reset_module._reset_demo = real_reset

    return client.post("/demo/reset").status_code


def test_reset_freezes_the_clock_at_today_21_00() -> None:
    today = datetime.now(clock.APP_TIMEZONE).date()

    response = client.post("/demo/reset")

    assert response.status_code == 200
    expected = datetime(today.year, today.month, today.day, 21, tzinfo=clock.APP_TIMEZONE)
    assert response.json() == {"status": "ok", "clock": expected.isoformat()}
    assert clock.is_frozen()
    assert clock.now() == expected


def test_reset_loads_the_golden_case() -> None:
    client.post("/demo/reset")

    assert roster(1) == dict.fromkeys((101, 102, 103, 104, 105), RosterStatus.ASSIGNED)
    assert roster(2) == dict.fromkeys((202, 203), RosterStatus.ASSIGNED)
    with Session(engine) as db:
        icu = db.scalars(select(StaffSkill.staff_id).where(StaffSkill.skill_id == ICU_SKILL_ID))
        assert set(icu) & set(roster(1)) == {101, 102}


def test_reset_can_run_again_on_a_used_database() -> None:
    client.post("/demo/reset")
    with Session(engine) as db:
        assignment = db.scalars(
            select(RosterAssignment).where(RosterAssignment.staff_id == 105)
        ).one()
        assignment.status = RosterStatus.CANCELLED
        db.commit()
    clock.advance(timedelta(hours=5))

    response = client.post("/demo/reset")

    assert response.status_code == 200
    assert roster(1)[105] is RosterStatus.ASSIGNED
    assert clock.now().hour == 21


def test_simultaneous_reset_requests_complete_and_allow_another_reset() -> None:
    outcome = run_in_child_process(_simultaneous_resets)

    responses = outcome["responses"]
    assert all(status == 200 and body["status"] == "ok" for status, body in responses)
    assert outcome["rosters"][1] == dict.fromkeys((101, 102, 103, 104, 105), RosterStatus.ASSIGNED)
    assert outcome["rosters"][2] == dict.fromkeys((202, 203), RosterStatus.ASSIGNED)
    assert outcome["clock_frozen"]
    assert outcome["clock_hour"] == 21
    # The original bug also caused subsequent resets to hang.
    assert outcome["follow_up_status"] == 200


def test_failed_reset_releases_lock_for_next_request() -> None:
    assert run_in_child_process(_failed_reset_then_reset) == 200
