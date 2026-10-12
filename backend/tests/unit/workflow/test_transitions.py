import pytest

from app.domain.enums import TERMINAL_CASE_STATUSES, CaseStatus
from app.domain.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    assert_transition,
)

# The Skeleton edges round 1 still uses (docs/workflow.md section 5.1)
SKELETON_EDGES = {
    (CaseStatus.OPEN, CaseStatus.ASSESSING),
    (CaseStatus.ASSESSING, CaseStatus.OPTIMIZING),
    (CaseStatus.OPTIMIZING, CaseStatus.OUTREACH),
    (CaseStatus.OUTREACH, CaseStatus.WAITING_RESPONSE),
    (CaseStatus.WAITING_APPROVAL, CaseStatus.EXECUTING),
    (CaseStatus.EXECUTING, CaseStatus.RESOLVED),
}

# docs/workflow.md section 5.1, T1 to T7.
ROUND1_EDGES = {
    "T1": (CaseStatus.WAITING_RESPONSE, CaseStatus.OUTREACH),
    "T2": (CaseStatus.WAITING_RESPONSE, CaseStatus.WAITING_APPROVAL),
    "T3": (CaseStatus.WAITING_APPROVAL, CaseStatus.WAITING_RESPONSE),
    "T4": (CaseStatus.WAITING_APPROVAL, CaseStatus.OUTREACH),
    "T5": (CaseStatus.OUTREACH, CaseStatus.MANUAL_HANDOFF),
    "T6": (CaseStatus.OPTIMIZING, CaseStatus.MANUAL_HANDOFF),
    "T7": (CaseStatus.OUTREACH, CaseStatus.WAITING_APPROVAL),
}


@pytest.mark.parametrize("current", list(CaseStatus))
@pytest.mark.parametrize("next_status", list(CaseStatus))
def test_transition_contract(current: CaseStatus, next_status: CaseStatus) -> None:
    skeleton = (current, next_status) in SKELETON_EDGES
    round1 = (current, next_status) in ROUND1_EDGES.values()
    failure = current not in TERMINAL_CASE_STATUSES and next_status is CaseStatus.FAILED
    if skeleton or round1 or failure:
        assert_transition(current, next_status)
    else:
        with pytest.raises(InvalidTransitionError, match="Invalid case transition"):
            assert_transition(current, next_status)


@pytest.mark.parametrize("name", list(ROUND1_EDGES))
def test_round1_edge_is_allowed(name: str) -> None:
    current, next_status = ROUND1_EDGES[name]
    assert_transition(current, next_status)


def test_round1_edges_are_new_and_distinct() -> None:
    """A typo that repeats an edge or a golden edge would leave one of T1 to T7 untested."""
    edges = set(ROUND1_EDGES.values())
    assert len(edges) == len(ROUND1_EDGES)
    assert edges.isdisjoint(SKELETON_EDGES)


def test_safety_validation_is_no_longer_a_step_of_the_case() -> None:
    """Safety runs per candidate inside the answer's transaction (Q31, round 1 PR 3)."""
    assert ALLOWED_TRANSITIONS[CaseStatus.SAFETY_VALIDATION] == frozenset({CaseStatus.FAILED})
    assert all(
        CaseStatus.SAFETY_VALIDATION not in targets for targets in ALLOWED_TRANSITIONS.values()
    )


def test_manual_handoff_has_no_exit_except_failed() -> None:
    assert ALLOWED_TRANSITIONS[CaseStatus.MANUAL_HANDOFF] == frozenset({CaseStatus.FAILED})


def test_every_case_status_has_an_explicit_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)


def test_terminal_statuses_are_resolved_unresolved_and_failed() -> None:
    """The contract test above reads this set, so a wrong member would change both sides."""
    assert set(TERMINAL_CASE_STATUSES) == {
        CaseStatus.RESOLVED,
        CaseStatus.UNRESOLVED,
        CaseStatus.FAILED,
    }
