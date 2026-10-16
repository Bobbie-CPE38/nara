"""
Closing the merge window of a shift: PART B of docs/workflow.md, section 3.

Events of one shift wait as RECEIVED. When the window is due, one transaction
under the shift lock applies every waiting event in order, checks the threshold
after each, and then judges the shift once from its final state: at most one
case per window, and every event of the window ends PROCESSED or IGNORED.

If anything raises on the way, nothing of the close is stored: every event is
still RECEIVED and the window is closed again on the next try.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Attendance,
    HardConstraintPolicy,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffUnavailability,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    COVERING_ROSTER_STATUSES,
    ActorName,
    AuditAction,
    AvailabilityReason,
    CaseStatus,
    EntityType,
    EventIgnoredReason,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.domain.errors import ShiftNotFoundError
from app.domain.staffing.gap_calculator import required_staff_for
from app.domain.staffing.threshold import ThresholdResult, check_threshold
from app.services import (
    actor_service,
    attendance_service,
    audit_service,
    gap_service,
    handoff_service,
    late_arrival_service,
    policy_service,
    requirement_service,
    unavailability_service,
)
from app.services.unavailability_service import NoAssignedRosterError
from app.workflow import orchestrator

logger = logging.getLogger(__name__)

# Key of STAFFING_EVENTS.payload that names who reported an event about someone
# or something else. A leave is reported by the person themselves (staff_id)
REPORTED_BY = "reported_by"

# Value of payload["reason"] on a STAFF_UNAVAILABLE event that the NO_SHOW job
# wrote (stage 1, workflow.md 6.24). A leave event has no such key
NO_SHOW_REASON = "NO_SHOW"


@dataclass(frozen=True)
class ClosedWindow:
    """What one window close did. case_id is None when no case was opened."""

    shift_id: int
    event_ids: tuple[int, ...]
    case_id: int | None
    case_status: CaseStatus | None


class _NotApplicableError(Exception):
    """The tables of one event cannot be updated. Only that event is IGNORED (Q44)."""

    def __init__(self, reason: EventIgnoredReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def iso(moment: datetime) -> str:
    """A time for an event or audit payload, always +07:00.

    A value copied from a row that was read from PostgreSQL is in UTC.
    """
    return moment.astimezone(clock.APP_TIMEZONE).isoformat()


def lock_shift(db: Session, shift_id: int) -> Shift:
    """Return the shift, locked until this transaction commits.

    Receiving an event and closing a window both take this lock first. An event
    that arrives during a close waits here and becomes the first event of the
    next window; without the lock it could be read by a close that then misses
    its roster change, or two closes could open two cases for one shift.

    FOR NO KEY UPDATE, not FOR UPDATE: other transactions that insert a row
    referencing this shift (a roster row, a candidate item) take KEY SHARE on
    it. FOR UPDATE would make them wait for event intake; this mode does not.
    """
    shift = db.scalar(
        select(Shift)
        .where(Shift.id == shift_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if shift is None:
        raise ShiftNotFoundError(f"No shift {shift_id}")
    return shift


def find_due_shift_ids(db: Session) -> list[int]:
    """Shifts whose window can close now, by ID. Read-only, takes no lock.

    A hint only: close_window() checks again under the shift lock.
    """
    shift_ids = db.scalars(
        select(StaffingEvent.shift_id)
        .where(StaffingEvent.status == EventStatus.RECEIVED)
        .distinct()
        .order_by(StaffingEvent.shift_id)
    ).all()
    due = []
    for shift_id in shift_ids:
        shift = db.get(Shift, shift_id)
        if shift is not None and _is_due(db, shift, _waiting_events(db, shift_id)):
            due.append(shift_id)
    return due


def close_window(db: Session, shift_id: int) -> ClosedWindow | None:
    """Close the window of one shift if it is due, in one transaction. Commits.

    Returns None, with nothing written, when the shift has no waiting event,
    the window is still open, or a case of the shift is still running.
    """
    shift = lock_shift(db, shift_id)
    closed = close_locked_window(db, shift)
    if closed is None:
        # Nothing was written: this only releases the shift lock
        db.commit()
    return closed


def close_due_windows(db: Session) -> list[ClosedWindow]:
    """Close every window that is due, one transaction per shift.

    A shift whose close raises is rolled back and skipped: its events stay
    RECEIVED and the next call tries again (section 3.9). The other shifts
    are not affected.
    """
    closed = []
    for shift_id in find_due_shift_ids(db):
        try:
            window = close_window(db, shift_id)
        except Exception:
            logger.exception("Closing the merge window of shift %s failed", shift_id)
            db.rollback()
            continue
        if window is not None:
            closed.append(window)
    return closed


def close_locked_window(db: Session, shift: Shift) -> ClosedWindow | None:
    """PART B for a shift the caller has locked with lock_shift().

    Commits only when a window was closed. Returns None without writing or
    committing when it is not due; the caller then ends its own transaction.
    """
    # The caller may have just added an event (a window of 0 seconds)
    db.flush()
    events = _waiting_events(db, shift.id)
    if not _is_due(db, shift, events):
        return None

    now = clock.now()
    policy = policy_service.get_hard_constraint_policy(db)
    orchestrator_actor = actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR)
    skipped: set[int] = set()
    # Events that only record history, like a NO_SHOW of a shift that has ended
    history_only: set[int] = set()
    first_passed: StaffingEvent | None = None

    # Every event updates its tables first. Whether a case opens is decided
    # only after the last one: a later event can undo what an earlier one did
    for event in events:
        try:
            counts_for_threshold = _apply(db, shift, event)
        except _NotApplicableError as error:
            skipped.add(event.id)
            _ignore(db, event, now=now, actor_id=orchestrator_actor, reason=error.reason)
            continue
        if not counts_for_threshold:
            history_only.add(event.id)
            continue
        if first_passed is None and _check_threshold(db, shift, policy).passed:
            first_passed = event

    case: StaffingCase | None = None
    reason = EventIgnoredReason.THRESHOLD_NOT_PASSED
    headcount_gap = 0
    if first_passed is not None:
        requirement = requirement_service.get_current_requirement(db, shift.id).requirement
        requirement.required_staff = required_staff_for(
            shift.patient_count, policy.maximum_patients_per_nurse
        )
        # Flushes, so the gap is measured against the value just written
        assessment = gap_service.assess_shift(db, shift)
        headcount_gap = assessment.result.headcount_gap
        if assessment.result.has_gap:
            case = StaffingCase(
                shift_id=shift.id,
                status=CaseStatus.OPEN,
                required_replacement_time=shift.start_at,
            )
            db.add(case)
            db.flush()
        else:
            reason = EventIgnoredReason.NO_GAP

    for event in events:
        if event.id in skipped:
            continue
        if case is None:
            _ignore(
                db,
                event,
                now=now,
                actor_id=orchestrator_actor,
                reason=EventIgnoredReason.SHIFT_ENDED if event.id in history_only else reason,
            )
        else:
            # Also the events that did not pass the threshold themselves (Q42)
            event.status = EventStatus.PROCESSED
            event.processed_at = now
            event.case_id = case.id
    event_ids = tuple(event.id for event in events)

    if case is None or first_passed is None:
        db.commit()
        return ClosedWindow(shift_id=shift.id, event_ids=event_ids, case_id=None, case_status=None)

    audit_service.log(
        db,
        case_id=case.id,
        actor_id=orchestrator_actor,
        action=AuditAction.CASE_OPENED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            # The first event that passed the threshold. Every event of the
            # case is in STAFFING_EVENTS.case_id
            "event_id": first_passed.id,
            "shift_id": shift.id,
            "headcount_gap": headcount_gap,
        },
    )
    # The gap of the new case covers the whole shift, so it replaces a case a
    # head nurse was still handling by hand (section 6.12, R2-Q19)
    handoff_service.close_superseded(db, shift_id=shift.id, successor_case_id=case.id)
    # Commits the whole transaction, also when the round ends in FAILED (D11)
    orchestrator.advance(db, case.id)
    return ClosedWindow(
        shift_id=shift.id, event_ids=event_ids, case_id=case.id, case_status=case.status
    )


def _waiting_events(db: Session, shift_id: int) -> list[StaffingEvent]:
    """The window of the shift: its RECEIVED events in the order they are applied."""
    return list(
        db.scalars(
            select(StaffingEvent)
            .where(
                StaffingEvent.shift_id == shift_id,
                StaffingEvent.status == EventStatus.RECEIVED,
            )
            .order_by(StaffingEvent.occurred_at, StaffingEvent.id)
        )
    )


def _is_due(db: Session, shift: Shift, events: list[StaffingEvent]) -> bool:
    """The window is open, long enough, and no case of the shift is still running (Q43)."""
    if not events:
        return False
    opened_at = min(event.occurred_at for event in events)
    if opened_at + timedelta(seconds=shift.merge_window_seconds) > clock.now():
        return False
    running_case = db.scalar(
        select(StaffingCase.id)
        .where(
            StaffingCase.shift_id == shift.id,
            StaffingCase.status.not_in(AUTOMATION_STOPPED_STATUSES),
        )
        .limit(1)
    )
    return running_case is None


def _check_threshold(db: Session, shift: Shift, policy: HardConstraintPolicy) -> ThresholdResult:
    """The threshold of the shift as it is now, after the events applied so far."""
    # The event just applied changed the roster, the patient count or the requirement
    db.flush()
    shift_requirement = requirement_service.get_current_requirement(db, shift.id)
    return check_threshold(
        patient_count=shift.patient_count,
        patients_per_nurse=policy.maximum_patients_per_nurse,
        required_roles=shift_requirement.required_roles,
        required_skills=shift_requirement.required_skills,
        roster=gap_service.load_roster(db, shift.id),
    )


def _ignore(
    db: Session,
    event: StaffingEvent,
    *,
    now: datetime,
    actor_id: int,
    reason: EventIgnoredReason,
) -> None:
    event.status = EventStatus.IGNORED
    event.processed_at = now
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=actor_id,
        action=AuditAction.EVENT_IGNORED,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=event.id,
        payload={"event_id": event.id, "shift_id": event.shift_id, "reason": reason.value},
    )


# --------------------------------------------------------------------------- #
# The tables each event type updates (section 3.4)
# --------------------------------------------------------------------------- #
def _apply(db: Session, shift: Shift, event: StaffingEvent) -> bool:
    """Update the tables of one event and write its audit row.

    Raises _NotApplicableError before the first write when it cannot. Returns
    whether the event counts for the threshold: False for a history-only event
    (a NO_SHOW of a shift that has ended), which can never open a case alone.
    """
    if event.event_type is EventType.STAFF_UNAVAILABLE:
        if event.payload.get("reason") == NO_SHOW_REASON:
            return _apply_no_show(db, shift, event)
        _apply_leave(db, shift, event)
    elif event.event_type is EventType.ASSIGNMENT_CANCELLED:
        _apply_cancellation(db, event)
    elif event.event_type is EventType.PATIENT_SURGE:
        _apply_patient_count(db, shift, event)
    elif event.event_type is EventType.REQUIREMENT_CHANGED:
        _apply_requirement(db, shift, event)
    else:
        raise ValueError(f"No rule for event type {event.event_type!r}")
    return True


def _assigned_roster(db: Session, event: StaffingEvent) -> RosterAssignment:
    """The roster row of the event's person, locked after the shift (section 6.11)."""
    assert event.staff_id is not None  # staff-group events always have one
    try:
        # COMPLETED too: the job may have completed the row after the event was
        # accepted, and the accepted report must still apply (round 3 PR R)
        return unavailability_service.lock_assigned_roster(
            db,
            staff_id=event.staff_id,
            shift_id=event.shift_id,
            statuses=COVERING_ROSTER_STATUSES,
        )
    except NoAssignedRosterError as error:
        # A second report for the same person in one window: the first one
        # already cancelled the row
        raise _NotApplicableError(EventIgnoredReason.NO_ASSIGNED_ROSTER) from error


