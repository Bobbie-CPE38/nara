"""Wave targets and their fill order (round 1 contract, section 8.3)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import SelectionType, TargetType
from app.domain.staffing.wave_targets import (
    TargetCredit,
    covers,
    elementary_slices,
    fill_targets,
    fill_targets_by_slice,
    is_short,
    wave_target,
)
from app.domain.workflow.case_status import GapFiller, IntervalGap

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2

P, R = SelectionType.PRIMARY, SelectionType.RESERVE


def person(staff_id: int, *skills: int, role: int = RN) -> GapFiller:
    return GapFiller(staff_id=staff_id, role_id=role, skill_ids=frozenset(skills))


def skill(skill_id: int, kind: SelectionType) -> TargetCredit:
    return TargetCredit(TargetType.SKILL, kind, skill_id=skill_id)


def role(role_id: int, kind: SelectionType) -> TargetCredit:
    return TargetCredit(TargetType.ROLE, kind, role_id=role_id)


def headcount(kind: SelectionType) -> TargetCredit:
    return TargetCredit(TargetType.HEADCOUNT, kind)


@pytest.mark.parametrize(("gap", "target"), [(0, 0), (1, 2), (2, 3), (9, 10), (10, 11), (11, 13)])
def test_wave_target_is_the_gap_plus_ten_percent_rounded_up(gap: int, target: int) -> None:
    assert wave_target(gap) == target


def test_wave_target_rejects_a_negative_gap() -> None:
    with pytest.raises(ValueError):
        wave_target(-1)


def test_contract_example() -> None:
    result = fill_targets(
        headcount_gap=2,
        role_gaps={RN: 2},
        skill_gaps={ICU: 1},
        candidates=[person(1, ICU), person(2, ICU), person(3), person(4)],
    )

    assert list(result) == [1, 2, 3]
    assert result[1] == (skill(ICU, P), role(RN, P), headcount(P))
    assert result[2] == (skill(ICU, R), role(RN, P), headcount(P))
    assert result[3] == (role(RN, R), headcount(R))


def test_golden_case() -> None:
    result = fill_targets(
        headcount_gap=1,
        role_gaps={RN: 1},
        skill_gaps={},
        candidates=[person(201), person(202)],
    )

    assert result == {
        201: (role(RN, P), headcount(P)),
        202: (role(RN, R), headcount(R)),
    }


def test_a_target_at_zero_gives_no_row() -> None:
    result = fill_targets(
        headcount_gap=0,
        role_gaps={RN: 1},
        skill_gaps={ICU: 2},
        candidates=[person(1, ICU), person(2, ICU), person(3, ICU)],
    )

    assert result[1] == (skill(ICU, P), role(RN, P))
    assert result[2] == (skill(ICU, P), role(RN, R))
    assert result[3] == (skill(ICU, R),)


def test_the_scarcest_skill_is_filled_first() -> None:
    result = fill_targets(
        headcount_gap=0,
        role_gaps={},
        skill_gaps={ICU: 1, BLS: 1},
        candidates=[person(1, BLS), person(2, BLS), person(3, ICU, BLS), person(4, ICU)],
    )

    assert list(result) == [3, 4, 1]


def test_preference_order_decides_between_equals() -> None:
    first = fill_targets(
        headcount_gap=1, role_gaps={}, skill_gaps={}, candidates=[person(1), person(2)]
    )
    second = fill_targets(
        headcount_gap=1, role_gaps={}, skill_gaps={}, candidates=[person(2), person(1)]
    )

    assert list(first) == [1, 2]
    assert list(second) == [2, 1]


def test_nobody_matches() -> None:
    assert (
        fill_targets(
            headcount_gap=0, role_gaps={}, skill_gaps={ICU: 1}, candidates=[person(1, BLS)]
        )
        == {}
    )


def test_a_duplicate_candidate_raises() -> None:
    with pytest.raises(ValueError):
        fill_targets(
            headcount_gap=1, role_gaps={}, skill_gaps={}, candidates=[person(1), person(1)]
        )


def test_first_wave_replacement_fills_only_the_remaining_target() -> None:
    from app.domain.workflow.case_status import GapFiller

    selected = fill_targets(
        headcount_gap=3,
        role_gaps={1: 3},
        skill_gaps={},
        already_selected=[GapFiller(i, 1, frozenset()) for i in (201, 202, 203)],
        candidates=[GapFiller(i, 1, frozenset()) for i in (204, 205)],
    )
    # ceil(3 * 1.1) is four, so three kept candidates leave only one vacancy.
    assert list(selected) == [204]


# fill_targets_by_slice (round 4 PR T4)

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def hr(hours: int) -> datetime:
    return T0 + timedelta(hours=hours)


def timed(
    staff_id: int, start: int | None, end: int | None, *skills: int, role: int = RN
) -> GapFiller:
    return GapFiller(
        staff_id=staff_id,
        role_id=role,
        skill_ids=frozenset(skills),
        start_at=None if start is None else hr(start),
        end_at=None if end is None else hr(end),
    )


def gap_slice(
    start: int,
    end: int,
    headcount_gap: int = 1,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> IntervalGap:
    return IntervalGap(hr(start), hr(end), headcount_gap, roles or {}, skills or {})


def test_is_short_needs_a_missing_headcount_role_or_skill() -> None:
    assert is_short(gap_slice(0, 4))
    assert is_short(gap_slice(0, 4, 0, roles={RN: 1}))
    assert is_short(gap_slice(0, 4, 0, skills={ICU: 1}))
    assert not is_short(gap_slice(0, 4, 0))


def test_covers_is_half_open_and_none_means_the_whole_shift() -> None:
    assert covers(timed(1, None, None), hr(0), hr(8))
    assert covers(timed(1, 0, 4), hr(0), hr(4))
    assert not covers(timed(1, 0, 4), hr(0), hr(5))
    assert not covers(timed(1, 1, 8), hr(0), hr(4))


def test_elementary_slices_cut_inside_a_slice_and_keep_only_short_ones() -> None:
    pieces = elementary_slices(
        [gap_slice(4, 8), gap_slice(0, 4, 0), gap_slice(8, 12)],
        [timed(1, 6, 10), timed(2, 0, 12)],
    )

    assert [(p.start_at, p.end_at) for p in pieces] == [
        (hr(4), hr(6)),
        (hr(6), hr(8)),
        (hr(8), hr(10)),
        (hr(10), hr(12)),
    ]
    assert [p.seconds for p in pieces] == [7200] * 4


def test_without_slices_it_is_exactly_fill_targets() -> None:
    candidates = [person(1, ICU), person(2), person(3, ICU)]
    expected = fill_targets(
        headcount_gap=2, role_gaps={RN: 1}, skill_gaps={ICU: 1}, candidates=candidates
    )

    got = fill_targets_by_slice(
        slices=None,
        candidates=candidates,
        headcount_gap=2,
        role_gaps={RN: 1},
        skill_gaps={ICU: 1},
    )

    assert got == expected


def test_one_slice_gives_the_same_people_and_targets_as_fill_targets() -> None:
    candidates = [person(1, ICU), person(2), person(3, ICU)]
    expected = fill_targets(
        headcount_gap=2, role_gaps={RN: 1}, skill_gaps={ICU: 1}, candidates=candidates
    )

    got = fill_targets_by_slice(
        slices=elementary_slices([gap_slice(0, 8, 2, {RN: 1}, {ICU: 1})], candidates),
        candidates=candidates,
    )

    assert list(got) == list(expected)
    for staff_id, credits in got.items():
        assert [(c.target_type, c.selection_type, c.role_id, c.skill_id) for c in credits] == [
            (c.target_type, c.selection_type, c.role_id, c.skill_id) for c in expected[staff_id]
        ]
        assert all(c.start_at == hr(0) and c.end_at == hr(8) for c in credits)


def test_a_member_needed_only_in_the_second_slice_is_kept() -> None:
    first = timed(1, 0, 4)
    second = timed(2, 4, 8)
    whole = timed(3, None, None)

    got = fill_targets_by_slice(
        slices=elementary_slices([gap_slice(0, 4), gap_slice(4, 8)], [first, second, whole]),
        candidates=[first, second, whole],
    )

    assert list(got) == [1, 3, 2]
    assert {c.start_at for c in got[2]} == {hr(4)}


def test_counted_fillers_reduce_the_residual_of_the_slices_they_fill_whole() -> None:
    # Person 9 is on the roster only in 00-04, so only that slice needs less
    counted = [timed(9, 0, 4)]
    candidates = [timed(1, None, None), timed(2, None, None)]

    got = fill_targets_by_slice(
        slices=elementary_slices([gap_slice(0, 4), gap_slice(4, 8)], candidates + counted),
        candidates=candidates,
        counted=counted,
    )

    # 00-04: the gap is closed by person 9, nothing to fill. 04-08: target 2
    assert set(got) == {1, 2}
    assert all(c.start_at == hr(4) and c.end_at == hr(8) for rows in got.values() for c in rows)


def test_counted_fillers_are_counted_once_per_person() -> None:
    counted = [timed(9, None, None), timed(9, None, None)]

    got = fill_targets_by_slice(
        slices=elementary_slices([gap_slice(0, 8, 2)], counted),
        candidates=[person(1), person(2), person(3)],
        counted=counted,
    )

    # Gap 2 minus one person is 1, so the target is 2
    assert set(got) == {1, 2}


def test_a_person_already_selected_in_a_later_slice_gets_no_new_rows_there() -> None:
    # Gap 1 gives a target of 2. Person 3 is chosen in 00-04 and is whole-shift, so
    # in 04-08 they count as already selected; their window stays 00-04
    first, second, third = timed(1, 0, 4), timed(2, 4, 8), timed(3, None, None)

    got = fill_targets_by_slice(
        slices=elementary_slices([gap_slice(0, 4), gap_slice(4, 8)], [first, second, third]),
        candidates=[first, second, third],
    )

    assert got[1] == (TargetCredit(TargetType.HEADCOUNT, P, start_at=hr(0), end_at=hr(4)),)
    assert got[3] == (TargetCredit(TargetType.HEADCOUNT, R, start_at=hr(0), end_at=hr(4)),)
    assert got[2] == (TargetCredit(TargetType.HEADCOUNT, R, start_at=hr(4), end_at=hr(8)),)
