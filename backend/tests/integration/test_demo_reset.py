"""POST /demo/reset rebuilds the Golden Case (docs/walking-skeleton.md step 2.3).

The reset commits to the test database, so every test here puts back the empty,
migrated schema that the other tests expect.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

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


@pytest.fixture(autouse=True)
def restore_empty_database() -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    clock.reset()


def roster(shift_id: int) -> dict[int, RosterStatus]:
    with Session(engine) as db:
        rows = db.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == shift_id))
        return {row.staff_id: row.status for row in rows}


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