def _reporter_actor(db: Session, event: StaffingEvent) -> int:
    return actor_service.user_id(db, int(event.payload[REPORTED_BY]))


def _apply_leave(db: Session, shift: Shift, event: StaffingEvent) -> None:
    roster = _assigned_roster(db, event)
    end_at = event.payload.get("end_at")
    unavailability = unavailability_service.record_unplanned_leave(
        db,
        roster=roster,
        shift=shift,
        end_at=None if end_at is None else datetime.fromisoformat(end_at),
    )
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=actor_service.user_id(db, roster.staff_id),
        action=AuditAction.UNAVAILABILITY_CREATED,
        entity_type=EntityType.STAFF_UNAVAILABILITY,
        entity_id=unavailability.id,
        payload={
            "unavailability_id": unavailability.id,
            "staff_id": roster.staff_id,
            "reason": unavailability.reason.value,
            "start_at": iso(unavailability.start_at),
            "end_at": iso(unavailability.end_at) if unavailability.end_at else None,
        },
    )


def _apply_no_show(db: Session, shift: Shift, event: StaffingEvent) -> bool:
    """Stage 2 of NO_SHOW (workflow.md 6.24): record the absence and cancel the row.

    The row is the one stage 1 named in the payload, locked after the shift. A
    row that ended while the event waited is not skipped: the history is still
    written. Returns whether the shift is still running, i.e. whether this event
    can count for a case.
    """
    roster = db.scalar(
        select(RosterAssignment)
        .where(RosterAssignment.id == int(event.payload["roster_assignment_id"]))
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if (
        roster is None
        or roster.status not in COVERING_ROSTER_STATUSES
        # The person was moved out of this row while the event waited
        or db.scalar(
            select(exists().where(RosterAssignment.transferred_from_assignment_id == roster.id))
        )
    ):
        raise _NotApplicableError(EventIgnoredReason.NO_ASSIGNED_ROSTER)

    attendance = db.scalar(
        select(Attendance).where(
            Attendance.staff_id == roster.staff_id, Attendance.shift_id == shift.id
        )
    )
    end_at = attendance_service.effective_end_at(roster, shift)
    # The event was written after the deadline, so a check-in found now is late
    late_check_in_at = (
        attendance.check_in_at
        if attendance is not None and attendance.check_in_at < end_at
        else None
    )
    unavailability = StaffUnavailability(
        staff_id=roster.staff_id,
        start_at=attendance_service.required_arrival_at(roster, shift),
        end_at=end_at if late_check_in_at is None else late_check_in_at,
        reason=AvailabilityReason.NO_SHOW,
    )
    db.add(unavailability)
    roster.status = RosterStatus.CANCELLED
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        action=AuditAction.UNAVAILABILITY_CREATED,
        entity_type=EntityType.STAFF_UNAVAILABILITY,
        entity_id=unavailability.id,
        payload={
            "unavailability_id": unavailability.id,
            "staff_id": roster.staff_id,
            "reason": unavailability.reason.value,
            "start_at": iso(unavailability.start_at),
            "end_at": iso(unavailability.end_at) if unavailability.end_at else None,
        },
    )
    if late_check_in_at is not None:
        # No case runs while a window is due (_is_due), so nothing is surplus yet
        late_arrival_service.restore(db, original=roster, check_in_at=late_check_in_at)
    return shift.end_at > clock.now()


