"""Demo control (docs/workflow.md 6.17, 6.33.5). On AWS the whole prefix is behind its own
Basic Auth, and in session mode every POST also needs an allowed Origin (6.33.3)."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DbSession
from app.core import clock
from app.db.models import Staff
from app.domain.enums import ActorName, CheckInSource, StaffStatus
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.attendance import CheckInResponse, SimulatedCheckIn
from app.schemas.clock import ClockView
from app.schemas.event import DemoEventCreate, EventResult
from app.schemas.job import ClockAdvance, ClockAdvanceResult
from app.seed.reset import reset_demo
from app.services import (
    actor_service,
    attendance_service,
    event_service,
    job_service,
    unavailability_service,
)
from app.services.requirement_service import RequirementNotFoundError

# payload.source of an event the Demo control simulates (6.33.4)
SIMULATED_SOURCE = CheckInSource.SIMULATED.value

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


@router.post("/events", status_code=status.HTTP_201_CREATED)
def simulate_event(body: DemoEventCreate, db: DbSession) -> EventResult:
    """The Demo control's events, now that POST /events refuses web accounts (6.33.4).

    The same validation and service as POST /events, as the demo character in
    `reporter_staff_id`, but recorded by the SYSTEM actor with payload.source SIMULATED:
    never a report of a signed-in user. No session is needed; on AWS this path is behind
    the Demo Basic Auth (6.33.5). Answers as POST /events, plus 404 for an unknown or
    inactive character. None of the errors writes anything.
    """
    reporter = db.get(Staff, body.reporter_staff_id)
    if reporter is None or reporter.status != StaffStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No active staff {body.reporter_staff_id}")
    try:
        outcome = event_service.receive_event(
            db,
            staff_id=reporter.id,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
            role_id=reporter.role_id,
            event_type=body.event_type,
            shift_id=body.shift_id,
            end_at=body.end_at,
            target_staff_id=body.staff_id,
            reason=body.reason,
            patient_count=body.patient_count,
            roles=None
            if body.roles is None
            else {item.role_id: item.required_count for item in body.roles},
            skills=None
            if body.skills is None
            else {item.skill_id: item.required_count for item in body.skills},
            source=SIMULATED_SOURCE,
        )
    except event_service.ShiftNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except RequirementNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except event_service.NotHeadNurseError as error:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except unavailability_service.NoAssignedRosterError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (event_service.InvalidEventDetailsError, event_service.InvalidLeaveEndError) as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return EventResult(
        event_id=outcome.event_id,
        event_status=outcome.event_status,
        case_id=outcome.case_id,
        case_status=outcome.case_status,
    )
