"""
Shared enums for the staffing workflow.

Source of truth: docs/workflow.md and docs/database-schema.md.
Rules:
  * Every value is stored in PostgreSQL as plain `text` (no DB ENUM, no CHECK yet).
  * Change a value only together with docs/workflow.md, in the same PR.
  * Requires Python 3.11+ (StrEnum).
"""
from enum import StrEnum


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
class EventType(StrEnum):
    # Staff group: staff_id is required
    STAFF_UNAVAILABLE = "STAFF_UNAVAILABLE"
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    # Demand group: staff_id must be NULL
    PATIENT_SURGE = "PATIENT_SURGE"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"


STAFF_EVENT_TYPES: frozenset[EventType] = frozenset({
    EventType.STAFF_UNAVAILABLE,
    EventType.ASSIGNMENT_CANCELLED,
})

DEMAND_EVENT_TYPES: frozenset[EventType] = frozenset(EventType) - STAFF_EVENT_TYPES


class EventStatus(StrEnum):
    RECEIVED = "RECEIVED"      # stored, not processed yet
    PROCESSED = "PROCESSED"    # gap found, attached to a case
    IGNORED = "IGNORED"        # no gap, no case was opened


# --------------------------------------------------------------------------- #
# Case
# --------------------------------------------------------------------------- #
class CaseStatus(StrEnum):
    OPEN = "OPEN"
    ASSESSING = "ASSESSING"
    OPTIMIZING = "OPTIMIZING"
    OUTREACH = "OUTREACH"                    # sending an offer (transient)
    WAITING_RESPONSE = "WAITING_RESPONSE"    # wait point: candidate reply
    SAFETY_VALIDATION = "SAFETY_VALIDATION"
    WAITING_APPROVAL = "WAITING_APPROVAL"    # wait point: approver decision
    EXECUTING = "EXECUTING"
    RESOLVED = "RESOLVED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"


WAITING_CASE_STATUSES: frozenset[CaseStatus] = frozenset({
    CaseStatus.WAITING_RESPONSE,
    CaseStatus.WAITING_APPROVAL,
})

TERMINAL_CASE_STATUSES: frozenset[CaseStatus] = frozenset({
    CaseStatus.RESOLVED,
    CaseStatus.UNRESOLVED,
    CaseStatus.FAILED,
})

# MANUAL_HANDOFF ends the automated workflow but the case is still open for humans.
AUTOMATION_STOPPED_STATUSES: frozenset[CaseStatus] = TERMINAL_CASE_STATUSES | {
    CaseStatus.MANUAL_HANDOFF,
}


# --------------------------------------------------------------------------- #
# Staff, shift, availability, roster
# --------------------------------------------------------------------------- #
class StaffStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    # Leave is not a staff status: see STAFF_UNAVAILABILITY / AvailabilityReason.


class ShiftType(StrEnum):
    DAY = "DAY"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


class AvailabilityReason(StrEnum):
    """STAFF_UNAVAILABILITY.reason. Never changes after the row is created."""
    PLANNED_LEAVE = "PLANNED_LEAVE"        # no clash with a rostered shift, no event
    UNPLANNED_LEAVE = "UNPLANNED_LEAVE"    # clashes with a rostered shift -> STAFF_UNAVAILABLE
    NO_SHOW = "NO_SHOW"                    # system-created, no check-in -> STAFF_UNAVAILABLE


class RosterStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ASSIGNED = "ASSIGNED"
    CANCELLED = "CANCELLED"     # includes "staff is absent from this shift"
    COMPLETED = "COMPLETED"


class AssignmentType(StrEnum):
    REGULAR = "REGULAR"
    REPLACEMENT = "REPLACEMENT"


class CandidateSource(StrEnum):
    SAME_WARD = "SAME_WARD"
    FLOAT_POOL = "FLOAT_POOL"
    CROSS_WARD = "CROSS_WARD"


# --------------------------------------------------------------------------- #
# Optimization
# --------------------------------------------------------------------------- #
class SolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    MODEL_INVALID = "MODEL_INVALID"
    UNKNOWN = "UNKNOWN"


class OptimizationObjective(StrEnum):
    MIN_CANDIDATE_COUNT = "MIN_CANDIDATE_COUNT"
    MIN_CONSECUTIVE_SHIFT = "MIN_CONSECUTIVE_SHIFT"
    CANDIDATE_SOURCE = "CANDIDATE_SOURCE"
    WEEKLY_WORKLOAD_FAIRNESS = "WEEKLY_WORKLOAD_FAIRNESS"
    MIN_PROJECTED_OVERTIME = "MIN_PROJECTED_OVERTIME"


