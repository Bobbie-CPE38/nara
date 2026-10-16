"""
Gap assessment of one shift from the database (docs/workflow.md, sections 3 and 8).

Loads what `domain.staffing.gap_calculator` needs and runs it. Event intake
uses the result to decide between IGNORED and a new case. The ASSESSING step
uses the same function, so both always agree.

`assess_shift()` only reads. The ASSESSING step stores its result with
`record_gap()`; event intake never does, because an ignored event has no case.

Round 4 PR T3: the gap is measured from max(Backend Clock, shift start) to the
shift end, per time slice, with each roster row counted only inside its actual
interval (workflow.md 6.20). `get_case_gap()` returns those slices for deciding,
from the same point on: time that has passed is never refilled (round 4 PR C3).
"""

from dataclasses import dataclass, field, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingGap,
    StaffingGapInterval,
    StaffingGapRole,
    StaffingGapRoleInterval,
    StaffingGapSkill,
    StaffingGapSkillInterval,
    StaffSkill,
)
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import GapResult, calculate_gap, effective_minimum_for
from app.domain.workflow.case_status import IntervalGap, remaining_intervals
from app.services import policy_service, requirement_service, roster_time_service
from app.services.requirement_service import ShiftRequirement


@dataclass(frozen=True)
class ShiftAssessment:
    """The gap of a shift together with the inputs it was computed from."""

    shift_requirement: ShiftRequirement
    result: GapResult


class GapNotFoundError(LookupError):
    """The case has no STAFFING_GAP row. A case past ASSESSING always has one."""


@dataclass(frozen=True)
class CaseGap:
    """What a case has to fill, read from its latest STAFFING_GAP.

    role_gaps and skill_gaps hold only the roles and skills that are short
    (gap_count > 0), keyed by ID. A case with both empty is short on headcount only.
    """

    gap: StaffingGap
    role_gaps: dict[int, int]
    skill_gaps: dict[int, int]
    # What each time slice misses from now on, in time order. The only input for
    # deciding whether the gap is closed: the summary counts are for display (6.20).
    # A gap written before round 4 is one whole-shift slice with its counts
    intervals: tuple[IntervalGap, ...] = field(default=())

    @property
    def headcount_gap(self) -> int:
        return self.gap.headcount_gap


def assess_shift(db: Session, shift: Shift) -> ShiftAssessment:
    """Compare the shift's current roster with its headcount and role/skill requirement.

    The headcount target comes from required_staff and minimum_staff of the
    current requirement and the preserve_minimum_staffing flag of the hard policy.
    """
    # The caller may have just cancelled a roster row. SessionLocal has
    # autoflush off, so send that change before the roster is read back
    db.flush()

    shift_requirement = requirement_service.get_current_requirement(db, shift.id)
    policy = policy_service.get_hard_constraint_policy(db)
    window = (_evaluated_from(shift.start_at, shift.end_at), shift.end_at)
    result = calculate_gap(
        shift_id=shift.id,
        required_staff=shift_requirement.requirement.required_staff,
        minimum_staff=shift_requirement.requirement.minimum_staff,
        preserve_minimum_staffing=policy.preserve_minimum_staffing,
        required_roles=shift_requirement.required_roles,
        required_skills=shift_requirement.required_skills,
        roster=load_roster(db, shift.id),
        window=window,
    )
    return ShiftAssessment(shift_requirement=shift_requirement, result=result)


def _evaluated_from(start_at: datetime, end_at: datetime) -> datetime:
    """Where a gap of the shift starts to count: max(Backend Clock, shift start).

    Past time is never refilled: measure from now once the shift has started.
    A shift with no time left keeps the whole-shift measure it had before
    round 4 (a window can close after the shift ended, round 3 PR R).
    """
    evaluated_from = max(clock.now(), start_at)
    return start_at if evaluated_from >= end_at else evaluated_from


