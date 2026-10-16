"""GET /clock: read the backend clock, so pages show the time the job and check-in use."""

from fastapi import APIRouter

from app.core import clock
from app.schemas.clock import ClockView

router = APIRouter(prefix="/clock", tags=["clock"])


@router.get("")
def read_clock() -> ClockView:
    """Read only, no identity: the same clock for everyone (app.core.clock)."""
    return ClockView(now=clock.now(), frozen=clock.is_frozen())
