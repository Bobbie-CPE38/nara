"""
Event intake (docs/workflow.md, section 3).

One transaction: record the event, record the leave, cancel the roster row,
check the shift for a gap, then either mark the event IGNORED or open a case
and hand it to the orchestrator. If anything raises on the way, nothing of the
event is stored.

The skeleton handles STAFF_UNAVAILABLE only. The other event types have no
intake rules yet (section 12).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Shift, StaffingCase, StaffingEvent
from app.domain.enums import (
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
)
from app.services import actor_service, audit_service, gap_service, unavailability_service
from app.workflow import orchestrator


class EventNotSupportedError(ValueError):
    """The skeleton has no intake rules for this event type."""


class ShiftNotFoundError(LookupError):
    """No SHIFT row has this ID."""


class InvalidLeaveEndError(ValueError):
    """The return time is not after the start of the shift."""


def _iso(moment: datetime) -> str:
    """A time for an audit payload, always +07:00.

    A value copied from a row that was read from PostgreSQL is in UTC.
    """
    return moment.astimezone(clock.APP_TIMEZONE).isoformat()


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
    event_type: EventType,
    shift_id: int,
    end_at: datetime | None = None,
) -> EventOutcome:
    """Take in one event reported by a staff member and commit the result.

    `actor_id` is that staff member's ACTORS.id (CurrentUser.actor_id in a route).

    Every check runs before the first write, so a rejected request leaves no
    trace: EventNotSupportedError, ShiftNotFoundError, InvalidLeaveEndError and
    unavailability_service.NoAssignedRosterError.
    """
    if event_type is not EventType.STAFF_UNAVAILABLE:
        raise EventNotSupportedError(f"Event type {event_type.value} is not supported yet")
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise ShiftNotFoundError(f"No shift {shift_id}")
    if end_at is not None and end_at <= shift.start_at:
        raise InvalidLeaveEndError("end_at must be after the start of the shift")
    # Locks the roster row: a second report for the same person and shift
    # waits here, then finds the row cancelled
    roster = unavailability_service.lock_assigned_roster(db, staff_id=staff_id, shift_id=shift.id)

    event = StaffingEvent(
        event_type=event_type,
        shift_id=shift.id,
        occurred_at=clock.now(),
        staff_id=staff_id,
        status=EventStatus.RECEIVED,
    )
    db.add(event)
    unavailability = unavailability_service.record_unplanned_leave(
        db, roster=roster, shift=shift, end_at=end_at
    )

    assessment = gap_service.assess_shift(db, shift)
    case: StaffingCase | None = None
    if assessment.result.has_gap:
        event.status = EventStatus.PROCESSED
        case = StaffingCase(
            event_id=event.id,
            shift_id=shift.id,
            status=CaseStatus.OPEN,
            required_replacement_time=shift.start_at,
        )
        db.add(case)
        db.flush()
    else:
        event.status = EventStatus.IGNORED
    case_id = case.id if case is not None else None

    # The audit rows are written after the case exists so that all of them
    # carry its case_id and show up on the case timeline, in this order
    audit_service.log(
        db,
        case_id=case_id,
        actor_id=actor_id,
        action=AuditAction.EVENT_RECEIVED,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=event.id,
        payload={"event_type": event_type.value, "shift_id": shift.id, "staff_id": staff_id},
    )
    audit_service.log(
        db,
        case_id=case_id,
        actor_id=actor_id,
        action=AuditAction.UNAVAILABILITY_CREATED,
        entity_type=EntityType.STAFF_UNAVAILABILITY,
        entity_id=unavailability.id,
        payload={
            "unavailability_id": unavailability.id,
            "staff_id": staff_id,
            "reason": unavailability.reason.value,
            "start_at": _iso(unavailability.start_at),
            "end_at": _iso(unavailability.end_at) if unavailability.end_at else None,
        },
    )
    orchestrator_actor = actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR)

    if case is None:
        audit_service.log(
            db,
            case_id=None,
            actor_id=orchestrator_actor,
            action=AuditAction.EVENT_IGNORED,
            entity_type=EntityType.STAFFING_EVENTS,
            entity_id=event.id,
            payload={"event_id": event.id, "shift_id": shift.id},
        )
        db.commit()
        return EventOutcome(
            event_id=event.id, event_status=event.status, case_id=None, case_status=None
        )

    audit_service.log(
        db,
        case_id=case.id,
        actor_id=orchestrator_actor,
        action=AuditAction.CASE_OPENED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            "event_id": event.id,
            "shift_id": shift.id,
            "headcount_gap": assessment.result.headcount_gap,
        },
    )
    # Commits the whole transaction, also when the round ends in FAILED (D11)
    orchestrator.advance(db, case.id)
    return EventOutcome(
        event_id=event.id,
        event_status=event.status,
        case_id=case.id,
        case_status=case.status,
    )
