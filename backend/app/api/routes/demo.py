from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DbSession
from app.core import clock
from app.schemas.job import ClockAdvance, ClockAdvanceResult
from app.seed.reset import reset_demo
from app.services import job_service

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset() -> dict[str, str]:
    """Drop the database, migrate, load the Golden Case and freeze the clock at D 21:00."""
    demo_time = reset_demo()
    return {"status": "ok", "clock": demo_time.isoformat()}


@router.post("/clock/advance")
def advance_clock(body: ClockAdvance, db: DbSession) -> ClockAdvanceResult:
    """Move the frozen demo clock forward, then expire offers, recover cases and close due windows.

    Runs the same function as the job service: a frozen clock that moves does
    not wake the job up. 409 when the clock is not frozen (no reset yet since
    the backend started).
    """
    if not clock.is_frozen():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The demo clock is not frozen. Call POST /demo/reset first"
        )
    now = clock.advance(timedelta(seconds=body.seconds))
    return ClockAdvanceResult.of(now, job_service.run_due_work(db))
