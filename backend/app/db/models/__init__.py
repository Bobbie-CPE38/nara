# Import every model here so its table registers on Base.metadata
# (alembic/env.py imports this package for autogenerate)
from app.db.models.actor import Actor
from app.db.models.role import Role
from app.db.models.roster_assignment import RosterAssignment
from app.db.models.shift import Shift
from app.db.models.skill import Skill
from app.db.models.staff import Staff
from app.db.models.staff_skill import StaffSkill
from app.db.models.staff_unavailability import StaffUnavailability
from app.db.models.staffing_case import StaffingCase
from app.db.models.staffing_event import StaffingEvent
from app.db.models.staffing_gap import StaffingGap
from app.db.models.staffing_gap_role import StaffingGapRole
from app.db.models.staffing_gap_skill import StaffingGapSkill
from app.db.models.staffing_requirement import StaffingRequirement
from app.db.models.staffing_requirement_role import StaffingRequirementRole
from app.db.models.staffing_requirement_skill import StaffingRequirementSkill
from app.db.models.ward import Ward

__all__ = [
    "Actor",
    "Role",
    "RosterAssignment",
    "Shift",
    "Skill",
    "Staff",
    "StaffSkill",
    "StaffUnavailability",
    "StaffingCase",
    "StaffingEvent",
    "StaffingGap",
    "StaffingGapRole",
    "StaffingGapSkill",
    "StaffingRequirement",
    "StaffingRequirementRole",
    "StaffingRequirementSkill",
    "Ward",
]
