"""Allowed case transitions from docs/workflow.md section 5.

The orchestrator validates every transition here before changing case.status.
Reject, timeout, retry and manual-handoff paths are added when implemented.
"""

from app.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus

ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.OPEN: frozenset({CaseStatus.ASSESSING, CaseStatus.FAILED}),
    CaseStatus.ASSESSING: frozenset({CaseStatus.OPTIMIZING, CaseStatus.FAILED}),
    CaseStatus.OPTIMIZING: frozenset({CaseStatus.OUTREACH, CaseStatus.FAILED}),
    CaseStatus.OUTREACH: frozenset({CaseStatus.WAITING_RESPONSE, CaseStatus.FAILED}),
    CaseStatus.WAITING_RESPONSE: frozenset({CaseStatus.SAFETY_VALIDATION, CaseStatus.FAILED}),
    CaseStatus.SAFETY_VALIDATION: frozenset({CaseStatus.WAITING_APPROVAL, CaseStatus.FAILED}),
    CaseStatus.WAITING_APPROVAL: frozenset({CaseStatus.EXECUTING, CaseStatus.FAILED}),
    CaseStatus.EXECUTING: frozenset({CaseStatus.RESOLVED, CaseStatus.FAILED}),
    # MANUAL_HANDOFF stops automation, but is not a terminal case status (section 5.2).
    CaseStatus.MANUAL_HANDOFF: frozenset({CaseStatus.FAILED}),
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
