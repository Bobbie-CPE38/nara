"""Register ORM tables on Base.metadata for Alembic autogeneration.

Import every model here so its table registers on Base.metadata
(alembic/env.py imports this package for autogenerate).
Timestamp values must be supplied using app.core.clock.now(), not database defaults.
"""

from app.db.models.actor import Actor
from app.db.models.approval_policy import ApprovalPolicy
from app.db.models.approval_request import ApprovalRequest
from app.db.models.attendance import Attendance
from app.db.models.audit_log import AuditLog
from app.db.models.candidate_item import CandidateItem
from app.db.models.candidate_outreach import CandidateOutreach
from app.db.models.candidate_plan import CandidatePlan
from app.db.models.contact import Contact
from app.db.models.hard_constraint_policy import HardConstraintPolicy
from app.db.models.role import Role
from app.db.models.roster_assignment import RosterAssignment
from app.db.models.safety_validation import SafetyValidation
from app.db.models.shift import Shift
from app.db.models.skill import Skill
from app.db.models.soft_constraint_policy import SoftConstraintPolicy
from app.db.models.staff import Staff
from app.db.models.staff_skill import StaffSkill
from app.db.models.staff_unavailability import StaffUnavailability
from app.db.models.staff_working_time_snapshot import StaffWorkingTimeSnapshot
from app.db.models.staffing_case import StaffingCase
from app.db.models.staffing_event import StaffingEvent
from app.db.models.staffing_gap import StaffingGap
from app.db.models.staffing_gap_role import StaffingGapRole
from app.db.models.staffing_gap_skill import StaffingGapSkill
from app.db.models.staffing_requirement import StaffingRequirement
from app.db.models.staffing_requirement_role import StaffingRequirementRole
from app.db.models.staffing_requirement_skill import StaffingRequirementSkill
from app.db.models.structured_handover import StructuredHandover
from app.db.models.ward import Ward

__all__ = [
    "Actor",
    "ApprovalPolicy",
    "ApprovalRequest",
    "Attendance",
    "AuditLog",
    "CandidateItem",
    "CandidateOutreach",
    "CandidatePlan",
    "Contact",
    "HardConstraintPolicy",
    "Role",
    "RosterAssignment",
    "SafetyValidation",
    "Shift",
    "Skill",
    "SoftConstraintPolicy",
    "Staff",
    "StaffSkill",
    "StaffUnavailability",
    "StaffWorkingTimeSnapshot",
    "StaffingCase",
    "StaffingEvent",
    "StaffingGap",
    "StaffingGapRole",
    "StaffingGapSkill",
    "StaffingRequirement",
    "StaffingRequirementRole",
    "StaffingRequirementSkill",
    "StructuredHandover",
    "Ward",
]
