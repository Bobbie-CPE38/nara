from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import (
    CountGap,
    GapResult,
    calculate_gap,
    effective_minimum_for,
    required_staff_for,
)

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2


def golden_roster() -> list[RosterMember]:
    """workflow.md section 10.2, including staff assigned to another shift."""
    return [
        RosterMember(101, 1, RosterStatus.ASSIGNED, RN, frozenset({ICU, BLS})),
        RosterMember(102, 1, RosterStatus.ASSIGNED, RN, frozenset({ICU})),
        RosterMember(103, 1, RosterStatus.ASSIGNED, RN, frozenset({BLS})),
        RosterMember(104, 1, RosterStatus.ASSIGNED, RN, frozenset({BLS})),
        RosterMember(105, 1, RosterStatus.ASSIGNED, RN, frozenset({BLS})),
        RosterMember(202, 2, RosterStatus.ASSIGNED, RN, frozenset({BLS})),
        RosterMember(203, 2, RosterStatus.ASSIGNED, RN, frozenset({ICU})),
    ]


def test_golden_case_before_and_after_leave_and_replacement() -> None:
    roster = golden_roster()
    roles, skills = {RN: 5}, {ICU: 2}

    def calculate() -> GapResult:
        return calculate_gap(
            shift_id=1,
            required_staff=5,
            minimum_staff=4,
            preserve_minimum_staffing=True,
            required_roles=roles,
            required_skills=skills,
            roster=roster,
        )

    before = calculate()
    assert before.effective_minimum == 5
    assert before.headcount_gap == 0
    assert before.role_gaps == {RN: CountGap(5, 5)}
    assert before.skill_gaps == {ICU: CountGap(2, 2)}
    assert not before.has_gap

    roster[4] = replace(roster[4], status=RosterStatus.CANCELLED)
    after = calculate()
    assert after.headcount_gap == 1
    assert after.role_gaps[RN].gap_count == 1
    assert after.role_gaps[RN].current_count == 4
    assert after.skill_gaps[ICU].gap_count == 0
    assert after.has_gap

    roster.append(RosterMember(201, 1, RosterStatus.ASSIGNED, RN, frozenset({ICU, BLS})))
    restored = calculate()
    assert restored.headcount_gap == 0
    assert restored.role_gaps[RN] == CountGap(5, 5)
    assert restored.skill_gaps[ICU] == CountGap(2, 3)
    assert restored.skill_gaps[ICU].gap_count == 0
    assert not restored.has_gap
    assert roles == {RN: 5} and skills == {ICU: 2}


def test_missing_skill_with_enough_headcount() -> None:
    roster = golden_roster()
    roster[1] = replace(roster[1], skill_ids=frozenset({BLS}))
    result = calculate_gap(
        shift_id=1,
        required_staff=5,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 5},
        required_skills={ICU: 2},
        roster=roster,
    )
    assert result.headcount_gap == 0
    assert result.role_gaps[RN].gap_count == 0
    assert result.skill_gaps[ICU] == CountGap(2, 1)
    assert result.skill_gaps[ICU].gap_count == 1
    assert result.has_gap


def test_wrong_role_does_not_fill_rn_shortage() -> None:
    roster = golden_roster()
    roster[4] = replace(roster[4], role_id=HEAD_NURSE)
    result = calculate_gap(
        shift_id=1,
        required_staff=5,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 5},
        required_skills={ICU: 2},
        roster=roster,
    )
    assert result.headcount_gap == 0
    assert result.role_gaps == {RN: CountGap(5, 4)}
    assert result.has_gap


@pytest.mark.parametrize("cancelled", [False, True])
def test_shift_two_has_no_gap_even_after_203_leaves(cancelled: bool) -> None:
    roster = golden_roster()
    if cancelled:
        roster[-1] = replace(roster[-1], status=RosterStatus.CANCELLED)
    result = calculate_gap(
        shift_id=2,
        required_staff=1,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 1},
        required_skills={},
        roster=roster,
    )
    assert result.headcount_gap == 0
    assert result.role_gaps[RN] == CountGap(1, 1 if cancelled else 2)
    assert result.role_gaps[RN].gap_count == 0
    assert result.skill_gaps == {}
    assert not result.has_gap


