"""interval_shortage() and choose_kept(): what a late arrival leaves of the gap
(docs/workflow.md, section 6.24).

The gap runs 02:00 to 08:00 and needs 2 RNs (one of them with ICU). One hour is 3600 seconds.
"""

from datetime import datetime, timedelta

import pytest

from app.core.clock import APP_TIMEZONE
from app.domain.workflow.case_status import (
    GapFiller,
    IntervalGap,
    choose_kept,
    interval_shortage,
    intervals_closed,
)

RN, HEAD_NURSE = 1, 2
ICU = 1
HOUR = 3600
MIDNIGHT = datetime(2026, 10, 10, 0, 0, tzinfo=APP_TIMEZONE)


def at(hour: int) -> datetime:
    return MIDNIGHT + timedelta(hours=hour)


def person(
    staff_id: int,
    *,
    start: int | None = None,
    end: int | None = None,
    role: int = RN,
    skills: frozenset[int] = frozenset(),
) -> GapFiller:
    return GapFiller(
        staff_id=staff_id,
        role_id=role,
        skill_ids=skills,
        start_at=None if start is None else at(start),
        end_at=None if end is None else at(end),
    )


def slice_of(
    start: int,
    end: int,
    *,
    headcount: int = 2,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> IntervalGap:
    return IntervalGap(
        start_at=at(start),
        end_at=at(end),
        headcount_gap=headcount,
        role_gaps=roles or {},
        skill_gaps=skills or {},
    )


GAP = [slice_of(2, 8, roles={RN: 2}, skills={ICU: 1})]


# ---- interval_shortage -------------------------------------------------------------------------


def test_nobody_leaves_the_whole_gap_open() -> None:
    # 6 hours x (2 headcount + 2 RNs + 1 ICU)
    assert interval_shortage(GAP, []) == 6 * HOUR * 5


def test_a_person_for_the_whole_slice_lowers_it_by_their_headcount_role_and_skills() -> None:
    icu_nurse = person(1, skills=frozenset({ICU}))
    assert interval_shortage(GAP, [icu_nurse]) == 6 * HOUR * 2  # one more RN is missing


def test_a_closed_gap_has_no_shortage_and_agrees_with_intervals_closed() -> None:
    fillers = [person(1, skills=frozenset({ICU})), person(2)]
    assert interval_shortage(GAP, fillers) == 0
    assert intervals_closed(GAP, fillers)
    assert not intervals_closed(GAP, fillers[:1])


def test_a_person_who_covers_part_of_the_slice_counts_only_in_the_pieces_they_cover() -> None:
    # 02:00-05:00 is covered by two people, 05:00-08:00 by one
    fillers = [person(1, skills=frozenset({ICU})), person(2, start=2, end=5)]
    assert interval_shortage(GAP, fillers) == 3 * HOUR * 2


def test_a_person_only_counts_where_they_are_present_for_the_whole_piece() -> None:
    # Starting at 04:00 cuts the slice in two: nothing counts before it
    assert interval_shortage([slice_of(2, 8, headcount=1)], [person(1, start=4)]) == 2 * HOUR


def test_the_same_person_twice_counts_once() -> None:
    gap = [slice_of(2, 8, headcount=2)]
    assert interval_shortage(gap, [person(1), person(1)]) == 6 * HOUR


def test_the_slices_add_up() -> None:
    gap = [slice_of(2, 4, headcount=1), slice_of(4, 8, headcount=2)]
    assert interval_shortage(gap, []) == 2 * HOUR * 1 + 4 * HOUR * 2


def test_a_person_outside_the_slice_changes_nothing() -> None:
    gap = [slice_of(4, 8, headcount=1)]
    assert interval_shortage(gap, [person(1, start=0, end=4)]) == 4 * HOUR


# ---- choose_kept -------------------------------------------------------------------------------


def test_nothing_is_kept_when_the_base_already_closes_the_gap() -> None:
    base = [person(1, skills=frozenset({ICU})), person(2)]
    assert choose_kept(GAP, base, [("a", person(3)), ("b", person(4))]) == set()


def test_candidates_that_lower_the_shortage_are_kept_until_the_gap_closes() -> None:
    base = [person(1, skills=frozenset({ICU}))]
    candidates = [("a", person(2)), ("b", person(3)), ("c", person(4))]
    assert choose_kept(GAP, base, candidates) == {"a"}


def test_a_tie_goes_to_the_earlier_candidate() -> None:
    base = [person(1, skills=frozenset({ICU}))]
    assert choose_kept(GAP, base, [("first", person(2)), ("second", person(3))]) == {"first"}
    assert choose_kept(GAP, base, [("second", person(3)), ("first", person(2))]) == {"second"}


def test_coverage_comes_before_order_so_a_late_better_candidate_beats_an_early_one() -> None:
    # 1 RN is missing from 02:00 to 08:00. The first candidate covers only the first
    # half, the second covers all of it: the second is kept, the first has nothing left to add
    gap = [slice_of(2, 8, headcount=1)]
    candidates = [("first_half", person(2, start=0, end=5)), ("whole", person(3))]
    assert choose_kept(gap, [], candidates) == {"whole"}


def test_two_partial_candidates_are_both_kept_when_they_cover_the_gap_together() -> None:
    gap = [slice_of(2, 8, headcount=1)]
    candidates = [("first_half", person(2, start=0, end=5)), ("second_half", person(3, start=5))]
    assert choose_kept(gap, [], candidates) == {"first_half", "second_half"}


def test_the_missing_second_half_is_filled_by_the_offer_for_it_not_the_first_half_request() -> None:
    # The base person covers 02:00-05:00; only 05:00-08:00 is still open
    gap = [slice_of(2, 8, headcount=1)]
    base = [person(1, start=0, end=5)]
    candidates = [("request_first_half", person(2, start=0, end=5)), ("offer", person(3, start=5))]
    assert choose_kept(gap, base, candidates) == {"offer"}


def test_a_candidate_with_the_missing_role_is_kept_over_one_that_only_adds_headcount() -> None:
    gap = [slice_of(2, 8, headcount=1, roles={HEAD_NURSE: 1})]
    candidates = [("rn", person(2)), ("head", person(3, role=HEAD_NURSE))]
    assert choose_kept(gap, [], candidates) == {"head"}


def test_the_base_and_the_candidates_are_not_changed() -> None:
    base = [person(1)]
    candidates = [("a", person(2))]
    choose_kept(GAP, base, candidates)
    assert base == [person(1)] and candidates == [("a", person(2))]


@pytest.mark.parametrize("candidates", [[], [("a", person(2))]])
def test_a_candidate_who_lowers_nothing_is_never_kept(
    candidates: list[tuple[str, GapFiller]],
) -> None:
    gap = [slice_of(2, 8, headcount=0, skills={ICU: 1})]
    assert choose_kept(gap, [], candidates) == set()
