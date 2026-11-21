"""Login attempt limits (docs/workflow.md 6.33.3, PR AU1)."""

from app.core.rate_limit import Limit, RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_eleventh_attempt_in_60_seconds_is_refused_with_retry_after() -> None:
    time = FakeTime()
    limiter = RateLimiter(monotonic=time)
    limit = [Limit("login:ip:1.2.3.4", 10)]

    for _ in range(10):
        assert limiter.hit(limit) is None
        time.now += 1

    # Attempts at 1000..1009; the next is allowed once the one at 1000 leaves the window
    assert limiter.hit(limit) == 51


def test_a_key_is_allowed_again_after_the_window() -> None:
    time = FakeTime()
    limiter = RateLimiter(monotonic=time)
    limit = [Limit("k", 2)]
    assert limiter.hit(limit) is None
    assert limiter.hit(limit) is None
    assert limiter.hit(limit) is not None

    time.now += 61

    assert limiter.hit(limit) is None


def test_refused_attempts_count_too() -> None:
    time = FakeTime()
    limiter = RateLimiter(monotonic=time)
    limit = [Limit("k", 2)]
    for _ in range(2):
        limiter.hit(limit)
    time.now += 30
    assert limiter.hit(limit) is not None

    # 31 s after the first two; the refused one at +30 still counts
    time.now += 31
    assert limiter.hit(limit) is None
    assert limiter.hit(limit) is not None


def test_every_limit_counts_and_any_one_refuses() -> None:
    limiter = RateLimiter(monotonic=FakeTime())
    for ip in range(10):
        assert limiter.hit([Limit(f"ip:{ip}", 10), Limit("staff:105", 10)]) is None

    # A new IP, but the account has had ten attempts
    assert limiter.hit([Limit("ip:99", 10), Limit("staff:105", 10)]) is not None
    # The other account from that IP is fine
    assert limiter.hit([Limit("ip:99", 10), Limit("staff:201", 10)]) is None


def test_a_full_table_drops_expired_keys_then_refuses_new_ones() -> None:
    time = FakeTime()
    limiter = RateLimiter(max_keys=3, monotonic=time)
    for key in ("a", "b", "c"):
        assert limiter.hit([Limit(key, 10)]) is None

    # Full: a new key waits until the oldest key expires; known keys still work
    assert limiter.hit([Limit("d", 10)]) == 60
    assert limiter.hit([Limit("a", 10)]) is None

    time.now += 61
    assert limiter.hit([Limit("d", 10)]) is None
