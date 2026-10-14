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

# docs/workflow.md section 5.1, T8 and T9: the ways out of MANUAL_HANDOFF.
ROUND2_EDGES = {
    "T8": (CaseStatus.MANUAL_HANDOFF, CaseStatus.RESOLVED),
    "T9": (CaseStatus.MANUAL_HANDOFF, CaseStatus.UNRESOLVED),
}


@pytest.mark.parametrize("current", list(CaseStatus))
@pytest.mark.parametrize("next_status", list(CaseStatus))
def test_transition_contract(current: CaseStatus, next_status: CaseStatus) -> None:
    skeleton = (current, next_status) in SKELETON_EDGES
    round1 = (current, next_status) in ROUND1_EDGES.values()
    round2 = (current, next_status) in ROUND2_EDGES.values()
    failure = current not in TERMINAL_CASE_STATUSES and next_status is CaseStatus.FAILED
    if skeleton or round1 or round2 or failure:
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


@pytest.mark.parametrize("name", list(ROUND2_EDGES))
def test_round2_edge_is_allowed(name: str) -> None:
    current, next_status = ROUND2_EDGES[name]
    assert_transition(current, next_status)


def test_round2_edges_are_new_and_distinct() -> None:
    edges = set(ROUND2_EDGES.values())
    assert len(edges) == len(ROUND2_EDGES)
    assert edges.isdisjoint(SKELETON_EDGES)
    assert edges.isdisjoint(ROUND1_EDGES.values())


def test_safety_validation_is_no_longer_a_step_of_the_case() -> None:
    """Safety runs per candidate inside the answer's transaction (Q31, round 1 PR 3)."""
    assert ALLOWED_TRANSITIONS[CaseStatus.SAFETY_VALIDATION] == frozenset({CaseStatus.FAILED})
    assert all(
        CaseStatus.SAFETY_VALIDATION not in targets for targets in ALLOWED_TRANSITIONS.values()
    )


def test_manual_handoff_leads_only_to_the_two_manual_exits_and_failed() -> None:
    """No edge leads back into the automatic flow: the solver runs once per case (Q37)."""
    assert ALLOWED_TRANSITIONS[CaseStatus.MANUAL_HANDOFF] == frozenset(
        {CaseStatus.RESOLVED, CaseStatus.UNRESOLVED, CaseStatus.FAILED}
    )


def test_unresolved_is_reached_only_from_manual_handoff() -> None:
    sources = {
        current
        for current, targets in ALLOWED_TRANSITIONS.items()
        if CaseStatus.UNRESOLVED in targets
    }
    assert sources == {CaseStatus.MANUAL_HANDOFF}


def test_every_case_status_has_an_explicit_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)


def test_terminal_statuses_are_resolved_unresolved_and_failed() -> None:
    """The contract test above reads this set, so a wrong member would change both sides."""
    assert set(TERMINAL_CASE_STATUSES) == {
        CaseStatus.RESOLVED,
        CaseStatus.UNRESOLVED,
        CaseStatus.FAILED,
    }