def gap_without(db: Session, *, shift: Shift, staff_id: int, from_at: datetime) -> GapResult:
    """The gap of `shift` if `staff_id` leaves it at `from_at`. Read-only.

    Same calculator and requirement as assess_shift, so the source shift of a move
    is judged exactly like a case (workflow.md 6.19). The person's rows end at
    `from_at` (rows starting at or after it are dropped). The window runs from
    max(from_at, Backend Clock) to the shift end; with no time left in it there is
    nothing to miss, so the result has no gap.
    """
    shift_requirement = requirement_service.get_current_requirement(db, shift.id)
    requirement = shift_requirement.requirement
    preserve_minimum_staffing = policy_service.get_hard_constraint_policy(
        db
    ).preserve_minimum_staffing
    evaluated_from = max(from_at, clock.now())
    if evaluated_from >= shift.end_at:
        return GapResult(
            effective_minimum=effective_minimum_for(
                required_staff=requirement.required_staff,
                minimum_staff=requirement.minimum_staff,
                preserve_minimum_staffing=preserve_minimum_staffing,
            ),
            headcount_gap=0,
            role_gaps={},
            skill_gaps={},
            evaluated_from=evaluated_from,
        )
    roster: list[RosterMember] = []
    for member in load_roster(db, shift.id):
        if member.staff_id == staff_id:
            if member.start_at is not None and from_at <= member.start_at:
                continue
            if member.end_at is None or member.end_at > from_at:
                member = replace(member, end_at=from_at)
        roster.append(member)
    return calculate_gap(
        shift_id=shift.id,
        required_staff=requirement.required_staff,
        minimum_staff=requirement.minimum_staff,
        preserve_minimum_staffing=preserve_minimum_staffing,
        required_roles=shift_requirement.required_roles,
        required_skills=shift_requirement.required_skills,
        roster=roster,
        window=(evaluated_from, shift.end_at),
    )


def record_gap(db: Session, case: StaffingCase, assessment: ShiftAssessment) -> StaffingGap:
    """Store one assessment as the STAFFING_GAP of a case; flush but never commit.

    effective_minimum is the target the calculator used, not a fresh read of the
    requirement or the policy. Every required role and skill gets a row, also the
    ones without a shortage.
    """
    result = assessment.result
    gap = StaffingGap(
        case_id=case.id,
        staffing_requirement_id=assessment.shift_requirement.requirement.id,
        headcount_gap=result.headcount_gap,
        effective_minimum=result.effective_minimum,
        computed_at=clock.now(),
        evaluated_from=result.evaluated_from,
    )
    db.add(gap)
    # The role and skill rows need the gap id
    db.flush()
    db.add_all(
        StaffingGapRole(
            gap_id=gap.id,
            role_id=role_id,
            required_count=count.required_count,
            current_count=count.current_count,
            gap_count=count.gap_count,
        )
        for role_id, count in result.role_gaps.items()
    )
    db.add_all(
        StaffingGapSkill(
            gap_id=gap.id,
            skill_id=skill_id,
            required_count=count.required_count,
            current_count=count.current_count,
            gap_count=count.gap_count,
        )
        for skill_id, count in result.skill_gaps.items()
    )
    for interval in result.intervals:
        db.add(
            StaffingGapInterval(
                gap_id=gap.id,
                start_at=interval.start_at,
                end_at=interval.end_at,
                required_count=interval.headcount.required_count,
                current_count=interval.headcount.current_count,
                gap_count=interval.headcount.gap_count,
            )
        )
        db.add_all(
            StaffingGapRoleInterval(
                gap_id=gap.id,
                role_id=role_id,
                start_at=interval.start_at,
                end_at=interval.end_at,
                required_count=count.required_count,
                current_count=count.current_count,
                gap_count=count.gap_count,
            )
            for role_id, count in interval.role_gaps.items()
        )
        db.add_all(
            StaffingGapSkillInterval(
                gap_id=gap.id,
                skill_id=skill_id,
                start_at=interval.start_at,
                end_at=interval.end_at,
                required_count=count.required_count,
                current_count=count.current_count,
                gap_count=count.gap_count,
            )
            for skill_id, count in interval.skill_gaps.items()
        )
    db.flush()
    return gap


def get_case_gap(db: Session, case_id: int) -> CaseGap:
    """Return the latest gap of a case with its short roles and skills. Read-only.

    The one loader for the Solver and Safety (workflow.md section 6.4, seam 11).
    "Latest" is the highest id. Raises GapNotFoundError when the case has no gap.

    The stored slices keep their counts (Q19), but `intervals` starts where
    assess_shift() would measure now (round 4 PR C3): the time before it has
    passed and cannot be filled, so a person who joined mid-shift, such as a
    nurse moved at the final approval, closes the gap from then on. The rows
    themselves are not changed.
    """
    gap = db.scalar(
        select(StaffingGap)
        .where(StaffingGap.case_id == case_id)
        .order_by(StaffingGap.id.desc())
        .limit(1)
    )
    if gap is None:
        raise GapNotFoundError(f"No staffing gap for case {case_id}")

    roles = db.execute(
        select(StaffingGapRole.role_id, StaffingGapRole.gap_count).where(
            StaffingGapRole.gap_id == gap.id, StaffingGapRole.gap_count > 0
        )
    )
    skills = db.execute(
        select(StaffingGapSkill.skill_id, StaffingGapSkill.gap_count).where(
            StaffingGapSkill.gap_id == gap.id, StaffingGapSkill.gap_count > 0
        )
    )
    role_gaps = {role_id: count for role_id, count in roles}
    skill_gaps = {skill_id: count for skill_id, count in skills}
    shift_start, shift_end = db.execute(
        select(Shift.start_at, Shift.end_at)
        .join(StaffingCase, StaffingCase.shift_id == Shift.id)
        .where(StaffingCase.id == gap.case_id)
    ).one()
    return CaseGap(
        gap=gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        intervals=remaining_intervals(
            _interval_gaps(db, gap, role_gaps, skill_gaps, (shift_start, shift_end)),
            _evaluated_from(shift_start, shift_end),
        ),
    )


