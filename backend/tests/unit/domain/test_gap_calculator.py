from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import CountGap, GapResult, calculate_gap

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
            patient_count=10,
            patients_per_nurse=2,
            required_roles=roles,
            required_skills=skills,
            roster=roster,
        )

    before = calculate()
    assert before.minimum_required_staff == 5
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
        patient_count=10,
        patients_per_nurse=2,
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
        patient_count=10,
        patients_per_nurse=2,
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
        patient_count=2,
        patients_per_nurse=2,
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
        patient_count=10,
        patients_per_nurse=2,
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
        patient_count=2,
        patients_per_nurse=2,
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
        patient_count=4,
        patients_per_nurse=2,
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
        patient_count=0,
        patients_per_nurse=2,
        required_roles={RN: 0},
        required_skills={ICU: 0},
        roster=[],
    )
    assert result.headcount_gap == 0
    assert result.role_gaps[RN].gap_count == 0
    assert result.skill_gaps[ICU].gap_count == 0
    assert not result.has_gap


@pytest.mark.parametrize("kind", ["headcount", "role", "skill"])
def test_negative_requirements_are_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        calculate_gap(
            shift_id=1,
            patient_count=-1 if kind == "headcount" else 2,
            patients_per_nurse=2,
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
            patient_count=2,
            patients_per_nurse=2,
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
        (1, Decimal("0.1"), 10),
        (10, Decimal("1.999999999999999999999999999999"), 6),
    ],
)
def test_workload_target_rounds_up_exactly(patients: int, ratio: Decimal, expected: int) -> None:
    result = calculate_gap(
        shift_id=1,
        patient_count=patients,
        patients_per_nurse=ratio,
        required_roles={},
        required_skills={},
        roster=[],
    )
    assert result.minimum_required_staff == expected
    assert result.headcount_gap == expected


def test_patient_surge_changes_gap_with_same_roster() -> None:
    roster = golden_roster()
    original = roster.copy()
    before = calculate_gap(
        shift_id=1,
        patient_count=10,
        patients_per_nurse=2,
        required_roles={RN: 5},
        required_skills={ICU: 2},
        roster=roster,
    )
    after = calculate_gap(
        shift_id=1,
        patient_count=11,
        patients_per_nurse=2,
        required_roles={RN: 5},
        required_skills={ICU: 2},
        roster=roster,
    )
    assert not before.has_gap
    assert after.minimum_required_staff == 6
    assert after.headcount_gap == 1
    assert after.role_gaps[RN].gap_count == after.skill_gaps[ICU].gap_count == 0
    assert after.has_gap
    assert roster == original


@pytest.mark.parametrize("ratio", ["0", "-2", "NaN", "Infinity", "-Infinity"])
def test_invalid_workload_ratio_is_rejected(ratio: str) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        calculate_gap(
            shift_id=1,
            patient_count=10,
            patients_per_nurse=Decimal(ratio),
            required_roles={},
            required_skills={},
            roster=[],
        )
