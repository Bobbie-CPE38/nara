"""
The staffing requirement of a shift (docs/workflow.md, section 6.4, seam 10).

Event intake and the ASSESSING step must judge a shift against the same
requirement. Both load it through `get_current_requirement()`, never with their
own query.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
)


class RequirementNotFoundError(LookupError):
    """The shift has no STAFFING_REQUIREMENTS row. The seed gives every shift one."""


@dataclass(frozen=True)
class ShiftRequirement:
    """One requirement version with its role and skill counts, keyed by ID."""

    requirement: StaffingRequirement
    required_roles: dict[int, int]
    required_skills: dict[int, int]


def get_current_requirement(db: Session, shift_id: int) -> ShiftRequirement:
    """Return the latest requirement of a shift. Read-only.

    STAFFING_REQUIREMENTS has no unique key on shift_id, so a shift can have
    several versions. "Latest" is the highest id, not created_at: the demo clock
    is frozen, so every row can carry the same time.
    """
    requirement = db.scalar(
        select(StaffingRequirement)
        .where(StaffingRequirement.shift_id == shift_id)
        .order_by(StaffingRequirement.id.desc())
        .limit(1)
    )
    if requirement is None:
        raise RequirementNotFoundError(f"No staffing requirement for shift {shift_id}")

    roles = db.execute(
        select(StaffingRequirementRole.role_id, StaffingRequirementRole.required_count).where(
            StaffingRequirementRole.staffing_requirement_id == requirement.id
        )
    )
    skills = db.execute(
        select(StaffingRequirementSkill.skill_id, StaffingRequirementSkill.required_count).where(
            StaffingRequirementSkill.staffing_requirement_id == requirement.id
        )
    )
    return ShiftRequirement(
        requirement=requirement,
        required_roles={role_id: count for role_id, count in roles},
        required_skills={skill_id: count for skill_id, count in skills},
    )
