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


def test_advance_requires_a_frozen_clock() -> None:
    with pytest.raises(RuntimeError):
        clock.advance(timedelta(minutes=1))


def test_reset_returns_to_real_time() -> None:
    clock.set_time(DEMO_TIME)

    clock.reset()

    assert not clock.is_frozen()
    assert clock.now() != DEMO_TIME
