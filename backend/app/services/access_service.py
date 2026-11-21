"""Which cases, events, wards and rosters a signed-in user may read (docs/workflow.md 6.33.4).

Round 6 PR AU2. The routes ask this module in AUTH_MODE=session only: demo mode keeps the
reads of section 9 (anonymous case reads, any roster). Every scope comes from the
database, never from the client:

  supervisor  every ward and every case
  head_nurse  their home ward, plus a case whose two-ward approval request has its
              SOURCE side in their ward (6.21): they decide that side, so they read it
  staff       only the cases they are part of: an event about them (their leave, their
              no-show), or a roster row the case gave them (an approved offer, a move or
              a manual assignment). An offer alone is not enough (round 6 PR EV8). Their
              roster is the shifts they are on, with everyone on those shifts; no gaps

Lists and counts take `case_condition()` into their own query, so rows a user may not
see are never loaded and then hidden.
"""

from dataclasses import dataclass

from sqlalchemy import ColumnElement, exists, false, or_, select, true
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    ManualAssignment,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
)
from app.services.auth_service import API_ROLES, ApiRole


@dataclass(frozen=True)
class Viewer:
    """The signed-in user as this module needs them."""

    staff_id: int
    home_ward_id: int
    role: ApiRole


def viewer(db: Session, staff: Staff, role: ApiRole | None = None) -> Viewer:
    """`role` from the session when it has one; a role outside API_ROLES gets least rights."""
    if role is None:
        name = db.scalar(select(Role.name).where(Role.id == staff.role_id))
        role = API_ROLES.get(name or "", "staff")
    return Viewer(staff_id=staff.id, home_ward_id=staff.home_ward_id, role=role)


def sees_ward(viewer: Viewer, ward_id: int) -> bool:
    return viewer.role == "supervisor" or ward_id == viewer.home_ward_id


def case_condition(viewer: Viewer) -> ColumnElement[bool]:
    """The STAFFING_CASES rows this viewer may read. The query must join SHIFT on
    StaffingCase.shift_id (the ward of a case is the ward of its shift)."""
    if viewer.role == "supervisor":
        return true()
    if viewer.role == "head_nurse":
        return or_(Shift.ward_id == viewer.home_ward_id, _source_side_in(viewer.home_ward_id))
    return _part_of(viewer.staff_id)


def _source_side_in(ward_id: int) -> ColumnElement[bool]:
    """A request of the case moves someone out of `ward_id`: that ward decides its SOURCE side."""
    source = aliased(RosterAssignment)
    source_shift = aliased(Shift)
    return exists(
        select(ApprovalRequest.id)
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(source, source.id == CandidateItem.source_assignment_id)
        .join(source_shift, source_shift.id == source.shift_id)
        .where(ApprovalRequest.case_id == StaffingCase.id, source_shift.ward_id == ward_id)
    )


def _part_of(staff_id: int) -> ColumnElement[bool]:
    """The case is about them (an event of theirs), or the case put them on a shift: an
    approved request with their roster row on the proposed shift (a replacement or a move,
    kept as history when the row ends later), or a manual assignment. Round 6 PR EV8: an
    offer they were sent, or answered, is no longer enough."""
    approved = exists(
        select(ApprovalRequest.id)
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(
            RosterAssignment,
            (RosterAssignment.staff_id == CandidateItem.staff_id)
            & (RosterAssignment.shift_id == CandidateItem.proposed_shift_id),
        )
        .where(
            ApprovalRequest.case_id == StaffingCase.id,
            ApprovalRequest.is_approved.is_(True),
            CandidateItem.staff_id == staff_id,
        )
    )
    reported = exists(
        select(StaffingEvent.id).where(
            StaffingEvent.case_id == StaffingCase.id, StaffingEvent.staff_id == staff_id
        )
    )
    assigned = exists(
        select(ManualAssignment.id)
        .join(RosterAssignment, RosterAssignment.id == ManualAssignment.roster_assignment_id)
        .where(ManualAssignment.case_id == StaffingCase.id, RosterAssignment.staff_id == staff_id)
    )
    return or_(reported, approved, assigned)


