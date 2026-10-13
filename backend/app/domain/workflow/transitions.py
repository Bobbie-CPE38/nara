"""Allowed case transitions from docs/workflow.md section 5.

The orchestrator validates every transition here before changing case.status.
T1 to T7 are the round 1 edges of section 5.1. The two SAFETY_VALIDATION edges of the
Skeleton were removed in round 1 PR 3. T8 and T9 are the round 2 edges out of
MANUAL_HANDOFF: a head nurse takes them, never a handler or recompute().
"""

from app.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus

ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.OPEN: frozenset({CaseStatus.ASSESSING, CaseStatus.FAILED}),
    CaseStatus.ASSESSING: frozenset({CaseStatus.OPTIMIZING, CaseStatus.FAILED}),
    CaseStatus.OPTIMIZING: frozenset(
        {
            CaseStatus.OUTREACH,
            CaseStatus.MANUAL_HANDOFF,  # T6
            CaseStatus.FAILED,
        }
    ),
    CaseStatus.OUTREACH: frozenset(
        {
            CaseStatus.WAITING_RESPONSE,
            CaseStatus.MANUAL_HANDOFF,  # T5
            CaseStatus.WAITING_APPROVAL,  # T7
            CaseStatus.FAILED,
        }
    ),
    CaseStatus.WAITING_RESPONSE: frozenset(
        {
            CaseStatus.OUTREACH,  # T1
            CaseStatus.WAITING_APPROVAL,  # T2
            CaseStatus.FAILED,
        }
    ),
    # Kept in the enum, but no edge leads here: Safety runs per candidate (Q31).
    CaseStatus.SAFETY_VALIDATION: frozenset({CaseStatus.FAILED}),
    CaseStatus.WAITING_APPROVAL: frozenset(
        {
            CaseStatus.WAITING_RESPONSE,  # T3
            CaseStatus.OUTREACH,  # T4
            CaseStatus.EXECUTING,
            CaseStatus.FAILED,
        }
    ),
    CaseStatus.EXECUTING: frozenset({CaseStatus.RESOLVED, CaseStatus.FAILED}),
    # MANUAL_HANDOFF stops automation, but is not a terminal case status (section 5.2).
    CaseStatus.MANUAL_HANDOFF: frozenset(
        {
            CaseStatus.RESOLVED,  # T8
            CaseStatus.UNRESOLVED,  # T9
            CaseStatus.FAILED,
        }
    ),
    **{status: frozenset() for status in TERMINAL_CASE_STATUSES},
}


class InvalidTransitionError(ValueError):
    """The requested transition is not part of the implemented workflow."""


def assert_transition(current_status: CaseStatus, next_status: CaseStatus) -> None:
    """Raise InvalidTransitionError unless the requested state change is allowed."""
    if next_status not in ALLOWED_TRANSITIONS.get(current_status, frozenset()):
        raise InvalidTransitionError(
            f"Invalid case transition: {current_status.value} -> {next_status.value}"
        )
