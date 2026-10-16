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
    STAFF_UNAVAILABLE = "STAFF_UNAVAILABLE"  # reason lives in STAFF_UNAVAILABILITY.reason
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    # Demand group: staff_id must be NULL
    PATIENT_SURGE = "PATIENT_SURGE"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"  # what changed goes in payload


STAFF_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.STAFF_UNAVAILABLE,
        EventType.ASSIGNMENT_CANCELLED,
    }
)

DEMAND_EVENT_TYPES: frozenset[EventType] = frozenset(EventType) - STAFF_EVENT_TYPES


class EventStatus(StrEnum):
    RECEIVED = "RECEIVED"  # stored, not processed yet
    PROCESSED = "PROCESSED"  # gap found, attached to a case
    IGNORED = "IGNORED"  # no gap, no case was opened


class EventIgnoredReason(StrEnum):
    """Why an event opened no case: `reason` in the EVENT_IGNORED payload (workflow.md 3.7)."""

    # No event of the window passed the threshold
    THRESHOLD_NOT_PASSED = "THRESHOLD_NOT_PASSED"
    # An event passed, but the shift is covered again after the last event
    NO_GAP = "NO_GAP"
    # Only this event: its person has no ASSIGNED roster row left to cancel
    NO_ASSIGNED_ROSTER = "NO_ASSIGNED_ROSTER"
    # Only this event: a role or skill it changes is not in the requirement
    REQUIREMENT_ITEM_NOT_FOUND = "REQUIREMENT_ITEM_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Case
# --------------------------------------------------------------------------- #
class CaseStatus(StrEnum):
    OPEN = "OPEN"
    ASSESSING = "ASSESSING"
    OPTIMIZING = "OPTIMIZING"
    OUTREACH = "OUTREACH"  # sending an offer (transient)
    WAITING_RESPONSE = "WAITING_RESPONSE"  # wait point: candidate reply
    SAFETY_VALIDATION = "SAFETY_VALIDATION"
    WAITING_APPROVAL = "WAITING_APPROVAL"  # wait point: approver decision
    EXECUTING = "EXECUTING"
    RESOLVED = "RESOLVED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"


WAITING_CASE_STATUSES: frozenset[CaseStatus] = frozenset(
    {
        CaseStatus.WAITING_RESPONSE,
        CaseStatus.WAITING_APPROVAL,
    }
)

TERMINAL_CASE_STATUSES: frozenset[CaseStatus] = frozenset(
    {
        CaseStatus.RESOLVED,
        CaseStatus.UNRESOLVED,
        CaseStatus.FAILED,
    }
)

# MANUAL_HANDOFF ends the automated workflow but the case is still open for humans.
AUTOMATION_STOPPED_STATUSES: frozenset[CaseStatus] = TERMINAL_CASE_STATUSES | {
    CaseStatus.MANUAL_HANDOFF,
}


