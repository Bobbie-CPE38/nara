"""
System clock (docs/workflow.md, decision D10).

Rules:
  * Every timestamp in the application comes from `now()`.
    Never call `datetime.now()` directly.
  * By default the clock follows real time. `set_time()` freezes it, so the demo
    and the tests produce the same timestamps on every run.
  * A frozen clock does not move by itself. Use `advance()` to move it.
  * The frozen time lives in process memory. It is lost when the backend
    restarts, and `POST /demo/reset` sets it again.
"""
from datetime import datetime, timedelta, timezone
from threading import Lock

# Thailand has no DST, so a fixed offset is enough and needs no tzdata package.
APP_TIMEZONE = timezone(timedelta(hours=7))

_lock = Lock()
_frozen_at: datetime | None = None   # None = follow real time


def now() -> datetime:
    """Return the current system time. Always timezone-aware (+07:00)."""
    with _lock:
        if _frozen_at is not None:
            return _frozen_at
    return datetime.now(APP_TIMEZONE)


def set_time(frozen_at: datetime) -> None:
    """Freeze the clock at `frozen_at`, for example D 21:00 +07:00 for the demo."""
    global _frozen_at
    if frozen_at.utcoffset() is None:
        raise ValueError("clock time must be timezone-aware")
    with _lock:
        _frozen_at = frozen_at.astimezone(APP_TIMEZONE)


def advance(delta: timedelta) -> datetime:
    """Move a frozen clock by `delta` and return the new time."""
    global _frozen_at
    with _lock:
        if _frozen_at is None:
            raise RuntimeError("clock is not frozen, call set_time() first")
        _frozen_at = _frozen_at + delta
        return _frozen_at


def reset() -> None:
    """Unfreeze the clock so that it follows real time again."""
    global _frozen_at
    with _lock:
        _frozen_at = None


def is_frozen() -> bool:
    with _lock:
        return _frozen_at is not None
