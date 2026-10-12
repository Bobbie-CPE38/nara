"""
Gap assessment of one shift from the database (docs/workflow.md, sections 3 and 8).

Loads what `domain.staffing.gap_calculator` needs and runs it. Event intake
uses the result to decide between IGNORED and a new case. The ASSESSING step
uses the same function, so both always agree.

`assess_shift()` only reads. The ASSESSING step stores its result with
`record_gap()`; event intake never does, because an ignored event has no case.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingGap,
    StaffingGapRole,
    StaffingGapSkill,
    StaffSkill,
)
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import GapResult, calculate_gap
from app.services import policy_service, requirement_service
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
    result = calculate_gap(
        shift_id=shift.id,
        required_staff=shift_requirement.requirement.required_staff,
        minimum_staff=shift_requirement.requirement.minimum_staff,
        preserve_minimum_staffing=policy.preserve_minimum_staffing,
        required_roles=shift_requirement.required_roles,
        required_skills=shift_requirement.required_skills,
        roster=_load_roster(db, shift.id),
    )
    return ShiftAssessment(shift_requirement=shift_requirement, result=result)


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
    db.flush()
    return gap


def get_case_gap(db: Session, case_id: int) -> CaseGap:
    """Return the latest gap of a case with its short roles and skills. Read-only.

    The one loader for the Solver and Safety (workflow.md section 6.4, seam 11).
    "Latest" is the highest id. Raises GapNotFoundError when the case has no gap.
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
    return CaseGap(
        gap=gap,
        role_gaps={role_id: count for role_id, count in roles},
        skill_gaps={skill_id: count for skill_id, count in skills},
    )


def _load_roster(db: Session, shift_id: int) -> list[RosterMember]:
    """Every roster row of the shift, each with the person's role and full skill set."""
    rows = db.execute(
        select(RosterAssignment.staff_id, RosterAssignment.status, Staff.role_id)
        .join(Staff, Staff.id == RosterAssignment.staff_id)
        .where(RosterAssignment.shift_id == shift_id)
    ).all()

    skills: dict[int, set[int]] = {}
    staff_ids = {staff_id for staff_id, _, _ in rows}
    if staff_ids:
        skill_rows = db.execute(
            select(StaffSkill.staff_id, StaffSkill.skill_id).where(
                StaffSkill.staff_id.in_(staff_ids)
            )
        )
        for staff_id, skill_id in skill_rows:
            skills.setdefault(staff_id, set()).add(skill_id)

    return [
        RosterMember(
            staff_id=staff_id,
            shift_id=shift_id,
            status=status,
            role_id=role_id,
            skill_ids=frozenset(skills.get(staff_id, ())),
        )
        for staff_id, status, role_id in rows
    ]
