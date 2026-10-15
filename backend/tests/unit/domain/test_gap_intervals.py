"""Gap time slices and the per-slice closing rule (round 4 PR T3, workflow.md 6.20).

Example used throughout: the night shift runs 00:00 to 08:00, the gap is
measured at 02:00, and the shift needs 3 RNs and 1 ICU nurse.
"""

from datetime import datetime, timedelta

import pytest

from app.core.clock import APP_TIMEZONE
from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import CountGap, GapResult, calculate_gap
from app.domain.workflow.case_status import GapFiller, IntervalGap, intervals_closed

RN, HEAD_NURSE = 1, 2
ICU = 1
MIDNIGHT = datetime(2026, 10, 10, 0, 0, tzinfo=APP_TIMEZONE)


def at(hour: int) -> datetime:
    return MIDNIGHT + timedelta(hours=hour)


def member(
    staff_id: int,
    *,
    start: int | None = None,
    end: int | None = None,
    skills: frozenset[int] = frozenset(),
    status: RosterStatus = RosterStatus.ASSIGNED,
) -> RosterMember:
    return RosterMember(
        staff_id=staff_id,
        shift_id=1,
        status=status,
        role_id=RN,
        skill_ids=skills,
        start_at=None if start is None else at(start),
        end_at=None if end is None else at(end),
    )


def gap(roster: list[RosterMember], *, window: tuple[int, int] | None = (2, 8)) -> GapResult:
    return calculate_gap(
        shift_id=1,
        required_staff=3,
        minimum_staff=3,
        preserve_minimum_staffing=True,
        required_roles={RN: 3},
        required_skills={ICU: 1},
        roster=roster,
        window=None if window is None else (at(window[0]), at(window[1])),
    )


def test_a_shift_without_moves_has_one_slice_with_the_old_counts() -> None:
    roster = [member(101, start=0, end=8, skills=frozenset({ICU})), member(102, start=0, end=8)]

    sliced = gap(roster)
    whole = gap(roster, window=None)

    assert [(i.start_at, i.end_at) for i in sliced.intervals] == [(at(2), at(8))]
    assert sliced.evaluated_from == at(2)
    assert (sliced.headcount_gap, dict(sliced.role_gaps), dict(sliced.skill_gaps)) == (
        whole.headcount_gap,
        dict(whole.role_gaps),
        dict(whole.skill_gaps),
    )
    assert sliced.has_gap is whole.has_gap is True


def test_a_person_counts_only_inside_their_own_interval() -> None:
    # 103 was moved out at 04:00: their row ends there
    roster = [
        member(101, start=0, end=8, skills=frozenset({ICU})),
        member(102, start=0, end=8),
        member(103, start=0, end=4),
    ]

    result = gap(roster)

    assert [(i.start_at, i.end_at, i.headcount) for i in result.intervals] == [
        (at(2), at(4), CountGap(3, 3)),
        (at(4), at(8), CountGap(3, 2)),
    ]
    assert result.has_gap is True


def test_the_summary_is_the_worst_slice_of_each_dimension_never_a_sum() -> None:
    # Short of one RN from 02:00 to 04:00 and of the ICU nurse from 06:00 on
    roster = [
        member(101, start=0, end=6, skills=frozenset({ICU})),
        member(102, start=0, end=8),
        member(103, start=4, end=8),
    ]

    result = gap(roster)

    assert [i.headcount.gap_count for i in result.intervals] == [1, 0, 1]
    assert [i.skill_gaps[ICU].gap_count for i in result.intervals] == [0, 0, 1]
    assert result.headcount_gap == 1
    assert result.role_gaps[RN] == CountGap(3, 2)
    assert result.skill_gaps[ICU] == CountGap(1, 0)


def test_neighbour_slices_with_equal_counts_are_joined() -> None:
    # 103 hands over to 104 at 05:00: the count never changes
    roster = [
        member(101, start=0, end=8, skills=frozenset({ICU})),
        member(102, start=0, end=8),
        member(103, start=0, end=5),
        member(104, start=5, end=8),
    ]

    result = gap(roster)

    assert [(i.start_at, i.end_at) for i in result.intervals] == [(at(2), at(8))]
    assert result.has_gap is False


def test_cancelled_rows_and_time_before_the_window_do_not_count() -> None:
    roster = [
        member(101, start=0, end=8, skills=frozenset({ICU})),
        member(102, start=0, end=8),
        member(103, start=0, end=8, status=RosterStatus.CANCELLED),
        # Worked only before the gap was measured at 02:00
        member(104, start=0, end=2),
    ]

    result = gap(roster)

    assert [(i.start_at, i.end_at, i.headcount) for i in result.intervals] == [
        (at(2), at(8), CountGap(3, 2))
    ]


def test_an_empty_window_has_no_slice_and_no_gap() -> None:
    result = gap([member(101, start=0, end=8)], window=(8, 8))

    assert result.intervals == ()
    assert result.has_gap is False


def test_the_same_person_with_two_rows_counts_once_per_slice() -> None:
    roster = [
        member(101, start=0, end=4, skills=frozenset({ICU})),
        member(101, start=3, end=8, skills=frozenset({ICU})),
    ]

    result = gap(roster)

    assert [i.headcount.current_count for i in result.intervals] == [1]


def test_conflicting_role_or_skills_of_one_person_still_raise() -> None:
    with pytest.raises(ValueError, match="Conflicting coverage"):
        gap([member(101, skills=frozenset({ICU})), member(101)])


# ----------------------------------------------------------------- closing rule


def filler(staff_id: int, start: int | None = None, end: int | None = None) -> GapFiller:
    return GapFiller(
        staff_id=staff_id,
        role_id=RN,
        skill_ids=frozenset(),
        start_at=None if start is None else at(start),
        end_at=None if end is None else at(end),
    )


TWO_SHORT_SLICES = (
    IntervalGap(start_at=at(0), end_at=at(2), headcount_gap=1),
    IntervalGap(start_at=at(2), end_at=at(4), headcount_gap=0),
    IntervalGap(start_at=at(4), end_at=at(8), headcount_gap=1),
)


def test_filling_one_short_slice_of_two_does_not_close_the_gap() -> None:
    # The summary is 1 and one person was found, but only for 04:00 to 08:00
    assert intervals_closed(TWO_SHORT_SLICES, [filler(201, start=4, end=8)]) is False


def test_part_of_a_slice_does_not_close_that_slice() -> None:
    assert (
        intervals_closed(TWO_SHORT_SLICES, [filler(201, start=0, end=1), filler(202, 4, 8)])
        is False
    )


def test_every_short_slice_covered_closes_the_gap() -> None:
    assert intervals_closed(TWO_SHORT_SLICES, [filler(201, 0, 2), filler(202, 4, 8)]) is True
    # A whole-shift filler (no times) covers every slice
    assert intervals_closed(TWO_SHORT_SLICES, [filler(203)]) is True


def test_two_people_in_relay_close_one_slice() -> None:
    one_slice = (IntervalGap(start_at=at(0), end_at=at(8), headcount_gap=1),)

    assert intervals_closed(one_slice, [filler(201, 0, 3), filler(202, 3, 8)]) is True
    assert intervals_closed(one_slice, [filler(201, 0, 3), filler(202, 4, 8)]) is False


def test_a_slice_must_start_before_it_ends() -> None:
    with pytest.raises(ValueError):
        IntervalGap(start_at=at(2), end_at=at(2), headcount_gap=1)
