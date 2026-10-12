"""decide_status() and gap_closed(): docs/workflow.md sections 4.2 and 5.3."""

from dataclasses import FrozenInstanceError
from itertools import product

import pytest

from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    CaseStatus,
)
from app.domain.workflow.case_status import CaseFacts, GapFiller, decide_status, gap_closed
from app.domain.workflow.transitions import ALLOWED_TRANSITIONS

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2

EXECUTING = CaseStatus.EXECUTING
WAITING_APPROVAL = CaseStatus.WAITING_APPROVAL
WAITING_RESPONSE = CaseStatus.WAITING_RESPONSE
OUTREACH = CaseStatus.OUTREACH


def person(staff_id: int, role_id: int = RN, *skills: int) -> GapFiller:
    return GapFiller(staff_id=staff_id, role_id=role_id, skill_ids=frozenset(skills))


def facts(
    *,
    by_assigned: bool = False,
    with_pending: bool = False,
    open_offer: bool = False,
    uncontacted: bool = False,
    pending: bool = False,
    paused: bool = False,
) -> CaseFacts:
    return CaseFacts(
        gap_closed_by_assigned=by_assigned,
        gap_closed_with_pending=with_pending,
        has_open_offer=open_offer,
        has_uncontacted_candidate=uncontacted,
        has_pending_approval=pending,
        has_paused_offer=paused,
    )


def every_valid_facts() -> list[CaseFacts]:
    return [
        facts(
            by_assigned=by_assigned,
            with_pending=with_pending,
            open_offer=open_offer,
            uncontacted=uncontacted,
            pending=pending,
            paused=paused,
        )
        for by_assigned, with_pending, open_offer, uncontacted, pending, paused in product(
            [True, False], repeat=6
        )
        if with_pending or not by_assigned
    ]


# --------------------------------------------------------------------------- #
# decide_status
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("case_facts", "expected"),
    [
        # 1. Assigned staff close the gap: nothing else matters
        (facts(by_assigned=True, with_pending=True), EXECUTING),
        (
            facts(
                by_assigned=True,
                with_pending=True,
                open_offer=True,
                uncontacted=True,
                pending=True,
                paused=True,
            ),
            EXECUTING,
        ),
        # 2. Pending approvals cover the rest, with or without open offers
        (facts(with_pending=True, pending=True), WAITING_APPROVAL),
        (
            facts(with_pending=True, pending=True, open_offer=True, uncontacted=True),
            WAITING_APPROVAL,
        ),
        # 3. An open offer
        (facts(open_offer=True), WAITING_RESPONSE),
        (facts(open_offer=True, uncontacted=True, pending=True, paused=True), WAITING_RESPONSE),
        # 4. Somebody left to contact: waiting never stops the next wave
        (facts(uncontacted=True), OUTREACH),
        (facts(uncontacted=True, pending=True, paused=True), OUTREACH),
        # 5. Nobody left to contact, an approval is pending: keep waiting for it
        (facts(pending=True), WAITING_APPROVAL),
        (facts(pending=True, paused=True), WAITING_APPROVAL),
        # 6. Nobody left to contact, only a paused offer: keep waiting for it
        (facts(paused=True), WAITING_RESPONSE),
        # 7. Nothing to wait for: OUTREACH, where contact_candidate hands the case off
        (facts(), OUTREACH),
    ],
)
def test_first_rule_that_holds_is_the_answer(case_facts: CaseFacts, expected: CaseStatus) -> None:
    assert decide_status(case_facts) is expected


@pytest.mark.parametrize("open_offer", [True, False])
def test_assigned_cannot_close_a_gap_that_assigned_plus_pending_leaves_open(
    open_offer: bool,
) -> None:
    """The pending group contains the assigned group, so this would be a loader bug."""
    with pytest.raises(ValueError, match="also closed with the pending"):
        facts(by_assigned=True, with_pending=False, open_offer=open_offer)


def test_decide_status_never_returns_a_stopped_status() -> None:
    """MANUAL_HANDOFF and FAILED are not computed: a handler or D11 sets them."""
    results = {decide_status(case_facts) for case_facts in every_valid_facts()}

    assert results == {EXECUTING, WAITING_APPROVAL, WAITING_RESPONSE, OUTREACH}
    assert results.isdisjoint(AUTOMATION_STOPPED_STATUSES)


@pytest.mark.parametrize("current", sorted(WAITING_CASE_STATUSES))
def test_every_answer_is_reachable_from_both_wait_points(current: CaseStatus) -> None:
    """The one move without an edge, WAITING_RESPONSE to EXECUTING, goes by WAITING_APPROVAL."""
    for case_facts in every_valid_facts():
        target = decide_status(case_facts)
        if target is current:
            continue
        if current is WAITING_RESPONSE and target is EXECUTING:
            assert WAITING_APPROVAL in ALLOWED_TRANSITIONS[current]
            assert EXECUTING in ALLOWED_TRANSITIONS[WAITING_APPROVAL]
        else:
            assert target in ALLOWED_TRANSITIONS[current], (current, target)