def _apply_cancellation(db: Session, event: StaffingEvent) -> None:
    roster = _assigned_roster(db, event)
    roster.status = RosterStatus.CANCELLED
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=_reporter_actor(db, event),
        action=AuditAction.ASSIGNMENT_CANCELLED,
        entity_type=EntityType.ROSTER_ASSIGNMENT,
        entity_id=roster.id,
        payload={
            "assignment_id": roster.id,
            "staff_id": roster.staff_id,
            "reason": event.payload["reason"],
        },
    )


def _apply_patient_count(db: Session, shift: Shift, event: StaffingEvent) -> None:
    """Set the total the event reported. The last event of a window wins."""
    old_count = shift.patient_count
    shift.patient_count = int(event.payload["patient_count"])
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=_reporter_actor(db, event),
        action=AuditAction.PATIENT_COUNT_UPDATED,
        entity_type=EntityType.SHIFT,
        entity_id=shift.id,
        payload={
            "shift_id": shift.id,
            "old_patient_count": old_count,
            "new_patient_count": shift.patient_count,
        },
    )


def _apply_requirement(db: Session, shift: Shift, event: StaffingEvent) -> None:
    """Update role and skill counts in the rows of the current requirement."""
    requirement = requirement_service.get_current_requirement(db, shift.id).requirement
    wanted_roles = {
        int(item["role_id"]): int(item["required_count"]) for item in _items(event, "roles")
    }
    wanted_skills = {
        int(item["skill_id"]): int(item["required_count"]) for item in _items(event, "skills")
    }
    role_rows = {
        row.role_id: row
        for row in db.scalars(
            select(StaffingRequirementRole).where(
                StaffingRequirementRole.staffing_requirement_id == requirement.id,
                StaffingRequirementRole.role_id.in_(wanted_roles),
            )
        )
    }
    skill_rows = {
        row.skill_id: row
        for row in db.scalars(
            select(StaffingRequirementSkill).where(
                StaffingRequirementSkill.staffing_requirement_id == requirement.id,
                StaffingRequirementSkill.skill_id.in_(wanted_skills),
            )
        )
    }
    if set(role_rows) != set(wanted_roles) or set(skill_rows) != set(wanted_skills):
        raise _NotApplicableError(EventIgnoredReason.REQUIREMENT_ITEM_NOT_FOUND)

    roles = []
    for role_id, count in sorted(wanted_roles.items()):
        roles.append(
            {
                "role_id": role_id,
                "old_required_count": role_rows[role_id].required_count,
                "new_required_count": count,
            }
        )
        role_rows[role_id].required_count = count
    skills = []
    for skill_id, count in sorted(wanted_skills.items()):
        skills.append(
            {
                "skill_id": skill_id,
                "old_required_count": skill_rows[skill_id].required_count,
                "new_required_count": count,
            }
        )
        skill_rows[skill_id].required_count = count
    db.flush()
    audit_service.log(
        db,
        case_id=None,
        event_id=event.id,
        actor_id=_reporter_actor(db, event),
        action=AuditAction.REQUIREMENT_UPDATED,
        entity_type=EntityType.STAFFING_REQUIREMENTS,
        entity_id=requirement.id,
        payload={"requirement_id": requirement.id, "roles": roles, "skills": skills},
    )


def _items(event: StaffingEvent, key: str) -> list[dict[str, Any]]:
    return list(event.payload.get(key) or [])