def approval_request_condition(viewer: Viewer | None) -> ColumnElement[bool]:
    """The pending approval REQUESTS this viewer may read, one by one (not by case).

    Reading a case is wider: a source head nurse reads the whole case when one of its requests
    moves someone out of their ward. Their queue of approvals is only the requests that have a
    side in their ward, as destination or as source, so another request of the same case that
    involves other wards stays out of it. The query must join CANDIDATE_ITEMS. A supervisor, and
    no viewer (demo mode), is not limited; a nurse has no approval queue (the route refuses).
    """
    if viewer is None or viewer.role == "supervisor":
        return true()
    if viewer.role != "head_nurse":
        return false()
    ward_shift = aliased(Shift)
    source_row = aliased(RosterAssignment)
    source_shift = aliased(Shift)
    destination = CandidateItem.proposed_shift_id.in_(
        select(ward_shift.id).where(ward_shift.ward_id == viewer.home_ward_id)
    )
    source = CandidateItem.source_assignment_id.in_(
        select(source_row.id)
        .join(source_shift, source_shift.id == source_row.shift_id)
        .where(source_shift.ward_id == viewer.home_ward_id)
    )
    return or_(destination, source)


def sees_case(db: Session, viewer: Viewer, case_id: int) -> bool:
    """One query for "it exists" and "this viewer may read it". False for both an unknown case
    and one that is not theirs, so a user cannot tell which IDs exist (6.33.4)."""
    return (
        db.scalar(
            select(StaffingCase.id)
            .join(Shift, Shift.id == StaffingCase.shift_id)
            .where(StaffingCase.id == case_id, case_condition(viewer))
        )
        is not None
    )


def event_condition(viewer: Viewer) -> ColumnElement[bool]:
    """The STAFFING_EVENTS rows this viewer may read: their own, those of a case they may read,
    and for a head nurse those of a shift of their ward that has no case yet (6.33.4)."""
    if viewer.role == "supervisor":
        return true()
    readable_case = StaffingEvent.case_id.in_(
        select(StaffingCase.id)
        .join(Shift, Shift.id == StaffingCase.shift_id)
        .where(case_condition(viewer))
    )
    conditions = [StaffingEvent.staff_id == viewer.staff_id, readable_case]
    if viewer.role == "head_nurse":
        conditions.append(
            StaffingEvent.shift_id.in_(select(Shift.id).where(Shift.ward_id == viewer.home_ward_id))
        )
    return or_(*conditions)


def sees_event(db: Session, viewer: Viewer, event_id: int) -> bool:
    """One query for "the event exists" and "this viewer may read it" (False for both)."""
    return (
        db.scalar(
            select(StaffingEvent.id).where(StaffingEvent.id == event_id, event_condition(viewer))
        )
        is not None
    )


def roster_shift_condition(viewer: Viewer) -> ColumnElement[bool]:
    """SHIFT rows whose roster this viewer reads when it is not their own row. A nurse has
    none: they read only their own roster (round 6 PR EV8)."""
    if viewer.role == "supervisor":
        return true()
    if viewer.role == "staff":
        return false()
    return Shift.ward_id == viewer.home_ward_id


def sees_shift_roster(db: Session, viewer: Viewer, shift_id: int, ward_id: int) -> bool:
    """The whole roster of one shift: a manager's ward, or for a nurse a shift they are on
    (a roster row of theirs in any status, so a shift they left or were moved from stays
    readable). Round 6 PR EV8."""
    if viewer.role != "staff":
        return sees_ward(viewer, ward_id)
    return (
        db.scalar(
            select(RosterAssignment.id)
            .where(
                RosterAssignment.shift_id == shift_id,
                RosterAssignment.staff_id == viewer.staff_id,
            )
            .limit(1)
        )
        is not None
    )


def sees_staff_roster(db: Session, viewer: Viewer, staff_id: int) -> bool | None:
    """Someone else's roster: their home ward must be visible, and a nurse reads only their
    own (round 6 PR EV8). None for unknown staff."""
    if staff_id == viewer.staff_id:
        return True
    if viewer.role == "staff":
        return False
    home_ward_id = db.scalar(select(Staff.home_ward_id).where(Staff.id == staff_id))
    if home_ward_id is None:
        return None
    return sees_ward(viewer, home_ward_id)