def _interval_gaps(
    db: Session,
    gap: StaffingGap,
    role_gaps: dict[int, int],
    skill_gaps: dict[int, int],
    shift_window: tuple[datetime, datetime],
) -> tuple[IntervalGap, ...]:
    """The stored slices of a gap; a gap without slices is short for the whole shift."""
    slices = db.execute(
        select(
            StaffingGapInterval.start_at,
            StaffingGapInterval.end_at,
            StaffingGapInterval.gap_count,
        )
        .where(StaffingGapInterval.gap_id == gap.id)
        .order_by(StaffingGapInterval.start_at)
    ).all()
    if not slices:
        return (
            IntervalGap(
                start_at=shift_window[0],
                end_at=shift_window[1],
                headcount_gap=gap.headcount_gap,
                role_gaps=role_gaps,
                skill_gaps=skill_gaps,
            ),
        )
    roles: dict[datetime, dict[int, int]] = {}
    for start_at, role_id, count in db.execute(
        select(
            StaffingGapRoleInterval.start_at,
            StaffingGapRoleInterval.role_id,
            StaffingGapRoleInterval.gap_count,
        ).where(StaffingGapRoleInterval.gap_id == gap.id, StaffingGapRoleInterval.gap_count > 0)
    ):
        roles.setdefault(start_at, {})[role_id] = count
    skills: dict[datetime, dict[int, int]] = {}
    for start_at, skill_id, count in db.execute(
        select(
            StaffingGapSkillInterval.start_at,
            StaffingGapSkillInterval.skill_id,
            StaffingGapSkillInterval.gap_count,
        ).where(StaffingGapSkillInterval.gap_id == gap.id, StaffingGapSkillInterval.gap_count > 0)
    ):
        skills.setdefault(start_at, {})[skill_id] = count
    return tuple(
        IntervalGap(
            start_at=start_at,
            end_at=end_at,
            headcount_gap=headcount_gap,
            role_gaps=roles.get(start_at, {}),
            skill_gaps=skills.get(start_at, {}),
        )
        for start_at, end_at, headcount_gap in slices
    )


def load_roster(db: Session, shift_id: int) -> list[RosterMember]:
    """Every roster row of the shift, each with the person's role and full skill set.

    Each row carries its effective interval: actual times, else the shift times
    (roster_time_service, round 4 PR T2). Reads the database as it is: flush
    pending roster changes first.
    """
    rows = db.execute(
        select(
            RosterAssignment.staff_id,
            RosterAssignment.status,
            Staff.role_id,
            roster_time_service.start_at(),
            roster_time_service.end_at(),
        )
        .join(Staff, Staff.id == RosterAssignment.staff_id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(RosterAssignment.shift_id == shift_id)
    ).all()

    skills = load_skill_sets(db, {row.staff_id for row in rows})
    return [
        RosterMember(
            staff_id=staff_id,
            shift_id=shift_id,
            status=status,
            role_id=role_id,
            skill_ids=skills.get(staff_id, frozenset()),
            start_at=start_at,
            end_at=end_at,
        )
        for staff_id, status, role_id, start_at, end_at in rows
    ]


def load_skill_sets(db: Session, staff_ids: set[int]) -> dict[int, frozenset[int]]:
    """The full skill set of each given person. Someone without skills has no entry."""
    if not staff_ids:
        return {}
    skills: dict[int, set[int]] = {}
    for staff_id, skill_id in db.execute(
        select(StaffSkill.staff_id, StaffSkill.skill_id).where(StaffSkill.staff_id.in_(staff_ids))
    ):
        skills.setdefault(staff_id, set()).add(skill_id)
    return {staff_id: frozenset(skill_ids) for staff_id, skill_ids in skills.items()}