def test_empty_roster_and_missing_categories() -> None:
    result = calculate_gap(
        shift_id=1,
        required_staff=5,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 4, HEAD_NURSE: 1},
        required_skills={ICU: 2, BLS: 3},
        roster=[],
    )
    assert result.headcount_gap == 5
    assert result.role_gaps == {RN: CountGap(4, 0), HEAD_NURSE: CountGap(1, 0)}
    assert result.skill_gaps == {ICU: CountGap(2, 0), BLS: CountGap(3, 0)}
    assert result.has_gap


@pytest.mark.parametrize("status", list(RosterStatus))
def test_only_assigned_staff_count(status: RosterStatus) -> None:
    member = RosterMember(1, 1, status, RN, frozenset({ICU}))
    result = calculate_gap(
        shift_id=1,
        required_staff=1,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 1},
        required_skills={ICU: 1},
        roster=[member],
    )
    expected = 1 if status == RosterStatus.ASSIGNED else 0
    assert result.headcount_gap == 1 - expected
    assert result.role_gaps[RN].current_count == expected
    assert result.skill_gaps[ICU].current_count == expected


def test_distinct_people_and_multiple_skills_without_mutating_input() -> None:
    member = RosterMember(1, 1, RosterStatus.ASSIGNED, RN, frozenset({ICU, BLS}))
    roster = [member, member, replace(member, shift_id=2)]
    original = roster.copy()
    result = calculate_gap(
        shift_id=1,
        required_staff=2,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 2},
        required_skills={ICU: 2, BLS: 1},
        roster=iter(roster),
    )
    assert result.headcount_gap == 1
    assert result.role_gaps[RN] == CountGap(2, 1)
    assert result.skill_gaps == {ICU: CountGap(2, 1), BLS: CountGap(1, 1)}
    assert roster == original


def test_zero_requirements() -> None:
    result = calculate_gap(
        shift_id=1,
        required_staff=0,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 0},
        required_skills={ICU: 0},
        roster=[],
    )
    assert result.headcount_gap == 0
    assert result.role_gaps[RN].gap_count == 0
    assert result.skill_gaps[ICU].gap_count == 0
    assert not result.has_gap


@pytest.mark.parametrize("kind", ["required", "minimum", "role", "skill"])
def test_negative_requirements_are_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        calculate_gap(
            shift_id=1,
            required_staff=-1 if kind == "required" else 1,
            minimum_staff=-1 if kind == "minimum" else 1,
            preserve_minimum_staffing=True,
            required_roles={RN: -1 if kind == "role" else 1},
            required_skills={ICU: -1 if kind == "skill" else 1},
            roster=[],
        )


@pytest.mark.parametrize("kind", ["role", "skills"])
def test_conflicting_staff_snapshots_are_rejected(kind: str) -> None:
    member = RosterMember(1, 1, RosterStatus.ASSIGNED, RN, frozenset({ICU}))
    other = (
        replace(member, role_id=HEAD_NURSE)
        if kind == "role"
        else replace(member, skill_ids=frozenset({BLS}))
    )
    with pytest.raises(ValueError, match="Conflicting coverage"):
        calculate_gap(
            shift_id=1,
            required_staff=1,
            minimum_staff=0,
            preserve_minimum_staffing=True,
            required_roles={},
            required_skills={},
            roster=[member, other],
        )


@pytest.mark.parametrize(
    ("patients", "ratio", "expected"),
    [
        (10, Decimal("2"), 5),
        (11, Decimal("2"), 6),
        (0, Decimal("2"), 0),
        (5, Decimal("2.5"), 2),
        (6, Decimal("2.5"), 3),
        (12, Decimal("2.4"), 5),
        (1, Decimal("0.1"), 10),
        (10, Decimal("1.999999999999999999999999999999"), 6),
        (10, 2, 5),
    ],
)
def test_required_staff_rounds_up_exactly(
    patients: int, ratio: Decimal | int, expected: int
) -> None:
    assert required_staff_for(patients, ratio) == expected


def test_required_staff_rejects_a_negative_number_of_patients() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        required_staff_for(-1, 2)


