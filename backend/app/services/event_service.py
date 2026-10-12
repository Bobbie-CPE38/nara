"""
Event intake: PART A of docs/workflow.md, section 3.

One transaction per event: lock the shift, check the request, store the event
as RECEIVED with its details in the payload, and write EVENT_RECEIVED. No other
table is touched here. The leave, the roster, the patient count and the
requirement are updated when the merge window of the shift closes
(merge_window_service, PART B).

A shift with merge_window_seconds = 0 closes its window right away, in the same
transaction, so the answer already carries the case. That does not happen while
another case of the shift is still running: the event then waits as RECEIVED.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, MAX_EVENT_REASON_LENGTH
from app.db.models import Role, Shift, StaffingCase, StaffingEvent
from app.domain.enums import (
    STAFF_EVENT_TYPES,
    AuditAction,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
)

# Re-exported: routes and tests still reach it as event_service.ShiftNotFoundError
from app.domain.errors import ShiftNotFoundError as ShiftNotFoundError
from app.services import (
    audit_service,
    merge_window_service,
    requirement_service,
    unavailability_service,
)
from app.services.merge_window_service import REPORTED_BY


class EventNotFoundError(LookupError):
    """No STAFFING_EVENTS row has this ID."""


class InvalidLeaveEndError(ValueError):
    """The return time is not after the start of the shift."""


class InvalidEventDetailsError(ValueError):
    """The details do not fit the event type or the requirement of the shift."""


class NotHeadNurseError(PermissionError):
    """Only a head nurse may report this event type."""


@dataclass(frozen=True)
class EventOutcome:
    event_id: int
    event_status: EventStatus
    case_id: int | None
    case_status: CaseStatus | None


def receive_event(
    db: Session,
    *,
    staff_id: int,
    actor_id: int,
    role_id: int,
    event_type: EventType,
    shift_id: int,
    end_at: datetime | None = None,
    target_staff_id: int | None = None,
    reason: str | None = None,
    patient_count: int | None = None,
    roles: Mapping[int, int] | None = None,
    skills: Mapping[int, int] | None = None,
) -> EventOutcome:
    """Take in one event reported by a staff member and commit the result.

    `staff_id`, `actor_id` and `role_id` describe the reporter (CurrentUser in a
    route). The other arguments are the details of each event type:

      * STAFF_UNAVAILABLE: `end_at`, optional. The reporter is the one on leave.
      * ASSIGNMENT_CANCELLED: `target_staff_id` and `reason`.
      * PATIENT_SURGE: `patient_count`, the new total of the shift.
      * REQUIREMENT_CHANGED: `roles` and `skills`, ID to new required count.

    Every check runs before the first write, so a rejected request leaves no
    trace: ShiftNotFoundError, requirement_service.RequirementNotFoundError,
    InvalidLeaveEndError, InvalidEventDetailsError, NotHeadNurseError and
    unavailability_service.NoAssignedRosterError.
    """
    shift = merge_window_service.lock_shift(db, shift_id)
    # Closing the window needs the requirement for the threshold and the gap.
    # Without one the close would fail every time, the event would stay
    # RECEIVED, and every later event of the shift would queue behind it
    requirement_service.get_current_requirement(db, shift.id)
    if event_type is EventType.STAFF_UNAVAILABLE:
        subject_staff_id: int | None = staff_id
        payload = _leave_details(shift, end_at)
    else:
        _require_head_nurse(db, role_id)
        if event_type is EventType.ASSIGNMENT_CANCELLED:
            subject_staff_id, payload = _cancellation_details(target_staff_id, reason)
        elif event_type is EventType.PATIENT_SURGE:
            subject_staff_id, payload = None, _patient_count_details(patient_count)
        else:
            subject_staff_id, payload = None, _requirement_details(db, shift, roles, skills)
        payload[REPORTED_BY] = staff_id
    if event_type in STAFF_EVENT_TYPES:
        assert subject_staff_id is not None
        # Taken after the shift lock, always in this order. It does not stop a
        # second report in the same window: the row is cancelled only when the
        # window closes, and the second event is then IGNORED there (Q44)
        unavailability_service.lock_assigned_roster(
            db, staff_id=subject_staff_id, shift_id=shift.id
        )

    event = StaffingEvent(
        event_type=event_type,
        shift_id=shift.id,
        occurred_at=clock.now(),
        staff_id=subject_staff_id,
        payload=payload,
        status=EventStatus.RECEIVED,
    )
    db.add(event)
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=actor_id,
        action=AuditAction.EVENT_RECEIVED,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=event.id,
        payload={
            "event_type": event_type.value,
            "shift_id": shift.id,
            "staff_id": subject_staff_id,
        },
    )

    # A window of 0 seconds is due at once, unless a case of the shift is still
    # running. close_locked_window() commits when it closes the window
    if (
        shift.merge_window_seconds > 0
        or merge_window_service.close_locked_window(db, shift) is None
    ):
        db.commit()
    return _outcome(db, event)


def get_event(db: Session, event_id: int) -> EventOutcome:
    """The status of an event and the case it became part of. Read-only."""
    event = db.get(StaffingEvent, event_id)
    if event is None:
        raise EventNotFoundError(f"No event {event_id}")
    return _outcome(db, event)


def _outcome(db: Session, event: StaffingEvent) -> EventOutcome:
    case = None if event.case_id is None else db.get(StaffingCase, event.case_id)
    return EventOutcome(
        event_id=event.id,
        event_status=event.status,
        case_id=None if case is None else case.id,
        case_status=None if case is None else case.status,
    )


def _require_head_nurse(db: Session, role_id: int) -> None:
    head_nurse = db.scalar(select(Role.id).where(Role.name == HEAD_NURSE_ROLE))
    if head_nurse is None or role_id != head_nurse:
        raise NotHeadNurseError("Only a head nurse can report this event type")


def _leave_details(shift: Shift, end_at: datetime | None) -> dict[str, Any]:
    if end_at is None:
        return {}
    if end_at <= shift.start_at:
        raise InvalidLeaveEndError("end_at must be after the start of the shift")
    return {"end_at": merge_window_service.iso(end_at)}


def _cancellation_details(
    target_staff_id: int | None, reason: str | None
) -> tuple[int, dict[str, Any]]:
    if target_staff_id is None:
        raise InvalidEventDetailsError("staff_id of the cancelled person is required")
    if reason is None or not reason.strip():
        raise InvalidEventDetailsError("reason is required")
    if len(reason.strip()) > MAX_EVENT_REASON_LENGTH:
        raise InvalidEventDetailsError(
            f"reason must be at most {MAX_EVENT_REASON_LENGTH} characters"
        )
    return target_staff_id, {"reason": reason.strip()}


def _patient_count_details(patient_count: int | None) -> dict[str, Any]:
    if patient_count is None or patient_count < 0:
        raise InvalidEventDetailsError("patient_count must be zero or more")
    return {"patient_count": patient_count}


def _requirement_details(
    db: Session,
    shift: Shift,
    roles: Mapping[int, int] | None,
    skills: Mapping[int, int] | None,
) -> dict[str, Any]:
    roles, skills = roles or {}, skills or {}
    if not roles and not skills:
        raise InvalidEventDetailsError("At least one role or skill is required")
    if any(count < 0 for count in (*roles.values(), *skills.values())):
        raise InvalidEventDetailsError("required_count must be zero or more")

    shift_requirement = requirement_service.get_current_requirement(db, shift.id)
    unknown_roles = sorted(set(roles) - set(shift_requirement.required_roles))
    unknown_skills = sorted(set(skills) - set(shift_requirement.required_skills))
    if unknown_roles or unknown_skills:
        raise InvalidEventDetailsError(
            f"Not in the requirement of shift {shift.id}: "
            f"roles {unknown_roles}, skills {unknown_skills}"
        )
    return {
        "roles": [
            {"role_id": role_id, "required_count": count}
            for role_id, count in sorted(roles.items())
        ],
        "skills": [
            {"skill_id": skill_id, "required_count": count}
            for skill_id, count in sorted(skills.items())
        ],
    }
