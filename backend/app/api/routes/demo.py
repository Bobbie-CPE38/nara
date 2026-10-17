from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DbSession
from app.core import clock
from app.db.models import Staff
from app.domain.enums import ActorName, CheckInSource
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.attendance import CheckInResponse, SimulatedCheckIn
from app.schemas.clock import ClockView
from app.schemas.job import ClockAdvance, ClockAdvanceResult
from app.seed.reset import reset_demo
from app.services import (
    actor_service,
    attendance_service,
    job_service,
    unavailability_service,
)

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


@router.post("/clock/freeze")
def freeze_clock() -> ClockView:
    """Freeze the clock at the time it shows now. Already frozen: nothing changes."""
    return ClockView(now=clock.freeze_now(), frozen=True)


@router.post("/clock/unfreeze")
def unfreeze_clock() -> ClockView:
    """Let the clock follow real time again (POST /demo/reset freezes it once more)."""
    clock.reset()
    return ClockView(now=clock.now(), frozen=False)


@router.post("/attendance/check-in")
def simulate_check_in(body: SimulatedCheckIn, db: DbSession) -> CheckInResponse:
    """Simulate the arrival of a character: no X-Demo-User, audit source SIMULATED by SYSTEM.

    Same function and answers as POST /me/attendance/check-in, plus 404 for an
    unknown staff ID. Must stay unreachable from the public channel (section 6.24).
    """
    try:
        if db.get(Staff, body.staff_id) is None:
            raise StaffNotFoundError(f"No staff {body.staff_id}")
        result = attendance_service.check_in(
            db,
            staff_id=body.staff_id,
            shift_id=body.shift_id,
            source=CheckInSource.SIMULATED,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        )
    except (
        StaffNotFoundError,
        ShiftNotFoundError,
        unavailability_service.NoAssignedRosterError,
    ) as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except attendance_service.CheckInOutsideWindowError as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except attendance_service.CheckInLockRetryError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return CheckInResponse(**vars(result))
