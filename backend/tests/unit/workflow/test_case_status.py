"""decide_status() and gap_closed(): docs/workflow.md sections 4.2 and 5.3."""

from dataclasses import FrozenInstanceError
from itertools import product

import pytest

from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    CaseStatus,
)
from app.domain.workflow.case_status import (
    CaseFacts,
    GapFiller,
    GapNeeds,
    decide_status,
    gap_closed,
)
from app.domain.workflow.transitions import ALLOWED_TRANSITIONS

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2


def person(staff_id: int, role_id: int = RN, *skills: int) -> GapFiller:
    return GapFiller(staff_id=staff_id, role_id=role_id, skill_ids=frozenset(skills))


# --------------------------------------------------------------------------- #
# decide_status
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("by_assigned", "with_pending", "open_offer", "expected"),
    [
        # Rule 1 wins over everything
        (True, True, True, CaseStatus.EXECUTING),
        (True, True, False, CaseStatus.EXECUTING),
        # Rule 2: pending approvals cover the rest, with or without open offers
        (False, True, True, CaseStatus.WAITING_APPROVAL),
        (False, True, False, CaseStatus.WAITING_APPROVAL),
        # Rule 3
        (False, False, True, CaseStatus.WAITING_RESPONSE),
        # Rule 4
        (False, False, False, CaseStatus.OUTREACH),
    ],
)
def test_first_rule_that_holds_is_the_answer(
    by_assigned: bool, with_pending: bool, open_offer: bool, expected: CaseStatus
) -> None:
    facts = CaseFacts(
        gap_closed_by_assigned=by_assigned,
        gap_closed_with_pending=with_pending,
        has_open_offer=open_offer,
    )

    assert decide_status(facts) is expected


@pytest.mark.parametrize("open_offer", [True, False])
def test_assigned_cannot_close_a_gap_that_assigned_plus_pending_leaves_open(
    open_offer: bool,
) -> None:
    """The pending group contains the assigned group, so this would be a loader bug."""
    with pytest.raises(ValueError, match="also closed with the pending"):
        CaseFacts(
            gap_closed_by_assigned=True, gap_closed_with_pending=False, has_open_offer=open_offer
        )


def test_decide_status_never_returns_a_stopped_status() -> None:
    """MANUAL_HANDOFF and FAILED are not computed: a handler or D11 sets them."""
    results = set()
    for by_assigned, with_pending, open_offer in product([True, False], repeat=3):
        if by_assigned and not with_pending:
            continue
        results.add(
            decide_status(
                CaseFacts(
                    gap_closed_by_assigned=by_assigned,
                    gap_closed_with_pending=with_pending,
                    has_open_offer=open_offer,
                )
            )
        )

    assert results == {
        CaseStatus.EXECUTING,
        CaseStatus.WAITING_APPROVAL,
        CaseStatus.WAITING_RESPONSE,
        CaseStatus.OUTREACH,
    }
    assert results.isdisjoint(AUTOMATION_STOPPED_STATUSES)


@pytest.mark.parametrize(
    ("current", "target", "edge"),
    [
        (CaseStatus.WAITING_RESPONSE, CaseStatus.OUTREACH, "T1"),
        (CaseStatus.WAITING_RESPONSE, CaseStatus.WAITING_APPROVAL, "T2"),
        (CaseStatus.WAITING_APPROVAL, CaseStatus.WAITING_RESPONSE, "T3"),
        (CaseStatus.WAITING_APPROVAL, CaseStatus.OUTREACH, "T4"),
        (CaseStatus.WAITING_APPROVAL, CaseStatus.EXECUTING, "golden"),
    ],
)
def test_every_move_recompute_makes_from_a_wait_point_is_an_allowed_transition(
    current: CaseStatus, target: CaseStatus, edge: str
) -> None:
    assert current in WAITING_CASE_STATUSES
    assert target in ALLOWED_TRANSITIONS[current], edge


def test_facts_cannot_be_mutated() -> None:
    facts = CaseFacts(
        gap_closed_by_assigned=False, gap_closed_with_pending=False, has_open_offer=True
    )

    with pytest.raises(FrozenInstanceError):
        facts.has_open_offer = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# gap_closed
# --------------------------------------------------------------------------- #
def test_golden_case_gap_is_closed_by_one_rn() -> None:
    needs = GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={})

    assert not gap_closed(needs, [])
    assert gap_closed(needs, [person(201, RN, ICU, BLS)])


