"""case_facts_service on the seeded Golden Case (docs/workflow.md, sections 4.1 and 5.3)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    Role,
    RosterAssignment,
    StaffingCase,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    CaseStatus,
    OutreachStatus,
    RosterStatus,
)
from app.domain.workflow.case_status import CaseFacts
from app.services import case_facts_service
from app.services.gap_service import GapNotFoundError
from tests.integration.case_rows import (
    DAY_SHIFT,
    approval,
    assign,
    cancel_roster,
    make_case,
    make_plan,
    offer,
    record_gap,
    replacement,
    safety,
    short_case,
)


def _facts(db: Session, case: StaffingCase) -> tuple[bool, bool, bool]:
    facts = case_facts_service.load_case_facts(db, case)
    assert isinstance(facts, CaseFacts)
    return (facts.gap_closed_by_assigned, facts.gap_closed_with_pending, facts.has_open_offer)


# --------------------------------------------------------------------------- #
# One RN short (the Golden Case after 105 left)
# --------------------------------------------------------------------------- #
def test_case_with_no_candidate_rows_has_nothing(seeded: Session) -> None:
    case, _ = short_case(seeded)

    assert _facts(seeded, case) == (False, False, False)


def test_a_sent_offer_is_an_open_offer(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])

    assert _facts(seeded, case) == (False, False, True)


@pytest.mark.parametrize(
    "status", [status for status in OutreachStatus if status is not OutreachStatus.SENT]
)
def test_only_sent_offers_are_open(seeded: Session, status: OutreachStatus) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], status)

    assert case_facts_service.has_open_offer(seeded, case.id) is False


def test_a_pending_approval_closes_the_gap_only_with_pending(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    approval(seeded, case, items[201])

    assert _facts(seeded, case) == (False, True, False)


def test_an_approved_candidate_on_the_roster_closes_the_gap(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    assign(seeded, case, items[201])

    assert _facts(seeded, case) == (True, True, False)


def test_an_approved_candidate_without_a_roster_row_is_not_assigned(seeded: Session) -> None:
    """Section 4.1: "on the roster" is read from ROSTER_ASSIGNMENT, not from the approval."""
    case, items = short_case(seeded)
    approval(seeded, case, items[201], approved=True)

    assert _facts(seeded, case) == (False, False, False)


def test_a_roster_row_without_an_approval_of_this_case_is_not_assigned(
    seeded: Session,
) -> None:
    case, items = short_case(seeded)
    replacement(seeded, items[201])

    assert _facts(seeded, case) == (False, False, False)


def test_a_rejected_approval_counts_nowhere(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.CANCELLED)
    approval(seeded, case, items[201], approved=False)

    assert _facts(seeded, case) == (False, False, False)


def test_an_accepted_reserve_without_an_approval_request_counts_nowhere(
    seeded: Session,
) -> None:
    """Q28: the reserve accepted after the gap was covered and has no request yet."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    approval(seeded, case, items[201])
    offer(seeded, case, items[202], OutreachStatus.ACCEPTED)

    assert _facts(seeded, case) == (False, True, False)


# --------------------------------------------------------------------------- #
# Two short, and a skill gap
# --------------------------------------------------------------------------- #
def test_gap_of_two_needs_two_candidates(seeded: Session) -> None:
    case, items = short_case(seeded, 104, 105)
    approval(seeded, case, items[201])
    assert _facts(seeded, case) == (False, False, False)

    approval(seeded, case, items[202])
    assert _facts(seeded, case) == (False, True, False)


def test_one_assigned_and_one_pending_close_a_gap_of_two_only_with_pending(
    seeded: Session,
) -> None:
    case, items = short_case(seeded, 104, 105)
    assign(seeded, case, items[201])
    approval(seeded, case, items[202])
    offer(seeded, case, items[203])

    assert _facts(seeded, case) == (False, True, False)


def test_two_assigned_close_a_gap_of_two(seeded: Session) -> None:
    case, items = short_case(seeded, 104, 105)
    assign(seeded, case, items[201])
    assign(seeded, case, items[202])

    assert _facts(seeded, case) == (True, True, False)


def test_skill_gap_is_not_closed_by_a_candidate_without_the_skill(seeded: Session) -> None:
    """101 held ICU. 202 has only BLS, 203 has ICU."""
    case, items = short_case(seeded, 101)
    approval(seeded, case, items[202])
    assert _facts(seeded, case) == (False, False, False)

    approval(seeded, case, items[203])
    assert _facts(seeded, case) == (False, True, False)


def test_gap_is_the_one_stored_with_the_case_not_the_shift_today(seeded: Session) -> None:
    """Q19: a later shortage on the shift belongs to the next window, not this case."""
    case, items = short_case(seeded)
    assign(seeded, case, items[201])

    cancel_roster(seeded, 104)

    assert _facts(seeded, case) == (True, True, False)


