"""Wave targets and their fill order (round 1 contract, section 8.3)."""

import pytest

from app.domain.enums import SelectionType, TargetType
from app.domain.staffing.wave_targets import TargetCredit, fill_targets, wave_target
from app.domain.workflow.case_status import GapFiller

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