def test_wrong_role_fills_headcount_but_not_the_role_gap() -> None:
    needs = GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={})

    assert not gap_closed(needs, [person(900, HEAD_NURSE)])


def test_headcount_only_gap_accepts_any_role() -> None:
    """Which roles may fill headcount is a Hard Rule for the caller, not this count."""
    needs = GapNeeds(headcount_gap=1, role_gaps={}, skill_gaps={})

    assert gap_closed(needs, [person(900, HEAD_NURSE)])


def test_skill_gap_needs_someone_who_holds_the_skill() -> None:
    needs = GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={ICU: 1})

    assert not gap_closed(needs, [person(202, RN, BLS)])
    assert gap_closed(needs, [person(203, RN, ICU)])


def test_one_person_counts_toward_every_gap_they_match() -> None:
    """A + B missing: one person with both, or one person each (Q46)."""
    needs = GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={ICU: 1, BLS: 1})

    assert gap_closed(needs, [person(201, RN, ICU, BLS)])
    assert gap_closed(needs, [person(203, RN, ICU), person(202, RN, BLS)])
    assert not gap_closed(needs, [person(203, RN, ICU)])


@pytest.mark.parametrize(("people", "closed"), [(0, False), (1, False), (2, True), (3, True)])
def test_headcount_gap_of_two_needs_two_people(people: int, closed: bool) -> None:
    needs = GapNeeds(headcount_gap=2, role_gaps={RN: 2}, skill_gaps={})

    assert gap_closed(needs, [person(200 + index) for index in range(people)]) is closed


def test_enough_people_without_the_skill_do_not_close_the_gap() -> None:
    needs = GapNeeds(headcount_gap=2, role_gaps={RN: 2}, skill_gaps={ICU: 2})

    assert not gap_closed(needs, [person(203, RN, ICU), person(202, RN, BLS)])
    assert gap_closed(needs, [person(203, RN, ICU), person(201, RN, ICU, BLS)])


def test_skill_gap_can_need_more_people_than_the_headcount_gap() -> None:
    """Headcount is covered by one person, but two ICU nurses are still missing."""
    needs = GapNeeds(headcount_gap=1, role_gaps={}, skill_gaps={ICU: 2})

    assert not gap_closed(needs, [person(203, RN, ICU)])
    assert gap_closed(needs, [person(203, RN, ICU), person(201, RN, ICU)])


def test_zero_entries_ask_for_nothing() -> None:
    needs = GapNeeds(headcount_gap=0, role_gaps={RN: 0}, skill_gaps={ICU: 0})

    assert gap_closed(needs, [])


def test_the_same_person_listed_twice_counts_once() -> None:
    needs = GapNeeds(headcount_gap=2, role_gaps={RN: 2}, skill_gaps={})
    same = person(201, RN, ICU)

    assert not gap_closed(needs, [same, same])


@pytest.mark.parametrize("kind", ["role", "skills"])
def test_conflicting_snapshots_of_one_person_are_rejected(kind: str) -> None:
    needs = GapNeeds(headcount_gap=1, role_gaps={}, skill_gaps={})
    other = person(201, HEAD_NURSE, ICU) if kind == "role" else person(201, RN, BLS)

    with pytest.raises(ValueError, match="Conflicting coverage"):
        gap_closed(needs, [person(201, RN, ICU), other])


def test_fillers_can_be_a_one_shot_iterator() -> None:
    needs = GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={})

    assert gap_closed(needs, iter([person(201)]))


@pytest.mark.parametrize("kind", ["headcount", "role", "skill"])
def test_negative_needs_are_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        GapNeeds(
            headcount_gap=-1 if kind == "headcount" else 1,
            role_gaps={RN: -1 if kind == "role" else 1},
            skill_gaps={ICU: -1 if kind == "skill" else 1},
        )


def test_needs_copy_their_mappings_and_hash_by_content() -> None:
    roles, skills = {RN: 1}, {ICU: 1}
    needs = GapNeeds(headcount_gap=1, role_gaps=roles, skill_gaps=skills)
    roles[RN] = 9
    skills.clear()

    assert needs == GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={ICU: 1})
    assert hash(needs) == hash(GapNeeds(headcount_gap=1, role_gaps={RN: 1}, skill_gaps={ICU: 1}))
    with pytest.raises(TypeError):
        needs.role_gaps[RN] = 0  # type: ignore[index]
