"""Event intake (docs/workflow.md, section 3).

Session mode (6.33.4, round 6 PR AU2): POST /events is refused to every web account (403);
a nurse reports their own leave with POST /me/unavailability and the Demo control uses
POST /demo/events. GET /events/{id} needs a user who may see the event.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.dependencies import (
    DbSession,
    DemoUser,
    Reader,
    access_viewer,
    deny_in_session,
    forbidden,
)
from app.core.constants import MAX_BIGINT
from app.db.models import StaffingEvent
from app.schemas.event import EventCreate, EventResult
from app.services import access_service, event_service
from app.services.event_service import (
    EventNotFoundError,
    EventOutcome,
    InvalidEventDetailsError,
    InvalidLeaveEndError,
    NotHeadNurseError,
    ShiftNotFoundError,
)
from app.services.requirement_service import RequirementNotFoundError
from app.services.unavailability_service import NoAssignedRosterError

router = APIRouter(prefix="/events", tags=["events"])

# Out of the bigint range is a 422 here, not a 500 from PostgreSQL
EventId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


def _result(outcome: EventOutcome) -> EventResult:
    return EventResult(
        event_id=outcome.event_id,
        event_status=outcome.event_status,
        case_id=outcome.case_id,
        case_status=outcome.case_status,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(
    user: DemoUser,
    # After the user (401 first), before the body: 403 in session mode, nothing written
    _closed: Annotated[None, Depends(deny_in_session)],
    body: EventCreate,
    db: DbSession,
) -> EventResult:
    """Report an event as the X-Demo-User staff member.

    201 also when the workflow ended in FAILED: that is a recorded result, shown
    in `case_status`. `event_status` RECEIVED means the event waits for the
    merge window of its shift; read it again with GET /events/{event_id}.
    None of the errors below writes anything.
    """
    try:
        outcome = event_service.receive_event(
            db,
            staff_id=user.staff.id,
            actor_id=user.actor_id,
            role_id=user.staff.role_id,
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
        )
    except ShiftNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except RequirementNotFoundError as error:
        # The shift is not set up for staffing yet: its window could never close
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except NotHeadNurseError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except NoAssignedRosterError as error:
        # Not on that shift, or the window that cancelled the row already closed
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (InvalidEventDetailsError, InvalidLeaveEndError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return _result(outcome)


@router.get("/{event_id}")
def get_event(event_id: EventId, db: DbSession, reader: Reader) -> EventResult:
    """Status of an event and the case it became part of. No X-Demo-User needed in demo
    mode; session mode needs a user who may see it (401, 404, then 403).

    The same shape as the answer of POST /events, for a reporter whose event
    was RECEIVED and who wants to know what its merge window made of it.
    """
    try:
        outcome = event_service.get_event(db, event_id)
    except EventNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    if reader is not None:
        event = db.get(StaffingEvent, event_id)
        assert event is not None
        if not access_service.sees_event(db, access_viewer(db, reader), event):
            raise forbidden()
    return _result(outcome)
