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


# --------------------------------------------------------------------------- #
# Round 6 PR EV6 (6.36.1): set the clock to any time, frozen or running on from it
# --------------------------------------------------------------------------- #
def _near_today(hours: int) -> datetime:
    """A time a few hours from real time, inside the range the route allows."""
    real = datetime.now(clock.APP_TIMEZONE).replace(minute=0, second=0, microsecond=0)
    return real + timedelta(hours=hours)


def test_set_freezes_the_clock_at_the_time_picked() -> None:
    at = _near_today(30)
    try:
        body = client.post("/demo/clock/set", json={"at": at.isoformat()}).json()
    finally:
        clock.reset()

    assert body["mode"] == "frozen" and body["frozen"] is True
    assert datetime.fromisoformat(body["now"]) == at


def test_set_running_runs_on_from_the_time_picked() -> None:
    at = _near_today(-5)
    try:
        body = client.post("/demo/clock/set", json={"at": at.isoformat(), "running": True}).json()
        later = clock.now()
        # An advance moves it forward and it keeps running from there
        advanced = client.post("/demo/clock/advance", json={"seconds": 600})
        after_advance = clock.now()
    finally:
        clock.reset()

    assert body["mode"] == "running" and body["frozen"] is False
    assert at <= datetime.fromisoformat(body["now"]) <= later < at + timedelta(minutes=1)
    assert advanced.status_code == 200
    assert after_advance >= at + timedelta(minutes=10)


def test_resume_runs_on_from_the_frozen_time() -> None:
    """The bug of the AWS machine: Unfreeze went back to real time. Resume keeps the time."""
    at = _near_today(48)
    clock.set_time(at)
    try:
        body = client.post("/demo/clock/resume").json()
        shown = clock.now()
    finally:
        clock.reset()

    assert body["mode"] == "running"
    assert at <= shown < at + timedelta(minutes=1)


def test_set_refuses_a_time_far_from_real_time_and_a_naive_one() -> None:
    far = _near_today(24 * 400)

    assert client.post("/demo/clock/set", json={"at": far.isoformat()}).status_code == 422
    naive = far.replace(tzinfo=None) - timedelta(days=390)
    assert client.post("/demo/clock/set", json={"at": naive.isoformat()}).status_code == 422
    assert clock.mode() == clock.ClockMode.REAL
