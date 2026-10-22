"""Light attempt limits for login (and AU5 register), docs/workflow.md 6.33.3.

A sliding window per key, in this process's memory: lost on restart and not shared
between processes, which is accepted for one Backend process per machine. Every attempt
counts, right or wrong, and a refused one too. Nothing locks an account.

The table holds at most MAX_KEYS keys. Expired keys go first; if it is still full, a
new key is refused until one expires instead of the table growing without bound.
Accepted limitation: someone can fill the table and keep new users out for a while,
so this is not a denial-of-service defence.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

WINDOW_SECONDS = 60.0
MAX_KEYS = 10_000

LOGIN_PER_IP = 10
LOGIN_PER_ACCOUNT = 10


@dataclass(frozen=True)
class Limit:
    key: str
    attempts: int


class RateLimiter:
    def __init__(
        self,
        *,
        window_seconds: float = WINDOW_SECONDS,
        max_keys: int = MAX_KEYS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_seconds
        self._max_keys = max_keys
        self._monotonic = monotonic
        self._lock = Lock()
        # Newest attempts of each key, at most limit + 1 of them
        self._attempts: dict[str, deque[float]] = {}

    def hit(self, limits: list[Limit]) -> int | None:
        """Count one attempt under every limit. None = allowed, otherwise the seconds
        to wait (for Retry-After). All keys are checked and counted together."""
        with self._lock:
            now = self._monotonic()
            new_keys = [limit.key for limit in limits if limit.key not in self._attempts]
            if new_keys and len(self._attempts) + len(new_keys) > self._max_keys:
                self._drop_expired(now)
                if len(self._attempts) + len(new_keys) > self._max_keys:
                    return self._seconds_until_a_key_expires(now)
            wait = 0.0
            for limit in limits:
                attempts = self._attempts.get(limit.key)
                if attempts is None or attempts.maxlen != limit.attempts + 1:
                    attempts = deque(attempts or (), maxlen=limit.attempts + 1)
                    self._attempts[limit.key] = attempts
                attempts.append(now)
                # One more than the limit inside the window: refuse until the second
                # oldest leaves it, when the next attempt would be the limit-th
                if len(attempts) > limit.attempts and attempts[0] > now - self._window:
                    wait = max(wait, attempts[1] + self._window - now)
            return None if wait == 0 else max(1, math.ceil(wait))

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _drop_expired(self, now: float) -> None:
        cutoff = now - self._window
        for key in [key for key, attempts in self._attempts.items() if attempts[-1] <= cutoff]:
            del self._attempts[key]

    def _seconds_until_a_key_expires(self, now: float) -> int:
        oldest_newest = min(attempts[-1] for attempts in self._attempts.values())
        return max(1, math.ceil(oldest_newest + self._window - now))


limiter = RateLimiter()