# --------------------------------------------------------------------------- #
# Staff, shift, availability, roster
# --------------------------------------------------------------------------- #
class StaffStatus(StrEnum):
    """Employment status only. Leave is stored in STAFF_UNAVAILABILITY."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ShiftType(StrEnum):
    DAY = "DAY"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


class AvailabilityReason(StrEnum):
    """STAFF_UNAVAILABILITY.reason. Never changes after the row is created."""

    PLANNED_LEAVE = "PLANNED_LEAVE"  # does not overlap an assigned shift, no event
    UNPLANNED_LEAVE = "UNPLANNED_LEAVE"  # overlaps an assigned shift -> STAFF_UNAVAILABLE event
    NO_SHOW = "NO_SHOW"  # created by the system from ATTENDANCE


class RosterStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"  # accepted, waiting for approval (not used in skeleton)
    ASSIGNED = "ASSIGNED"
    CANCELLED = "CANCELLED"  # includes "staff is absent from this shift"
    COMPLETED = "COMPLETED"


# Rows that block the staff member from another shift at the same time, and the
# shifts that fatigue rules and working time count. COMPLETED is an ASSIGNED row
# whose shift has ended (round 3 PR R): it still counts, or yesterday's shift
# would drop out of rest and consecutive-shift checks.
COMMITTED_ROSTER_STATUSES: frozenset[RosterStatus] = frozenset(
    {
        RosterStatus.PENDING_APPROVAL,
        RosterStatus.ASSIGNED,
        RosterStatus.COMPLETED,
    }
)

# Rows that cover a shift in the gap and threshold counts. COMPLETED counts like
# ASSIGNED, so a shift that ends while its case is open keeps the same gap.
COVERING_ROSTER_STATUSES: frozenset[RosterStatus] = frozenset(
    {
        RosterStatus.ASSIGNED,
        RosterStatus.COMPLETED,
    }
)


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


class TargetType(StrEnum):
    """CANDIDATE_ITEM_TARGET.target_type: what a candidate was selected to fill."""

    HEADCOUNT = "HEADCOUNT"
    ROLE = "ROLE"
    SKILL = "SKILL"


class SelectionType(StrEnum):
    """CANDIDATE_ITEM_TARGET.selection_type.

    RESERVE is the extra 10% of a wave target. It is not the reserve of Q28, a
    candidate who accepted after the gap was already closed.
    """

    PRIMARY = "PRIMARY"
    RESERVE = "RESERVE"


class ManualHandoffReason(StrEnum):
    """`reason` in the payload of a MANUAL_HANDOFF audit row."""

    NO_CANDIDATE_LEFT = "NO_CANDIDATE_LEFT"  # T5, written by contact_candidate
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"  # T6, written by optimize
    # Round 2: the solver hit its time limit without a plan (UNKNOWN), written by optimize
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"


# --------------------------------------------------------------------------- #
# Outreach
# --------------------------------------------------------------------------- #
class OutreachStatus(StrEnum):
    PENDING = "PENDING"  # reserved: queued for a later wave
    SENT = "SENT"  # sent, waiting for reply
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"  # could not be delivered
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


# Round 4 PR S: APPROVAL_WARD_DECISION.side.
class ApprovalSide(StrEnum):
    DESTINATION = "DESTINATION"  # the ward of the shift that is short
    SOURCE = "SOURCE"  # the ward of the shift the person is moved off


# Round 4 PR S: APPROVAL_WARD_DECISION.decided_as.
class ApproverCapacity(StrEnum):
    HEAD_NURSE = "HEAD_NURSE"
    SUPERVISOR = "SUPERVISOR"


# Round 4 PR C2: `reason` of TRANSFER_CHECK_FAILED (docs/workflow.md 6.19).
class TransferFailureReason(StrEnum):
    SOURCE_COVERAGE_LOST = "SOURCE_COVERAGE_LOST"
    DESTINATION_WINDOW_PASSED = "DESTINATION_WINDOW_PASSED"
    HARD_RULE_FAILED = "HARD_RULE_FAILED"
    # PR C3 removed SOURCE_SHIFT_STARTED (R4-Q43): a move after the source shift started
    # is a mid-shift move now. Old audit rows may still hold it; the readers keep the raw string


# --------------------------------------------------------------------------- #
# Actors & audit
# --------------------------------------------------------------------------- #
# Round 5 PR N1: `source` in the payload of an ATTENDANCE_CHECKED_IN audit row (6.24)
class CheckInSource(StrEnum):
    SELF = "SELF"  # the nurse checked in, from the web page or LINE
    SIMULATED = "SIMULATED"  # the demo simulated the arrival under /demo/


class ActorType(StrEnum):
    """Stored in ACTORS.actor_type. Lowercase values by team convention."""

    USER = "user"
    SYSTEM = "system"
    COMPONENT = "component"


class ActorName(StrEnum):
    """ACTORS.name for non-user actors. User actors use str(staff.id) instead."""

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
    SHIFT = "SHIFT"
    STAFFING_REQUIREMENTS = "STAFFING_REQUIREMENTS"
    # Round 3 PR K: linking and unlinking a LINE account. Not written yet
    CONTACTS = "CONTACTS"
    # Round 5 PR N1: a check-in (docs/workflow.md 6.24). Not written yet
    ATTENDANCE = "ATTENDANCE"


class AuditAction(StrEnum):
    # Event intake
    EVENT_RECEIVED = "EVENT_RECEIVED"
    EVENT_IGNORED = "EVENT_IGNORED"
    # Case lifecycle
    CASE_OPENED = "CASE_OPENED"
    CASE_STATUS_CHANGED = "CASE_STATUS_CHANGED"  # written only by the orchestrator
    CASE_RESOLVED = "CASE_RESOLVED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"
    # Round 2, T9: closed by a head nurse or by a successor case. Not written yet
    CASE_CLOSED_UNRESOLVED = "CASE_CLOSED_UNRESOLVED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    # Steps
    GAP_ASSESSED = "GAP_ASSESSED"
    SOLVER_EXECUTED = "SOLVER_EXECUTED"
    OFFER_SENT = "OFFER_SENT"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_REJECTED = "OFFER_REJECTED"
    OFFER_TIMEOUT = "OFFER_TIMEOUT"
    # Round 2, in the case that lost the offer to another case. Not written yet
    OFFER_CANCELLED_BY_ASSIGNMENT = "OFFER_CANCELLED_BY_ASSIGNMENT"
    # Round 3 PR L: LINE delivery failed; written by line_delivery_service.
    OFFER_DELIVERY_FAILED = "OFFER_DELIVERY_FAILED"
    SAFETY_PASSED = "SAFETY_PASSED"
    SAFETY_FAILED = "SAFETY_FAILED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_TIMEOUT = "APPROVAL_TIMEOUT"  # round 2 PR T, written by the job
    # Round 4 PR S: one ward of a two-ward request approved. Not written yet
    APPROVAL_WARD_APPROVED = "APPROVAL_WARD_APPROVED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    # Round 2: a head nurse staffed a MANUAL_HANDOFF case directly. Not written yet
    MANUAL_ASSIGNMENT_CREATED = "MANUAL_ASSIGNMENT_CREATED"
    # Round 4 PR C2: a person moved off another ward's shift.
    ASSIGNMENT_TRANSFERRED = "ASSIGNMENT_TRANSFERRED"
    # Round 4 PR C2: the check at the real move failed; the request ends.
    TRANSFER_CHECK_FAILED = "TRANSFER_CHECK_FAILED"
    # Round 5 PR H1: the shared assignment function (docs/workflow.md 6.25). Not written yet
    HANDOVER_GENERATED = "HANDOVER_GENERATED"
    # Round 5 PR N1: a nurse checked in, or the demo simulated it (6.24). Not written yet
    ATTENDANCE_CHECKED_IN = "ATTENDANCE_CHECKED_IN"
    # Round 5 PR N2: a late arrival made an offer or request unneeded (6.24). Not written yet
    OFFER_CANCELLED_NOT_NEEDED = "OFFER_CANCELLED_NOT_NEEDED"
    # Unavailability
    UNAVAILABILITY_CREATED = "UNAVAILABILITY_CREATED"
    UNAVAILABILITY_UPDATED = "UNAVAILABILITY_UPDATED"
    # Round 3 PR K: a staff member's LINE account. Not written yet
    LINE_ACCOUNT_LINKED = "LINE_ACCOUNT_LINKED"
    LINE_ACCOUNT_UNLINKED = "LINE_ACCOUNT_UNLINKED"
    # Event side effects written when a merge window closes
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    PATIENT_COUNT_UPDATED = "PATIENT_COUNT_UPDATED"
    REQUIREMENT_UPDATED = "REQUIREMENT_UPDATED"


# Round 3 PR X: LLM ranking explanation
class ExplanationStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# Round 3 PR X: one row per LLM attempt. IN_FLIGHT is written before the call, so if it
# stays, the attempt crashed and its usage is unknown
class LlmCallStatus(StrEnum):
    IN_FLIGHT = "IN_FLIGHT"
    SUCCEEDED = "SUCCEEDED"
    # Retryable
    TIMEOUT = "TIMEOUT"
    THROTTLED = "THROTTLED"
    SERVICE_ERROR = "SERVICE_ERROR"
    # Not retryable
    CONFIG_ERROR = "CONFIG_ERROR"
    TRUNCATED = "TRUNCATED"
    INVALID_OUTPUT = "INVALID_OUTPUT"


# Exact non-transition audit sequence expected by the Golden Case E2E test.
# Its one-person gap has ceil(1.1 * 1) = 2 candidates: wave 1 sends to
# both 201 and 202, hence two consecutive OFFER_SENT rows.
GOLDEN_PATH_AUDIT_ACTIONS: tuple[AuditAction, ...] = (
    AuditAction.EVENT_RECEIVED,
    AuditAction.UNAVAILABILITY_CREATED,
    AuditAction.CASE_OPENED,
    AuditAction.GAP_ASSESSED,
    AuditAction.SOLVER_EXECUTED,
    AuditAction.OFFER_SENT,
    AuditAction.OFFER_SENT,
    AuditAction.OFFER_ACCEPTED,
    AuditAction.SAFETY_PASSED,
    AuditAction.APPROVAL_REQUESTED,
    AuditAction.APPROVAL_APPROVED,
    AuditAction.ASSIGNMENT_CREATED,
    AuditAction.CASE_RESOLVED,
)


class ApprovalOutcome(StrEnum):
    WAITING_OTHER_WARD = "WAITING_OTHER_WARD"
    ASSIGNED = "ASSIGNED"
    REJECTED = "REJECTED"
    TRANSFER_CANCELLED = "TRANSFER_CANCELLED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
