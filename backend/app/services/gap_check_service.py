"""
Read-only gap check of any shift, before or without a case (docs/workflow.md 6.31, 9.8).

Round 6 PR F1. Every function here only reads: the gap comes from
`gap_service.assess_shift()`, never `record_gap()`, so looking at a shift writes no
STAFFING_GAP, event, audit row or case. The clock is the Backend Clock, the same
point the case page measures from, so a shift whose case was just assessed shows
the same slices as `GET /cases/{id}`.

Who sees what (R6-Q16 ก): a Supervisor sees every ward, anyone else only their
home ward. The dashboard uses the same rule.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import SUPERVISOR_ROLE
from app.db.models import (
    Attendance,
    Role,
    RosterAssignment,
    Shift,
    Skill,
    Staff,
    StaffingCase,
    StaffUnavailability,
    Ward,
)
from app.domain.enums import COVERING_ROSTER_STATUSES, TERMINAL_CASE_STATUSES
from app.domain.staffing.gap_calculator import CountGap, GapInterval
from app.schemas.case import GapCount, GapIntervalView, HeadcountCount
from app.schemas.gap_check import GapRosterEntry, GapShiftDetail, GapShiftSummary
from app.services import gap_service, roster_time_service


class WardNotVisibleError(PermissionError):
    """The caller may not look at this ward (403)."""


class ShiftNotFoundError(LookupError):
    """No shift with this ID (404)."""


@dataclass(frozen=True)
class WardScope:
    """The wards one demo user may see. `all_wards` is True for a Supervisor."""

    all_wards: bool
    ward_ids: tuple[int, ...]

    def sees(self, ward_id: int) -> bool:
        return self.all_wards or ward_id in self.ward_ids


def ward_scope(db: Session, staff: Staff) -> WardScope:
    """Supervisor: every active ward. Anyone else: their home ward only (R6-Q16 ก)."""
    role = db.scalar(select(Role.name).where(Role.id == staff.role_id))
    if role == SUPERVISOR_ROLE:
        ward_ids = db.scalars(
            select(Ward.id).where(Ward.is_active.is_(True)).order_by(Ward.id)
        ).all()
        return WardScope(all_wards=True, ward_ids=tuple(ward_ids))
    return WardScope(all_wards=False, ward_ids=(staff.home_ward_id,))


def running_case_ids(db: Session, shift_ids: list[int]) -> dict[int, int]:
    """The latest case of each shift that has not ended (MANUAL_HANDOFF still counts)."""
    if not shift_ids:
        return {}
    rows = db.execute(
        select(StaffingCase.shift_id, func.max(StaffingCase.id))
        .where(
            StaffingCase.shift_id.in_(shift_ids),
            StaffingCase.status.not_in(list(TERMINAL_CASE_STATUSES)),
        )
        .group_by(StaffingCase.shift_id)
    )
    return {shift_id: case_id for shift_id, case_id in rows}


def list_shifts(db: Session, scope: WardScope, *, ward_id: int, day: date) -> list[GapShiftSummary]:
    """Active shifts of the ward starting on `day` (Asia/Bangkok), each with its gap now."""
    if not scope.sees(ward_id):
        raise WardNotVisibleError(f"Ward {ward_id} is not visible to this user")
    start = datetime.combine(day, time(), tzinfo=clock.APP_TIMEZONE)
    with db.no_autoflush:
        shifts = db.scalars(
            select(Shift)
            .where(
                Shift.ward_id == ward_id,
                Shift.is_active.is_(True),
                Shift.start_at >= start,
                Shift.start_at < start + timedelta(days=1),
            )
            .order_by(Shift.start_at, Shift.id)
        ).all()
        cases = running_case_ids(db, [shift.id for shift in shifts])
        rostered = _rostered_counts(db, [shift.id for shift in shifts])
        result = []
        for shift in shifts:
            assessment = gap_service.assess_shift(db, shift)
            result.append(
                GapShiftSummary(
                    shift_id=shift.id,
                    ward_id=shift.ward_id,
                    start_at=shift.start_at,
                    end_at=shift.end_at,
                    required_staff=assessment.shift_requirement.requirement.required_staff,
                    rostered_count=rostered.get(shift.id, 0),
                    headcount_gap=assessment.result.headcount_gap,
                    case_id=cases.get(shift.id),
                )
            )
        return result


def _rostered_counts(db: Session, shift_ids: list[int]) -> dict[int, int]:
    """People on each shift's roster who cover it (ASSIGNED or COMPLETED), whole or part."""
    if not shift_ids:
        return {}
    rows = db.execute(
        select(RosterAssignment.shift_id, func.count(func.distinct(RosterAssignment.staff_id)))
        .where(
            RosterAssignment.shift_id.in_(shift_ids),
            RosterAssignment.status.in_(list(COVERING_ROSTER_STATUSES)),
        )
        .group_by(RosterAssignment.shift_id)
    )
    return {shift_id: count for shift_id, count in rows}