# --------------------------------------------------------------------------- #
# Paused offers: the candidate accepted another case (Q29)
# --------------------------------------------------------------------------- #
def _other_case_accepted_by(
    db: Session, staff_id: int, status: CaseStatus = CaseStatus.WAITING_APPROVAL
) -> tuple[StaffingCase, CandidateItem, CandidateOutreach]:
    other = make_case(db, status, shift_id=DAY_SHIFT)
    item = make_plan(db, other, (staff_id,))[staff_id]
    accepted = offer(db, other, item, OutreachStatus.ACCEPTED)
    return other, item, accepted


def test_offer_is_paused_while_its_candidate_waits_on_another_case(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    _other_case_accepted_by(seeded, 201)

    assert case_facts_service.staff_waiting_on_another_case(seeded, case.id, {201}) == {201}
    assert _facts(seeded, case) == (False, False, False)


def test_one_open_offer_is_enough_when_another_is_paused(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    offer(seeded, case, items[202])
    _other_case_accepted_by(seeded, 201)

    assert _facts(seeded, case) == (False, False, True)


def test_pending_approval_on_the_other_case_still_pauses(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other, item, _ = _other_case_accepted_by(seeded, 201)
    approval(seeded, other, item)

    assert case_facts_service.has_open_offer(seeded, case.id) is False


def test_offer_opens_again_when_the_other_case_drops_the_candidate(seeded: Session) -> None:
    """Safety failed or the approver said no: the other offer becomes CANCELLED."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    _, _, accepted = _other_case_accepted_by(seeded, 201)
    assert case_facts_service.has_open_offer(seeded, case.id) is False

    accepted.status = OutreachStatus.CANCELLED
    seeded.flush()

    assert case_facts_service.has_open_offer(seeded, case.id) is True


def test_offer_is_not_paused_once_the_other_case_approved_the_candidate(
    seeded: Session,
) -> None:
    """The outcome is known. An offer that clashes is cancelled by that approval itself."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other, item, _ = _other_case_accepted_by(seeded, 201)
    approval(seeded, other, item, approved=True)

    assert case_facts_service.has_open_offer(seeded, case.id) is True


@pytest.mark.parametrize("stopped", sorted(AUTOMATION_STOPPED_STATUSES))
def test_an_accepted_offer_on_a_stopped_case_does_not_pause(
    seeded: Session, stopped: CaseStatus
) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    _other_case_accepted_by(seeded, 201, stopped)

    assert case_facts_service.has_open_offer(seeded, case.id) is True


def test_a_sent_offer_on_another_case_does_not_pause(seeded: Session) -> None:
    """Holding two unanswered offers is allowed; only an accepted one pauses the rest."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other = make_case(seeded, shift_id=DAY_SHIFT)
    offer(seeded, other, make_plan(seeded, other, (201,))[201])

    assert case_facts_service.has_open_offer(seeded, case.id) is True


def test_the_candidates_own_accepted_offer_on_this_case_does_not_pause_it(
    seeded: Session,
) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)

    assert case_facts_service.staff_waiting_on_another_case(seeded, case.id, {201}) == set()


def test_waiting_staff_is_limited_to_the_requested_ids(seeded: Session) -> None:
    case, _ = short_case(seeded)
    _other_case_accepted_by(seeded, 201)

    assert case_facts_service.staff_waiting_on_another_case(seeded, case.id, {202, 203}) == set()
    assert case_facts_service.staff_waiting_on_another_case(seeded, case.id, set()) == set()


# --------------------------------------------------------------------------- #
# Scope and behaviour
# --------------------------------------------------------------------------- #
def test_rows_of_another_case_do_not_leak_in(seeded: Session) -> None:
    case, _ = short_case(seeded)
    other = make_case(seeded, shift_id=DAY_SHIFT)
    other_items = make_plan(seeded, other, (201, 202))
    offer(seeded, other, other_items[201])
    approval(seeded, other, other_items[202])

    assert _facts(seeded, case) == (False, False, False)


def test_case_without_a_gap_row_raises(seeded: Session) -> None:
    case = make_case(seeded)

    with pytest.raises(GapNotFoundError, match=str(case.id)):
        case_facts_service.load_case_facts(seeded, case)


def test_loader_does_not_flush_or_commit(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = production_seeded
    case, items = short_case(db)
    offer(db, case, items[201])

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Reading the facts of a case must not flush or commit")

    monkeypatch.setattr(db, "commit", forbidden)
    monkeypatch.setattr(db, "flush", forbidden)
    assert _facts(db, case) == (False, False, True)


def test_loader_works_with_production_session_settings(production_seeded: Session) -> None:
    db = production_seeded
    assert db.autoflush is False
    case, items = short_case(db, 104, 105)
    assign(db, case, items[201])
    approval(db, case, items[202])
    offer(db, case, items[203])

    assert _facts(db, case) == (False, True, False)


# --------------------------------------------------------------------------- #
# Review fixes: COMPLETED rows, a self-sufficient "waiting" rule, the wait facts
# --------------------------------------------------------------------------- #
def test_a_completed_replacement_row_still_counts_as_assigned(seeded: Session) -> None:
    """The shift started and the row was closed while the case waits on a second approval."""
    case, items = short_case(seeded, 104, 105)
    assign(seeded, case, items[201])
    approval(seeded, case, items[202])
    row = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
        )
    ).one()
    row.status = RosterStatus.COMPLETED
    seeded.flush()

    assert _facts(seeded, case) == (False, True, False)


def test_a_cancelled_replacement_row_does_not_count(seeded: Session) -> None:
    case, items = short_case(seeded)
    assign(seeded, case, items[201])
    row = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
        )
    ).one()
    row.status = RosterStatus.CANCELLED
    seeded.flush()

    assert _facts(seeded, case)[:2] == (False, False)


def test_a_candidate_rejected_on_the_other_case_is_free_even_if_that_offer_stayed_accepted(
    seeded: Session,
) -> None:
    """The other case should cancel the offer, but this rule does not depend on that write."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other, item, accepted = _other_case_accepted_by(seeded, 201)
    approval(seeded, other, item, approved=False)
    assert accepted.status is OutreachStatus.ACCEPTED

    assert case_facts_service.staff_waiting_on_another_case(seeded, case.id, {201}) == set()
    assert case_facts_service.has_open_offer(seeded, case.id) is True


def test_a_candidate_who_failed_safety_on_the_other_case_is_free(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other, item, _ = _other_case_accepted_by(seeded, 201)
    safety(seeded, other, item, passed=False)

    assert case_facts_service.has_open_offer(seeded, case.id) is True


def test_a_candidate_who_passed_safety_on_the_other_case_still_waits(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other, item, _ = _other_case_accepted_by(seeded, 201)
    safety(seeded, other, item, passed=True)
    approval(seeded, other, item)

    assert case_facts_service.has_open_offer(seeded, case.id) is False


def test_plan_with_someone_never_contacted_is_reported(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.REJECTED)
    offer(seeded, case, items[202], OutreachStatus.TIMEOUT)
    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is True

    offer(seeded, case, items[203], OutreachStatus.CANCELLED)
    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is False


def test_uncontacted_looks_at_the_latest_plan_and_only_at_offers_of_this_case(
    seeded: Session,
) -> None:
    case, old_items = short_case(seeded)
    for item in old_items.values():
        offer(seeded, case, item, OutreachStatus.REJECTED)
    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is False

    # A newer plan of the same case: its items have no offer yet
    make_plan(seeded, case, (201,))
    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is True

    # An offer of another case to the same person does not count as contacted here
    other = make_case(seeded, shift_id=DAY_SHIFT)
    offer(seeded, other, make_plan(seeded, other, (201,))[201])
    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is True


def test_case_without_a_plan_has_nobody_to_contact(seeded: Session) -> None:
    case = make_case(seeded)
    cancel_roster(seeded, 105)
    record_gap(seeded, case)

    assert case_facts_service.load_case_facts(seeded, case).has_uncontacted_candidate is False


def test_pending_and_paused_facts(seeded: Session) -> None:
    """Gap of two: one pending approval and one paused offer, neither closes the gap."""
    case, items = short_case(seeded, 104, 105)
    approval(seeded, case, items[201])
    offer(seeded, case, items[202])
    _other_case_accepted_by(seeded, 202)

    facts = case_facts_service.load_case_facts(seeded, case)

    assert (facts.gap_closed_by_assigned, facts.gap_closed_with_pending) == (False, False)
    assert facts.has_pending_approval is True
    assert facts.has_paused_offer is True
    assert facts.has_open_offer is False
    assert facts.has_uncontacted_candidate is True  # 203


@pytest.mark.parametrize(
    "read",
    [
        lambda db, case: case_facts_service.load_case_facts(db, case),
        lambda db, case: case_facts_service.has_open_offer(db, case.id),
        lambda db, case: case_facts_service.staff_waiting_on_another_case(db, case.id, {201}),
    ],
    ids=["load_case_facts", "has_open_offer", "staff_waiting_on_another_case"],
)
def test_reads_do_not_flush_unrelated_pending_work_with_autoflush_on(
    seeded: Session, read: object
) -> None:
    """The `seeded` session autoflushes. A read here must not send the caller's rows."""
    assert seeded.autoflush is True
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    pending = Role(name="NOT_FLUSHED_BY_A_READ")
    seeded.add(pending)

    read(seeded, case)  # type: ignore[operator]

    assert pending in seeded.new
    assert pending.id is None
