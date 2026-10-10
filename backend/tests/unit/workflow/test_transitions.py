import pytest

from app.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus
from app.domain.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    assert_transition,
)

GOLDEN_PATH = (
    CaseStatus.OPEN,
    CaseStatus.ASSESSING,
    CaseStatus.OPTIMIZING,
    CaseStatus.OUTREACH,
    CaseStatus.WAITING_RESPONSE,
    CaseStatus.SAFETY_VALIDATION,
    CaseStatus.WAITING_APPROVAL,
    CaseStatus.EXECUTING,
    CaseStatus.RESOLVED,
)
GOLDEN_EDGES = set(zip(GOLDEN_PATH, GOLDEN_PATH[1:], strict=False))


@pytest.mark.parametrize("current", list(CaseStatus))
@pytest.mark.parametrize("next_status", list(CaseStatus))
def test_transition_contract(current: CaseStatus, next_status: CaseStatus) -> None:
    golden = (current, next_status) in GOLDEN_EDGES
    failure = current not in TERMINAL_CASE_STATUSES and next_status is CaseStatus.FAILED
    if golden or failure:
        assert_transition(current, next_status)
    else:
        with pytest.raises(InvalidTransitionError, match="Invalid case transition"):
            assert_transition(current, next_status)


def test_every_case_status_has_an_explicit_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)


def test_terminal_statuses_are_resolved_unresolved_and_failed() -> None:
    """The contract test above reads this set, so a wrong member would change both sides."""
    assert set(TERMINAL_CASE_STATUSES) == {
        CaseStatus.RESOLVED,
        CaseStatus.UNRESOLVED,
        CaseStatus.FAILED,
    }
