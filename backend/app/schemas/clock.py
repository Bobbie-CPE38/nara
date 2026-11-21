from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from app.core import clock
from app.core.clock import ClockMode
from app.schemas.types import AppDatetime

# How far from real time the Demo control may set the clock (6.36.1): a year both ways
# covers any demo, and keeps a typing slip from landing in another century
CLOCK_SET_RANGE = timedelta(days=366)


class DemoReset(BaseModel):
    """Optional body of POST /demo/reset (round 6 PR EV6, 6.36.3)."""

    model_config = ConfigDict(extra="forbid")
    # True: the Golden Case and the hospital demo; False: the Golden Case alone
    hospital: bool


class ClockSet(BaseModel):
    """Body of POST /demo/clock/set (round 6 PR EV6, 6.36.1)."""

    model_config = ConfigDict(extra="forbid")
    at: AppDatetime
    # True: the clock runs on at real speed from `at`; False: it stays frozen there
    running: bool = False

    @field_validator("at")
    @classmethod
    def _near_real_time(cls, value: datetime) -> datetime:
        # Real time like the date of a reset (D10), not clock.now(): the bound must not
        # move with the demo clock
        real_now = datetime.now(clock.APP_TIMEZONE)
        if abs(value - real_now) > CLOCK_SET_RANGE:
            raise ValueError("the time must be within 366 days of real time")
        return value


class ClockView(BaseModel):
    """GET /clock: the time the backend runs on (docs/workflow.md 9.7, R5-Q18)."""

    now: AppDatetime
    # True while the demo clock is frozen; False when it follows real time, a test run or
    # a time picked on the Demo control
    frozen: bool
    # Round 6 PR EV5a (6.35.1): which state, and in scenario mode the seconds moved by
    # advance and the test run that owns the clock (else 0 and None). PR EV6 adds the
    # running mode (6.36.1), which also counts its advances
    mode: ClockMode
    advanced_seconds: float = 0
    test_run_id: int | None = None

    @classmethod
    def current(cls) -> "ClockView":
        return cls(
            now=clock.now(),
            frozen=clock.is_frozen(),
            mode=clock.mode(),
            advanced_seconds=clock.advanced_seconds(),
            test_run_id=clock.test_run_id(),
        )
