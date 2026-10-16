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
    assert response.json() == {"now": "2026-10-09T21:10:00+07:00", "frozen": True}


def test_real_time_is_reported_as_not_frozen() -> None:
    before = clock.now()
    body = client.get("/clock").json()

    assert body["frozen"] is False
    assert datetime.fromisoformat(body["now"]) >= before.replace(microsecond=0)


def test_the_clock_needs_no_demo_user() -> None:
    assert client.get("/clock", headers={}).status_code == 200
