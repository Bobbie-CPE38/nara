from pydantic import BaseModel

from app.core import clock
from app.core.clock import ClockMode
from app.schemas.types import AppDatetime


class ClockView(BaseModel):
    """GET /clock: the time the backend runs on (docs/workflow.md 9.7, R5-Q18)."""

    now: AppDatetime
    # True while the demo clock is frozen; False when it follows real time or a test run
    frozen: bool
    # Round 6 PR EV5a (6.35.1): which of the three states, and in scenario mode the
    # seconds moved by advance and the test run that owns the clock (else 0 and None)
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