def shift_detail(db: Session, scope: WardScope, shift_id: int) -> GapShiftDetail:
    """The gap of one shift by time slice, with its roster. 404 before 403."""
    with db.no_autoflush:
        shift = db.get(Shift, shift_id)
        if shift is None:
            raise ShiftNotFoundError(f"No shift {shift_id}")
        if not scope.sees(shift.ward_id):
            raise WardNotVisibleError(f"Ward {shift.ward_id} is not visible to this user")
        result = gap_service.assess_shift(db, shift).result
        names = _names(db, result.intervals)
        return GapShiftDetail(
            shift_id=shift.id,
            ward_id=shift.ward_id,
            start_at=shift.start_at,
            end_at=shift.end_at,
            evaluated_from=result.evaluated_from,
            intervals=[interval_view(interval, names) for interval in result.intervals],
            roster=_roster(db, shift),
            case_id=running_case_ids(db, [shift.id]).get(shift.id),
        )


@dataclass(frozen=True)
class Names:
    roles: dict[int, str]
    skills: dict[int, str]


def _names(db: Session, intervals: tuple[GapInterval, ...]) -> Names:
    role_ids = {role_id for interval in intervals for role_id in interval.role_gaps}
    skill_ids = {skill_id for interval in intervals for skill_id in interval.skill_gaps}
    return names_of(db, role_ids, skill_ids)


def names_of(db: Session, role_ids: set[int], skill_ids: set[int]) -> Names:
    roles: dict[int, str] = {}
    if role_ids:
        roles = {
            role_id: name
            for role_id, name in db.execute(select(Role.id, Role.name).where(Role.id.in_(role_ids)))
        }
    skills: dict[int, str] = {}
    if skill_ids:
        skills = {
            skill_id: name
            for skill_id, name in db.execute(
                select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids))
            )
        }
    return Names(roles=roles, skills=skills)


def interval_view(interval: GapInterval, names: Names) -> GapIntervalView:
    """One slice in the shape of `gap.intervals` of GET /cases/{id}, roles and skills by ID."""
    return GapIntervalView(
        start_at=interval.start_at,
        end_at=interval.end_at,
        headcount=HeadcountCount(
            required_count=interval.headcount.required_count,
            current_count=interval.headcount.current_count,
            gap_count=interval.headcount.gap_count,
        ),
        roles=_counts(interval.role_gaps, names.roles),
        skills=_counts(interval.skill_gaps, names.skills),
    )


def _counts(gaps: Mapping[int, CountGap], names: dict[int, str]) -> list[GapCount]:
    return [
        GapCount(
            id=item_id,
            name=names[item_id],
            required_count=count.required_count,
            current_count=count.current_count,
            gap_count=count.gap_count,
        )
        for item_id, count in sorted(gaps.items())
    ]


def _roster(db: Session, shift: Shift) -> list[GapRosterEntry]:
    """Every roster row of the shift, cancelled ones too, with leave and check-in flags.

    on_leave: an unavailability period of the person overlaps the shift. checked_in: the
    person has a check-in for this shift.
    """
    on_leave = exists().where(
        StaffUnavailability.staff_id == RosterAssignment.staff_id,
        StaffUnavailability.start_at < Shift.end_at,
        (StaffUnavailability.end_at.is_(None)) | (StaffUnavailability.end_at > Shift.start_at),
    )
    checked_in = exists().where(
        Attendance.staff_id == RosterAssignment.staff_id,
        Attendance.shift_id == RosterAssignment.shift_id,
    )
    rows = db.execute(
        select(
            RosterAssignment.id,
            RosterAssignment.staff_id,
            Staff.first_name,
            Staff.last_name,
            RosterAssignment.status,
            roster_time_service.start_at(),
            roster_time_service.end_at(),
            on_leave,
            checked_in,
        )
        .join(Staff, Staff.id == RosterAssignment.staff_id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(RosterAssignment.shift_id == shift.id)
        .order_by(RosterAssignment.staff_id, RosterAssignment.id)
    )
    return [
        GapRosterEntry(
            roster_assignment_id=row_id,
            staff_id=staff_id,
            name=f"{first_name} {last_name}",
            status=status,
            effective_start_at=start_at,
            effective_end_at=end_at,
            on_leave=leave,
            checked_in=checked,
        )
        for (
            row_id,
            staff_id,
            first_name,
            last_name,
            status,
            start_at,
            end_at,
            leave,
            checked,
        ) in rows
    ]