# --------------------------------------------------------------------------- #
# Outreach
# --------------------------------------------------------------------------- #
class OutreachStatus(StrEnum):
    PENDING = "PENDING"        # reserved: queued for a later wave
    SENT = "SENT"              # sent, waiting for reply
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"          # could not be delivered
    CANCELLED = "CANCELLED"


class CandidateResponse(StrEnum):
    """Value sent by the candidate (LINE / LINE simulator)."""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class Channel(StrEnum):
    LINE = "LINE"


# --------------------------------------------------------------------------- #
# Safety & approval
# --------------------------------------------------------------------------- #
class ValidationResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class ApprovalMode(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


# --------------------------------------------------------------------------- #
# Actors & audit
# --------------------------------------------------------------------------- #
class ActorType(StrEnum):
    """Stored in ACTORS.actor_type. Lowercase values by team convention."""
    USER = "user"
    SYSTEM = "system"
    COMPONENT = "component"


class ActorName(StrEnum):
    """ACTORS.name for non-user actors. User actors use the staff code instead."""
    SYSTEM = "system"
    WORKFLOW_ORCHESTRATOR = "workflow_orchestrator"
    STAFFING_GAP_ASSESSMENT_AGENT = "staffing_gap_assessment_agent"
    CONSTRAINT_FAIR_SCHEDULING_AGENT = "constraint_fair_scheduling_agent"
    OUTREACH_AGENT = "outreach_agent"
    SAFETY_RULE_ENGINE = "safety_rule_engine"


class EntityType(StrEnum):
    """AUDIT_LOG.entity_type: name of the table that was acted on."""
    STAFFING_EVENTS = "STAFFING_EVENTS"
    STAFFING_CASES = "STAFFING_CASES"
    STAFFING_GAP = "STAFFING_GAP"
    CANDIDATE_PLANS = "CANDIDATE_PLANS"
    CANDIDATE_OUTREACH = "CANDIDATE_OUTREACH"
    SAFETY_VALIDATION = "SAFETY_VALIDATION"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    ROSTER_ASSIGNMENT = "ROSTER_ASSIGNMENT"
    STRUCTURED_HANDOVER = "STRUCTURED_HANDOVER"
    STAFF_UNAVAILABILITY = "STAFF_UNAVAILABILITY"


class AuditAction(StrEnum):
    # Event intake
    EVENT_RECEIVED = "EVENT_RECEIVED"
    EVENT_IGNORED = "EVENT_IGNORED"
    # Case lifecycle
    CASE_OPENED = "CASE_OPENED"
    CASE_STATUS_CHANGED = "CASE_STATUS_CHANGED"   # written only by the orchestrator
    CASE_RESOLVED = "CASE_RESOLVED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    # Steps
    GAP_ASSESSED = "GAP_ASSESSED"
    SOLVER_EXECUTED = "SOLVER_EXECUTED"
    OFFER_SENT = "OFFER_SENT"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_REJECTED = "OFFER_REJECTED"
    OFFER_TIMEOUT = "OFFER_TIMEOUT"
    SAFETY_PASSED = "SAFETY_PASSED"
    SAFETY_FAILED = "SAFETY_FAILED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    HANDOVER_GENERATED = "HANDOVER_GENERATED"
    # Staff unavailability
    UNAVAILABILITY_CREATED = "UNAVAILABILITY_CREATED"
    UNAVAILABILITY_UPDATED = "UNAVAILABILITY_UPDATED"


# Actions the golden-path E2E test expects to find, in order of first appearance.
GOLDEN_PATH_AUDIT_ACTIONS: tuple[AuditAction, ...] = (
    AuditAction.EVENT_RECEIVED,
    AuditAction.CASE_OPENED,
    AuditAction.GAP_ASSESSED,
    AuditAction.SOLVER_EXECUTED,
    AuditAction.OFFER_SENT,
    AuditAction.OFFER_ACCEPTED,
    AuditAction.SAFETY_PASSED,
    AuditAction.APPROVAL_REQUESTED,
    AuditAction.APPROVAL_APPROVED,
    AuditAction.ASSIGNMENT_CREATED,
    AuditAction.CASE_RESOLVED,
)
