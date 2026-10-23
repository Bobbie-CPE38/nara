from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from app.core import clock

DEMO_TIME = datetime(2026, 10, 8, 21, 0, tzinfo=clock.APP_TIMEZONE)


@pytest.fixture(autouse=True)
def unfrozen_clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


def test_now_follows_real_time_by_default() -> None:
    before = datetime.now(UTC)
    current = clock.now()
    after = datetime.now(UTC)

    assert not clock.is_frozen()
    assert before <= current <= after


def test_now_is_timezone_aware_in_app_timezone() -> None:
    assert clock.now().utcoffset() == timedelta(hours=7)


def test_set_time_freezes_the_clock() -> None:
    clock.set_time(DEMO_TIME)

    assert clock.is_frozen()
    assert clock.now() == DEMO_TIME
    assert clock.now() == DEMO_TIME  # does not move by itself


def test_set_time_converts_to_app_timezone() -> None:
    clock.set_time(datetime(2026, 10, 8, 14, 0, tzinfo=UTC))

    assert clock.now() == DEMO_TIME
    assert clock.now().utcoffset() == timedelta(hours=7)


def test_set_time_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        clock.set_time(datetime(2026, 10, 8, 21, 0))

    assert not clock.is_frozen()


def test_advance_moves_a_frozen_clock() -> None:
    clock.set_time(DEMO_TIME)

    returned = clock.advance(timedelta(minutes=15))

    assert returned == DEMO_TIME + timedelta(minutes=15)
    assert clock.now() == returned


def test_advance_requires_a_frozen_or_scenario_clock() -> None:
    with pytest.raises(RuntimeError):
        clock.advance(timedelta(minutes=1))


def test_run_from_follows_real_time_from_the_scenario_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((1000.0, 1090.0))
    monkeypatch.setattr(clock, "_monotonic", lambda: next(ticks))

    clock.run_from(DEMO_TIME, test_run_id=7)

    assert clock.mode() == clock.ClockMode.SCENARIO
    assert not clock.is_frozen()
    assert clock.test_run_id() == 7
    assert clock.now() == DEMO_TIME + timedelta(seconds=90)


def test_advance_in_scenario_mode_adds_to_the_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    real = {"now": 1000.0}
    monkeypatch.setattr(clock, "_monotonic", lambda: real["now"])
    clock.run_from(DEMO_TIME, test_run_id=7)
    real["now"] = 1030.0

    returned = clock.advance(timedelta(minutes=10))
    real["now"] = 1040.0

    assert returned == DEMO_TIME + timedelta(seconds=30, minutes=10)
    assert clock.now() == DEMO_TIME + timedelta(seconds=40, minutes=10)
    assert clock.advanced_seconds() == 600
    assert clock.mode() == clock.ClockMode.SCENARIO


@pytest.mark.parametrize("leave", ["set_time", "freeze_now", "reset"])
def test_every_other_clock_call_leaves_scenario_mode(
    monkeypatch: pytest.MonkeyPatch, leave: str
) -> None:
    monkeypatch.setattr(clock, "_monotonic", lambda: 1000.0)
    clock.run_from(DEMO_TIME, test_run_id=7)
    clock.advance(timedelta(minutes=5))

    if leave == "set_time":
        clock.set_time(DEMO_TIME)
    elif leave == "freeze_now":
        # Freezes at the time the scenario shows, not at real time
        assert clock.freeze_now() == DEMO_TIME + timedelta(minutes=5)
    else:
        clock.reset()

    assert clock.mode() != clock.ClockMode.SCENARIO
    assert clock.test_run_id() is None
    assert clock.advanced_seconds() == 0


def test_mode_names_each_state() -> None:
    assert clock.mode() == clock.ClockMode.REAL
    clock.set_time(DEMO_TIME)
    assert clock.mode() == clock.ClockMode.FROZEN


def test_run_from_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        clock.run_from(datetime(2026, 10, 8, 21, 0), test_run_id=1)

    assert clock.mode() == clock.ClockMode.REAL


def test_reset_returns_to_real_time() -> None:
    clock.set_time(DEMO_TIME)

    clock.reset()

    assert not clock.is_frozen()
    assert clock.now() != DEMO_TIME
