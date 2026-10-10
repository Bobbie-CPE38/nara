"""
Gap assessment of one shift from the database (docs/workflow.md, sections 3 and 8).

Loads what `domain.staffing.gap_calculator` needs and runs it. Event intake
uses the result to decide between IGNORED and a new case. The ASSESSING step
uses the same function, so both always agree.

`assess_shift()` only reads. The ASSESSING step stores its result with
`record_gap()`; event intake never does, because an ignored event has no case.
"""

from dataclasses import dataclass
from decimal import Decimal

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
    patient_count: int
    patients_per_nurse: Decimal
    result: GapResult


def assess_shift(db: Session, shift: Shift) -> ShiftAssessment:
    """Compare the shift's current roster with its workload and requirement."""
    # The caller may have just cancelled a roster row. SessionLocal has
    # autoflush off, so send that change before the roster is read back
    db.flush()

    shift_requirement = requirement_service.get_current_requirement(db, shift.id)
    policy = policy_service.get_hard_constraint_policy(db)
    result = calculate_gap(
        shift_id=shift.id,
        patient_count=shift.patient_count,
        patients_per_nurse=policy.maximum_patients_per_nurse,
        required_roles=shift_requirement.required_roles,
        required_skills=shift_requirement.required_skills,
        roster=_load_roster(db, shift.id),
    )
    return ShiftAssessment(
        shift_requirement=shift_requirement,
        patient_count=shift.patient_count,
        patients_per_nurse=policy.maximum_patients_per_nurse,
        result=result,
    )


def record_gap(db: Session, case: StaffingCase, assessment: ShiftAssessment) -> StaffingGap:
    """Store one assessment as the STAFFING_GAP of a case; flush but never commit.

    The snapshot columns take the values the calculator was given, not a fresh
    read of the shift or the policy. Every required role and skill gets a row,
    also the ones without a shortage.
    """
    result = assessment.result
    gap = StaffingGap(
        case_id=case.id,
        staffing_requirement_id=assessment.shift_requirement.requirement.id,
        headcount_gap=result.headcount_gap,
        patient_count=assessment.patient_count,
        patients_per_nurse=assessment.patients_per_nurse,
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
