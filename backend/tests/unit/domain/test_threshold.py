"""check_threshold(): docs/workflow.md section 3.3."""

from decimal import Decimal

import pytest

from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import required_staff_for
from app.domain.staffing.threshold import ThresholdResult, check_threshold

RN, HEAD_NURSE = 1, 2
ICU, BLS = 1, 2


def nurse(
    staff_id: int,
    *skills: int,
    role_id: int = RN,
    status: RosterStatus = RosterStatus.ASSIGNED,
) -> RosterMember:
    return RosterMember(
        staff_id=staff_id,
        shift_id=1,
        status=status,
        role_id=role_id,
        skill_ids=frozenset(skills),
    )


def nurses(count: int) -> list[RosterMember]:
    return [nurse(100 + index) for index in range(count)]


def check(
    roster: list[RosterMember],
    *,
    patients: int = 0,
    ratio: Decimal | int = 2,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> ThresholdResult:
    return check_threshold(
        patient_count=patients,
        patients_per_nurse=ratio,
        required_roles=roles or {},
        required_skills=skills or {},
        roster=roster,
    )


# --------------------------------------------------------------------------- #
# Ratio
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("patients", "staff", "exceeded"),
    [
        (10, 5, False),  # the Golden Case before the leave
        (10, 4, True),  # after 105 left
        (8, 4, False),  # exactly at the limit
        (9, 4, True),
        (2, 1, False),
        (0, 0, False),  # nobody needed, nobody there
        (1, 0, True),  # a shift with nobody left: no division by zero
    ],
)
def test_ratio_is_exceeded_only_above_the_limit(patients: int, staff: int, exceeded: bool) -> None:
    result = check(nurses(staff), patients=patients)

    assert result.ratio_exceeded is exceeded
    assert result.passed is exceeded


def test_ratio_gives_the_same_answer_as_comparing_with_required_staff() -> None:
    """Section 3.3: patient_count > ratio * staff is staff < ceil(patient_count / ratio)."""
    for ratio in (1, 2, 3, Decimal("2.5"), Decimal("0.5")):
        for patients in range(0, 31):
            for staff in range(0, 16):
                by_product = check(nurses(staff), patients=patients, ratio=ratio).ratio_exceeded
                assert by_product is (staff < required_staff_for(patients, ratio))


def test_only_covering_rows_count_and_each_person_once() -> None:
    roster = [
        nurse(101),
        nurse(101),
        nurse(102, status=RosterStatus.CANCELLED),
        # Round 3 PR R: a shift that ended keeps its people
        nurse(103, status=RosterStatus.COMPLETED),
        nurse(104, status=RosterStatus.PENDING_APPROVAL),
    ]

    # Two people present (101 and 103): 5 patients are above the limit of 4
    assert check(roster, patients=4).ratio_exceeded is False
    assert check(roster, patients=5).ratio_exceeded is True


# --------------------------------------------------------------------------- #
# Role and skill
# --------------------------------------------------------------------------- #
def test_a_missing_role_passes_even_when_the_ratio_holds() -> None:
    result = check([nurse(101), nurse(900, role_id=HEAD_NURSE)], patients=2, roles={RN: 2})

    assert result == ThresholdResult(ratio_exceeded=False, short_role_ids=(RN,), short_skill_ids=())
    assert result.passed


def test_a_missing_skill_passes_even_when_the_ratio_holds() -> None:
    result = check([nurse(101, ICU), nurse(102, BLS)], patients=2, skills={ICU: 2, BLS: 1})

    assert result == ThresholdResult(
        ratio_exceeded=False, short_role_ids=(), short_skill_ids=(ICU,)
    )
    assert result.passed


def test_short_ids_are_sorted() -> None:
    result = check([], roles={HEAD_NURSE: 1, RN: 1}, skills={BLS: 1, ICU: 1})

    assert result.short_role_ids == (RN, HEAD_NURSE)
    assert result.short_skill_ids == (ICU, BLS)


def test_a_requirement_of_zero_is_never_short() -> None:
    assert not check([], roles={RN: 0}, skills={ICU: 0}).passed


def test_one_person_counts_toward_every_skill_they_hold() -> None:
    assert not check([nurse(101, ICU, BLS)], skills={ICU: 1, BLS: 1}).passed


def test_a_covered_shift_does_not_pass() -> None:
    roster = [nurse(101, ICU), nurse(102, ICU), nurse(103), nurse(104), nurse(105)]

    result = check(roster, patients=10, roles={RN: 5}, skills={ICU: 2})

    assert result == ThresholdResult(ratio_exceeded=False, short_role_ids=(), short_skill_ids=())
    assert not result.passed


def test_minimum_staff_is_not_an_input() -> None:
    """Q32: 2 patients, 1 nurse left, a floor of 2. The ratio holds, so it does not pass.

    The floor is not a parameter of the check at all.
    """
    assert not check(nurses(1), patients=2, roles={RN: 1}).passed


# --------------------------------------------------------------------------- #
# Bad input
# --------------------------------------------------------------------------- #
def test_negative_patient_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        check([], patients=-1)


@pytest.mark.parametrize("ratio", [0, -1, Decimal("0"), Decimal("NaN"), Decimal("Infinity")])
def test_ratio_must_be_positive_and_finite(ratio: Decimal | int) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        check([], ratio=ratio)


@pytest.mark.parametrize("ratio", [2.0, True])
def test_float_and_bool_ratios_are_rejected(ratio: object) -> None:
    with pytest.raises(TypeError, match="Decimal or int"):
        check([], ratio=ratio)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", ["role", "skill"])
def test_negative_requirement_counts_are_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        check(
            [],
            roles={RN: -1} if kind == "role" else {},
            skills={ICU: -1} if kind == "skill" else {},
        )
