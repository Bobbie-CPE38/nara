"""GET /clock (round 5 PR U5, docs/workflow.md 9.7)."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core import clock
from app.main import app

client = TestClient(app)


def test_a_frozen_clock_is_reported_with_its_time_in_bangkok() -> None:
    clock.set_time(datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE))
    try:
        clock.advance(timedelta(minutes=10))
        response = client.get("/clock")
    finally:
        clock.reset()

    assert response.status_code == 200
    assert response.json() == {
        "now": "2026-10-09T21:10:00+07:00",
        "frozen": True,
        "mode": "frozen",
        "advanced_seconds": 0,
        "test_run_id": None,
    }


def test_a_test_run_clock_is_reported_with_its_run_and_offset() -> None:
    """Round 6 PR EV5a (6.35.1): the pages show the scenario mode and how far it was moved."""
    clock.run_from(datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE), test_run_id=12)
    try:
        clock.advance(timedelta(minutes=10))
        body = client.get("/clock").json()
    finally:
        clock.reset()

    assert body["frozen"] is False
    assert body["mode"] == "scenario"
    assert body["advanced_seconds"] == 600
    assert body["test_run_id"] == 12
    assert datetime.fromisoformat(body["now"]) >= datetime(
        2026, 10, 9, 21, 10, tzinfo=clock.APP_TIMEZONE
    )


def test_real_time_is_reported_as_not_frozen() -> None:
    before = clock.now()
    body = client.get("/clock").json()

    assert body["frozen"] is False
    assert body["mode"] == "real"
    assert datetime.fromisoformat(body["now"]) >= before.replace(microsecond=0)


def test_the_clock_needs_no_demo_user() -> None:
    assert client.get("/clock", headers={}).status_code == 200