def test_a_case_with_something_to_wait_for_and_nobody_to_contact_does_not_enter_outreach() -> None:
    """A parked case keeps its wait point, so a recompute with no news writes nothing."""
    for case_facts in every_valid_facts():
        waits_for_something = case_facts.has_pending_approval or case_facts.has_paused_offer
        if waits_for_something and not case_facts.has_uncontacted_candidate:
            assert decide_status(case_facts) is not OUTREACH


def test_facts_cannot_be_mutated() -> None:
    case_facts = facts(open_offer=True)

    with pytest.raises(FrozenInstanceError):
        case_facts.has_open_offer = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# gap_closed
# --------------------------------------------------------------------------- #
def closed(
    fillers: list[GapFiller],
    *,
    headcount: int = 1,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> bool:
    return gap_closed(
        headcount_gap=headcount,
        role_gaps={RN: 1} if roles is None else roles,
        skill_gaps=skills or {},
        fillers=fillers,
    )


def test_golden_case_gap_is_closed_by_one_rn() -> None:
    assert not closed([])
    assert closed([person(201, RN, ICU, BLS)])


def test_wrong_role_fills_headcount_but_not_the_role_gap() -> None:
    assert not closed([person(900, HEAD_NURSE)])


def test_headcount_only_gap_accepts_any_role() -> None:
    """Which roles may fill headcount is a Hard Rule for the caller, not this count."""
    assert closed([person(900, HEAD_NURSE)], roles={})


def test_skill_gap_needs_someone_who_holds_the_skill() -> None:
    assert not closed([person(202, RN, BLS)], skills={ICU: 1})
    assert closed([person(203, RN, ICU)], skills={ICU: 1})


def test_one_person_counts_toward_every_gap_they_match() -> None:
    """A + B missing: one person with both, or one person each (Q46)."""
    both = {ICU: 1, BLS: 1}

    assert closed([person(201, RN, ICU, BLS)], skills=both)
    assert closed([person(203, RN, ICU), person(202, RN, BLS)], skills=both)
    assert not closed([person(203, RN, ICU)], skills=both)


@pytest.mark.parametrize(("people", "expected"), [(0, False), (1, False), (2, True), (3, True)])
def test_headcount_gap_of_two_needs_two_people(people: int, expected: bool) -> None:
    group = [person(200 + index) for index in range(people)]

    assert closed(group, headcount=2, roles={RN: 2}) is expected


def test_enough_people_without_the_skill_do_not_close_the_gap() -> None:
    def two_icu(group: list[GapFiller]) -> bool:
        return closed(group, headcount=2, roles={RN: 2}, skills={ICU: 2})

    assert not two_icu([person(203, RN, ICU), person(202, RN, BLS)])
    assert two_icu([person(203, RN, ICU), person(201, RN, ICU, BLS)])


def test_skill_gap_can_need_more_people_than_the_headcount_gap() -> None:
    """Headcount is covered by one person, but two ICU nurses are still missing."""
    assert not closed([person(203, RN, ICU)], roles={}, skills={ICU: 2})
    assert closed([person(203, RN, ICU), person(201, RN, ICU)], roles={}, skills={ICU: 2})


def test_zero_entries_ask_for_nothing() -> None:
    assert closed([], headcount=0, roles={RN: 0}, skills={ICU: 0})


def test_the_same_person_listed_twice_counts_once() -> None:
    same = person(201, RN, ICU)

    assert not closed([same, same], headcount=2, roles={RN: 2})


def test_fillers_can_be_a_one_shot_iterator() -> None:
    assert gap_closed(
        headcount_gap=1, role_gaps={RN: 1}, skill_gaps={}, fillers=iter([person(201)])
    )


@pytest.mark.parametrize("kind", ["headcount", "role", "skill"])
def test_negative_gap_counts_are_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        gap_closed(
            headcount_gap=-1 if kind == "headcount" else 1,
            role_gaps={RN: -1 if kind == "role" else 1},
            skill_gaps={ICU: -1 if kind == "skill" else 1},
            fillers=[],
        )


def test_gap_mappings_are_not_mutated() -> None:
    roles, skills = {RN: 1}, {ICU: 1}

    gap_closed(headcount_gap=1, role_gaps=roles, skill_gaps=skills, fillers=[person(201, RN, ICU)])

    assert (roles, skills) == ({RN: 1}, {ICU: 1})
