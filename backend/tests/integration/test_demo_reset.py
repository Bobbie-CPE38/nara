"""POST /demo/reset rebuilds the Golden Case (docs/walking-skeleton.md step 2.3).

The reset commits to the test database, so every test here puts back the empty,
migrated schema that the other tests expect.
"""

import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from threading import Barrier, Thread
from typing import TypeVar, cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, StaffSkill
from app.db.session import engine
from app.domain.enums import RosterStatus
from app.main import app
from app.seed.reset import ALEMBIC_INI

client = TestClient(app)

ICU_SKILL_ID = 1

T = TypeVar("T")


@pytest.fixture(autouse=True)
def restore_empty_database() -> Iterator[None]:
    yield
    with engine.begin() as connection:
        # A reset that hung in another thread may still hold schema locks; end its
        # session so the DROP cannot block forever and the hung thread releases its lock
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        )
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    clock.reset()


def roster(shift_id: int) -> dict[int, RosterStatus]:
    with Session(engine) as db:
        rows = db.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == shift_id))
        return {row.staff_id: row.status for row in rows}


def run_concurrently(*calls: Callable[[], T], timeout: float = 30.0) -> list[T]:
    """Run each call in its own thread and return the results in order.

    Fails the test if any call is still running after `timeout` seconds. Daemon threads
    are used instead of ThreadPoolExecutor, whose shutdown waits for a stuck worker and
    would hang the run instead of failing it.
    """
    results: list[T | None] = [None] * len(calls)
    errors: list[BaseException] = []

    def run(index: int, call: Callable[[], T]) -> None:
        try:
            results[index] = call()
        except BaseException as error:
            errors.append(error)

    threads = [
        Thread(target=run, args=(index, call), daemon=True) for index, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    if any(thread.is_alive() for thread in threads):
        pytest.fail(f"Reset did not finish within {timeout:g}s; it may be deadlocked")
    if errors:
        raise errors[0]
    return cast(list[T], results)


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
    start = Barrier(2)

    def request_reset() -> tuple[int, dict[str, str]]:
        # Separate clients simulate two browsers clicking Reset at the same time.
        with TestClient(app) as request_client:
            start.wait(timeout=5)
            response = request_client.post("/demo/reset")
            return response.status_code, response.json()

    results = run_concurrently(request_reset, request_reset)

    assert all(status == 200 and body["status"] == "ok" for status, body in results)
    assert roster(1) == dict.fromkeys((101, 102, 103, 104, 105), RosterStatus.ASSIGNED)
    assert roster(2) == dict.fromkeys((202, 203), RosterStatus.ASSIGNED)
    assert clock.is_frozen()
    assert clock.now().hour == 21
    # The original bug also caused subsequent resets to hang.
    [response] = run_concurrently(lambda: client.post("/demo/reset"))
    assert response.status_code == 200


def test_failed_reset_releases_lock_for_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.seed import reset as reset_module

    def fail() -> datetime:
        raise RuntimeError("Reset failed")

    with monkeypatch.context() as patch:
        patch.setattr(reset_module, "_reset_demo", fail)
        with pytest.raises(RuntimeError, match="Reset failed"):
            run_concurrently(reset_module.reset_demo)

    [response] = run_concurrently(lambda: client.post("/demo/reset"))
    assert response.status_code == 200