@pytest.mark.parametrize("ratio", ["0", "-2", "NaN", "Infinity", "-Infinity"])
def test_invalid_workload_ratio_is_rejected(ratio: str) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        required_staff_for(10, Decimal(ratio))


@pytest.mark.parametrize("ratio", [2.4, 2.0, True, False, "2.4", None])
def test_ratio_requires_decimal_or_integer(ratio: object) -> None:
    with pytest.raises(TypeError, match="Decimal or int"):
        required_staff_for(12, ratio)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("required", "minimum", "preserve", "expected"),
    [
        (5, 4, True, 5),  # Golden Case shift 1: the workload target is the larger one
        (2, 4, True, 4),  # the fixed floor is the larger one
        (4, 4, True, 4),
        (2, 4, False, 2),  # flag off: the floor is not used
        (5, 4, False, 5),
        (0, 0, True, 0),
    ],
)
def test_effective_minimum_uses_the_floor_only_when_the_flag_is_on(
    required: int, minimum: int, preserve: bool, expected: int
) -> None:
    assert (
        effective_minimum_for(
            required_staff=required, minimum_staff=minimum, preserve_minimum_staffing=preserve
        )
        == expected
    )


@pytest.mark.parametrize(("preserve", "target", "gap"), [(True, 4, 2), (False, 2, 0)])
def test_minimum_staff_above_required_staff_opens_a_headcount_gap(
    preserve: bool, target: int, gap: int
) -> None:
    """Two patients need one nurse at ratio 2, but the shift must never drop below four."""
    member = RosterMember(1, 1, RosterStatus.ASSIGNED, RN, frozenset())
    result = calculate_gap(
        shift_id=1,
        required_staff=2,
        minimum_staff=4,
        preserve_minimum_staffing=preserve,
        required_roles={},
        required_skills={},
        roster=[member, replace(member, staff_id=2)],
    )
    assert result.effective_minimum == target
    assert result.headcount_gap == gap
    assert result.has_gap is (gap > 0)


def test_higher_required_staff_changes_gap_with_same_roster() -> None:
    """A patient surge reaches the gap through required_staff, rewritten by its owner."""
    roster = golden_roster()
    original = roster.copy()

    def calculate(required_staff: int) -> GapResult:
        return calculate_gap(
            shift_id=1,
            required_staff=required_staff,
            minimum_staff=4,
            preserve_minimum_staffing=True,
            required_roles={RN: 5},
            required_skills={ICU: 2},
            roster=roster,
        )

    before = calculate(required_staff_for(10, 2))
    after = calculate(required_staff_for(11, 2))
    assert not before.has_gap
    assert after.effective_minimum == 6
    assert after.headcount_gap == 1
    assert after.role_gaps[RN].gap_count == after.skill_gaps[ICU].gap_count == 0
    assert after.has_gap
    assert roster == original


def test_calculated_result_cannot_be_mutated() -> None:
    result = calculate_gap(
        shift_id=1,
        required_staff=5,
        minimum_staff=0,
        preserve_minimum_staffing=True,
        required_roles={RN: 5},
        required_skills={ICU: 2},
        roster=golden_roster(),
    )
    with pytest.raises(TypeError):
        result.role_gaps[RN] = CountGap(5, 0)  # type: ignore[index]
    with pytest.raises(TypeError):
        result.skill_gaps[ICU] = CountGap(2, 0)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.role_gaps[RN].current_count = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.headcount_gap = 99  # type: ignore[misc]
    assert not result.has_gap


def test_result_copies_input_mappings_and_hash_ignores_insertion_order() -> None:
    roles = {RN: CountGap(5, 4), HEAD_NURSE: CountGap(1, 1)}
    skills = {ICU: CountGap(2, 2), BLS: CountGap(3, 3)}
    result = GapResult(5, 1, roles, skills)
    reordered = GapResult(
        5, 1, dict(reversed(list(roles.items()))), dict(reversed(list(skills.items())))
    )
    original_hash = hash(result)
    roles.clear()
    skills[ICU] = CountGap(2, 0)
    assert result == reordered
    assert hash(result) == hash(reordered) == original_hash
    assert len({result, reordered}) == 1
    assert result.role_gaps[RN] == CountGap(5, 4)
    assert result.skill_gaps[ICU] == CountGap(2, 2)
