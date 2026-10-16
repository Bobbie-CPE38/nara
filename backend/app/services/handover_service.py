"""Immutable database snapshots, in the assignment transaction; no LINE or commits."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HANDOVER_CONTENT_VERSION
from app.db.models import (
    AuditLog,
    Role,
    RosterAssignment,
    Shift,
    Skill,
    Staff,
    StaffingCase,
    StaffingEvent,
    StructuredHandover,
    Ward,
)
from app.domain.enums import (
    AssignmentType,
    AuditAction,
    EntityType,
    EventType,
    HandoverReason,
    RosterStatus,
)
from app.schemas.handover import HandoverView
from app.services import audit_service, requirement_service, roster_time_service


def case_reason(db: Session, case: StaffingCase) -> HandoverReason:
    """Use the threshold-passing event recorded by CASE_OPENED, never guess."""
    opened = db.scalar(
        select(AuditLog)
        .where(AuditLog.case_id == case.id, AuditLog.action == AuditAction.CASE_OPENED)
        .order_by(AuditLog.id)
        .limit(1)
    )
    event_id = opened.payload.get("event_id") if opened is not None else None
    event = db.get(StaffingEvent, event_id) if type(event_id) is int else None
    if event is None or event.case_id != case.id or event.shift_id != case.shift_id:
        raise ValueError(f"Case {case.id} has no valid opening event")
    if event.event_type == EventType.STAFF_UNAVAILABLE:
        return (
            HandoverReason.NO_SHOW
            if (event.payload or {}).get("reason") == "NO_SHOW"
            else HandoverReason.UNPLANNED_LEAVE
        )
    return HandoverReason(event.event_type.value)


def _content(db: Session, case: StaffingCase, row: RosterAssignment) -> dict[str, Any]:
    shift = db.get(Shift, row.shift_id)
    if shift is None or shift.id != case.shift_id:
        raise ValueError("Handover assignment must belong to the case's shift")
    ward = db.get(Ward, shift.ward_id)
    if ward is None:
        raise LookupError(f"No ward {shift.ward_id}")
    start, end = roster_time_service.effective_interval(
        shift_start_at=shift.start_at,
        shift_end_at=shift.end_at,
        actual_start_at=row.actual_start_at,
        actual_end_at=row.actual_end_at,
    )
    requirement = requirement_service.get_current_requirement(db, shift.id)
    roles = [
        dict(role_id=id, name=name, required_count=requirement.required_roles[id])
        for id, name in db.execute(
            select(Role.id, Role.name)
            .where(Role.id.in_(requirement.required_roles))
            .order_by(Role.id)
        )
    ]
    skills = [
        dict(skill_id=id, name=name, required_count=requirement.required_skills[id])
        for id, name in db.execute(
            select(Skill.id, Skill.name)
            .where(Skill.id.in_(requirement.required_skills))
            .order_by(Skill.id)
        )
    ]
    coworkers = {}
    for person, role_name in db.execute(
        select(Staff, Role.name)
        .join(Role, Role.id == Staff.role_id)
        .join(RosterAssignment, RosterAssignment.staff_id == Staff.id)
        .where(
            RosterAssignment.shift_id == shift.id,
            RosterAssignment.status.in_((RosterStatus.ASSIGNED, RosterStatus.COMPLETED)),
            RosterAssignment.staff_id != row.staff_id,
            roster_time_service.start_at() < end,
            roster_time_service.end_at() > start,
        )
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .order_by(Staff.id)
    ):
        coworkers[person.id] = dict(
            staff_id=person.id, name=f"{person.first_name} {person.last_name}", role_name=role_name
        )
    return dict(
        version=HANDOVER_CONTENT_VERSION,
        shift=dict(
            id=shift.id,
            ward_id=ward.id,
            ward_name=ward.name,
            start_at=shift.start_at.astimezone(clock.APP_TIMEZONE).isoformat(),
            end_at=shift.end_at.astimezone(clock.APP_TIMEZONE).isoformat(),
        ),
        cover_start_at=start.astimezone(clock.APP_TIMEZONE).isoformat(),
        cover_end_at=end.astimezone(clock.APP_TIMEZONE).isoformat(),
        reason=case_reason(db, case).value,
        patient_count=shift.patient_count,
        requirement=dict(roles=roles, skills=skills),
        co_workers=list(coworkers.values()),
        case_id=case.id,
    )


def ensure(
    db: Session, *, case: StaffingCase, assignment: RosterAssignment, actor_id: int
) -> StructuredHandover:
    """One snapshot and audit per roster row, including concurrent callers.

    Caller owns assignment locks and the transaction. The unique constraint is
    the final arbiter; ON CONFLICT avoids rolling back any of the caller's work.
    """
    db.flush()
    if (
        assignment.assignment_type != AssignmentType.REPLACEMENT
        or assignment.shift_id != case.shift_id
    ):
        raise ValueError("Handover requires a replacement on this case's shift")
    existing = db.scalar(
        select(StructuredHandover).where(StructuredHandover.roster_assignment_id == assignment.id)
    )
    if existing is not None:
        if existing.case_id != case.id or existing.incoming_staff_id != assignment.staff_id:
            raise ValueError("Handover ownership mismatch")
        return existing
    handover_id = db.scalar(
        insert(StructuredHandover)
        .values(
            case_id=case.id,
            shift_id=assignment.shift_id,
            incoming_staff_id=assignment.staff_id,
            roster_assignment_id=assignment.id,
            content=_content(db, case, assignment),
            generated_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=[StructuredHandover.roster_assignment_id])
        .returning(StructuredHandover.id)
    )
    if handover_id is None:
        existing = db.scalars(
            select(StructuredHandover).where(
                StructuredHandover.roster_assignment_id == assignment.id
            )
        ).one()
        if existing.case_id != case.id or existing.incoming_staff_id != assignment.staff_id:
            raise ValueError("Handover ownership mismatch")
        return existing
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.HANDOVER_GENERATED,
        entity_type=EntityType.STRUCTURED_HANDOVER,
        entity_id=handover_id,
        payload=dict(
            handover_id=handover_id,
            roster_assignment_id=assignment.id,
            staff_id=assignment.staff_id,
            shift_id=assignment.shift_id,
            case_id=case.id,
        ),
    )
    return db.get_one(StructuredHandover, handover_id)


def list_handovers(
    db: Session, *, staff_id: int | None = None, case_id: int | None = None
) -> list[HandoverView]:
    """Current first, then history, newest first within each group. Read-only."""
    query = (
        select(StructuredHandover, RosterAssignment.status, roster_time_service.end_at())
        .join(RosterAssignment, RosterAssignment.id == StructuredHandover.roster_assignment_id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
    )
    if staff_id is not None:
        query = query.where(StructuredHandover.incoming_staff_id == staff_id)
    if case_id is not None:
        query = query.where(StructuredHandover.case_id == case_id)
    now = clock.now()
    rows = [
        HandoverView(
            handover_id=h.id,
            roster_assignment_id=h.roster_assignment_id,
            active=status == RosterStatus.ASSIGNED and now < end,
            generated_at=h.generated_at,
            content=h.content,
        )
        for h, status, end in db.execute(query)
    ]
    return sorted(rows, key=lambda h: (h.active, h.generated_at, h.handover_id), reverse=True)
