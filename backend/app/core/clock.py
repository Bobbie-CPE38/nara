"""
System clock (docs/workflow.md, decision D10).

Rules:
  * Every timestamp in the application comes from `now()`.
    Never call `datetime.now()` directly.
  * By default the clock follows real time. `set_time()` freezes it, so the demo
    and the tests produce the same timestamps on every run. The demo routes freeze it too:
    `POST /demo/reset` (at D 21:00) and `POST /demo/clock/freeze` (at the time it shows now,
    `freeze_now()`); `POST /demo/clock/unfreeze` follows real time again (`reset()`).
  * A frozen clock does not move by itself. Use `advance()` to move it.
  * A test run (6.35.1) puts the clock in scenario mode with `run_from()`: it runs at
    real speed from the scenario time, and `advance()` adds to a recorded offset.
    `set_time()`, `freeze_now()` and `reset()` leave scenario mode.
  * The frozen time and the scenario live in process memory. They are lost when the
    backend restarts, and `POST /demo/reset` sets the time again.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import Lock

# Thailand has no DST, so a fixed offset is enough and needs no tzdata package.
APP_TIMEZONE = timezone(timedelta(hours=7))


class ClockMode(StrEnum):
    FROZEN = "frozen"
    REAL = "real"
    SCENARIO = "scenario"


@dataclass(frozen=True)
class _Scenario:
    start: datetime
    # time.monotonic() when run_from() was called: wall-clock jumps do not move the run
    started_monotonic: float
    advanced: timedelta
    test_run_id: int


# Replaced in tests to let real time pass without sleeping
_monotonic = time.monotonic

_lock = Lock()
_frozen_at: datetime | None = None  # None = follow real time (or the scenario)
_scenario: _Scenario | None = None


def _scenario_now(scenario: _Scenario) -> datetime:
    elapsed = timedelta(seconds=_monotonic() - scenario.started_monotonic)
    return scenario.start + elapsed + scenario.advanced


def now() -> datetime:
    """Return the current system time. Always timezone-aware (+07:00)."""
    with _lock:
        if _frozen_at is not None:
            return _frozen_at
        if _scenario is not None:
            return _scenario_now(_scenario)
    return datetime.now(APP_TIMEZONE)


def set_time(frozen_at: datetime) -> None:
    """Freeze the clock at `frozen_at`, for example D 21:00 +07:00 for the demo."""
    global _frozen_at, _scenario
    if frozen_at.utcoffset() is None:
        raise ValueError("clock time must be timezone-aware")
    with _lock:
        _frozen_at = frozen_at.astimezone(APP_TIMEZONE)
        _scenario = None


def run_from(start: datetime, test_run_id: int) -> None:
    """Enter scenario mode: run at real speed from `start` for this test run (6.35.1)."""
    global _frozen_at, _scenario
    if start.utcoffset() is None:
        raise ValueError("clock time must be timezone-aware")
    with _lock:
        _frozen_at = None
        _scenario = _Scenario(
            start=start.astimezone(APP_TIMEZONE),
            started_monotonic=_monotonic(),
            advanced=timedelta(0),
            test_run_id=test_run_id,
        )


def advance(delta: timedelta) -> datetime:
    """Move a frozen clock, or a scenario's offset, by `delta` and return the new time."""
    global _frozen_at, _scenario
    with _lock:
        if _frozen_at is not None:
            _frozen_at = _frozen_at + delta
            return _frozen_at
        if _scenario is not None:
            _scenario = _Scenario(
                start=_scenario.start,
                started_monotonic=_scenario.started_monotonic,
                advanced=_scenario.advanced + delta,
                test_run_id=_scenario.test_run_id,
            )
            return _scenario_now(_scenario)
        raise RuntimeError("clock follows real time, call set_time() or run_from() first")


def freeze_now() -> datetime:
    """Freeze the clock at the time it shows (it keeps the frozen time if already frozen)."""
    global _frozen_at, _scenario
    with _lock:
        if _frozen_at is None:
            _frozen_at = (
                _scenario_now(_scenario) if _scenario is not None else datetime.now(APP_TIMEZONE)
            )
        _scenario = None
        return _frozen_at


def reset() -> None:
    """Unfreeze the clock, or leave scenario mode, so that it follows real time again."""
    global _frozen_at, _scenario
    with _lock:
        _frozen_at = None
        _scenario = None


def is_frozen() -> bool:
    with _lock:
        return _frozen_at is not None


def mode() -> ClockMode:
    with _lock:
        if _frozen_at is not None:
            return ClockMode.FROZEN
        return ClockMode.SCENARIO if _scenario is not None else ClockMode.REAL


def advanced_seconds() -> float:
    """Seconds added by advance() in scenario mode; 0 in the other modes."""
    with _lock:
        return _scenario.advanced.total_seconds() if _scenario is not None else 0.0


def test_run_id() -> int | None:
    """The test run that owns scenario mode; None in the other modes."""
    with _lock:
        return _scenario.test_run_id if _scenario is not None else None
