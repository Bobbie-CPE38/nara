"""Immutable database snapshots, in the assignment transaction; no network or commits."""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.core.constants import HANDOVER_CONTENT_VERSION, MAX_BIGINT
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
from app.schemas.handover import HandoverPage, HandoverView
from app.services import audit_service, requirement_service, roster_time_service


class InvalidCursorError(ValueError):
    """An invalid history cursor supplied by the caller."""


class HandoverProvenanceError(ValueError):
    """The case's opening event is missing or inconsistent; do not guess a reason."""


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
        raise HandoverProvenanceError(f"Case {case.id} has no valid opening event")
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
    # An event or a scheduled partial interval alone does not mean the person
    # actually left. Only the recorded transfer link proves this source was cut.
    replaced_staff = select(StaffingEvent.staff_id).where(
        StaffingEvent.case_id == case.id,
        StaffingEvent.event_type.in_((EventType.STAFF_UNAVAILABLE, EventType.ASSIGNMENT_CANCELLED)),
        StaffingEvent.staff_id.is_not(None),
    )
    destination = aliased(RosterAssignment)
    transferred = (
        select(destination.id)
        .where(destination.transferred_from_assignment_id == RosterAssignment.id)
        .correlate(RosterAssignment)
        .exists()
    )
    for person, role_name in db.execute(
        select(Staff, Role.name)
        .join(Role, Role.id == Staff.role_id)
        .join(RosterAssignment, RosterAssignment.staff_id == Staff.id)
        .where(
            RosterAssignment.shift_id == shift.id,
            RosterAssignment.status.in_((RosterStatus.ASSIGNED, RosterStatus.COMPLETED)),
            RosterAssignment.staff_id != row.staff_id,
            or_(
                RosterAssignment.staff_id.not_in(replaced_staff),
                ~transferred,
            ),
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
    from app.core.config import settings
    from app.services import line_delivery_service

    handover = db.get_one(StructuredHandover, handover_id)
    if settings.real_line_enabled:
        line_delivery_service.prepare_handover_delivery(db, handover)
    return handover


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


def _history_cursor(staff_id: int, row: HandoverView) -> str:
    payload = {"v": 1, "staff": staff_id, "at": row.generated_at.isoformat(), "id": row.handover_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _read_history_cursor(cursor: str, staff_id: int) -> tuple[datetime, int]:
    try:
        payload = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != {"v", "staff", "at", "id"}:
            raise ValueError
        if type(payload["v"]) is not int or payload["v"] != 1 or payload["staff"] != staff_id:
            raise ValueError
        oid = payload["id"]
        if type(oid) is not int or not 1 <= oid <= MAX_BIGINT:
            raise ValueError
        at = datetime.fromisoformat(payload["at"])
        if at.utcoffset() is None:
            raise ValueError
        # Normalize here: extreme offsets can overflow Python/driver UTC conversion.
        at = at.astimezone(UTC)
        return at, oid
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        binascii.Error,
        UnicodeDecodeError,
    ) as error:
        raise InvalidCursorError("Invalid handover history cursor") from error


def page_handovers(
    db: Session, *, staff_id: int, limit: int = 20, cursor: str | None = None
) -> HandoverPage:
    """Always return current assignments; keyset-page only history. No writes.

    Generated time and ID are immutable; status is read anew on every request.
    Case detail keeps its existing complete list through list_handovers().
    """
    if not 1 <= limit <= 100:
        raise ValueError("Handover history limit must be between 1 and 100")
    boundary = _read_history_cursor(cursor, staff_id) if cursor is not None else None
    active = and_(
        RosterAssignment.status == RosterStatus.ASSIGNED,
        roster_time_service.end_at() > clock.now(),
    )
    query = (
        select(StructuredHandover, active.label("active"))
        .join(RosterAssignment, RosterAssignment.id == StructuredHandover.roster_assignment_id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(StructuredHandover.incoming_staff_id == staff_id)
        .order_by(StructuredHandover.generated_at.desc(), StructuredHandover.id.desc())
    )

    def views(rows: Any) -> list[HandoverView]:
        return [
            HandoverView(
                handover_id=h.id,
                roster_assignment_id=h.roster_assignment_id,
                active=is_active,
                generated_at=h.generated_at,
                content=h.content,
            )
            for h, is_active in rows
        ]

    with db.no_autoflush:
        current = views(db.execute(query.where(active)))
        history_query = query.where(~active)
        if boundary is not None:
            at, oid = boundary
            history_query = history_query.where(
                or_(
                    StructuredHandover.generated_at < at,
                    and_(StructuredHandover.generated_at == at, StructuredHandover.id < oid),
                )
            )
        history = views(db.execute(history_query.limit(limit + 1)))
    more = len(history) > limit
    history = history[:limit]
    return HandoverPage(
        active=current,
        history=history,
        next_cursor=_history_cursor(staff_id, history[-1]) if more else None,
    )
