"""The round 1 Solver on plain values (round 1 contract, section 8.3)."""

from fractions import Fraction

import pytest

from app.domain.constraints.penalties import SoftWeights
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource, SelectionType, TargetType
from app.domain.staffing.wave_targets import TargetCredit
from app.domain.workflow.case_status import GapFiller
from app.optimization.solver import SolverCandidate, SolverResult, solve

RN = 1
ICU, BLS = 1, 2
SAME = CandidateSource.SAME_WARD
P, R = SelectionType.PRIMARY, SelectionType.RESERVE

WEIGHTS = SoftWeights(
    candidate_count=Fraction(1000),
    consecutive_shift=Fraction(5),
    workload_imbalance=Fraction(1),
    projected_overtime=Fraction(2),
    roster_change=Fraction(300),
    candidate_source=Fraction(200),
    source_order=(SAME, CandidateSource.FLOAT_POOL, CandidateSource.CROSS_WARD),
)


def person(
    staff_id: int,
    *skills: int,
    role: int = RN,
    hours: int = 0,
    run: int = 1,
    overtime: int = 0,
) -> SolverCandidate:
    return SolverCandidate(
        filler=GapFiller(staff_id=staff_id, role_id=role, skill_ids=frozenset(skills)),
        metrics=SoftMetrics(
            staff_id=staff_id,
            source=SAME,
            hours_this_week=Fraction(hours),
            projected_consecutive_shifts=run,
            overtime_hours=Fraction(overtime),
        ),
    )


def run(
    candidates: list[SolverCandidate],
    *,
    headcount: int = 1,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> SolverResult:
    return solve(
        headcount_gap=headcount,
        role_gaps={RN: 1} if roles is None else roles,
        skill_gaps=skills or {},
        candidates=candidates,
        weights=WEIGHTS,
    )


def golden() -> list[SolverCandidate]:
    return [person(201), person(202, hours=8, run=2), person(203, hours=8, run=2)]


def test_golden_case() -> None:
    result = run(golden())

    assert result.ranked_staff_ids == (201, 202, 203)
    assert list(result.first_wave) == [201, 202]
    assert result.first_wave[201] == (
        TargetCredit(TargetType.ROLE, P, role_id=RN),
        TargetCredit(TargetType.HEADCOUNT, P),
    )
    assert result.first_wave[202] == (
        TargetCredit(TargetType.ROLE, R, role_id=RN),
        TargetCredit(TargetType.HEADCOUNT, R),
    )
    assert result.objective_score == 2023


def test_skill_gap() -> None:
    candidates = [
        person(201, ICU, BLS),
        person(202, BLS, hours=8, run=2),
        person(203, ICU, hours=8, run=2),
    ]

    result = run(candidates, skills={ICU: 1})

    assert result.ranked_staff_ids == (201, 203, 202)
    assert list(result.first_wave) == [201, 203]
    assert result.first_wave[201] == (
        TargetCredit(TargetType.SKILL, P, skill_id=ICU),
        TargetCredit(TargetType.ROLE, P, role_id=RN),
        TargetCredit(TargetType.HEADCOUNT, P),
    )
    assert result.first_wave[203] == (
        TargetCredit(TargetType.SKILL, R, skill_id=ICU),
        TargetCredit(TargetType.ROLE, R, role_id=RN),
        TargetCredit(TargetType.HEADCOUNT, R),
    )


def test_fewer_candidates_than_the_target() -> None:
    result = run([person(201)])

    assert result.ranked_staff_ids == (201,)
    assert list(result.first_wave) == [201]
    assert result.objective_score == 1005


def test_no_candidates() -> None:
    assert run([]) == SolverResult((), {}, None)


def test_the_fewest_people_that_cover_the_targets_win() -> None:
    candidates = [
        person(1, ICU, BLS, hours=52, run=7),
        person(2, ICU, BLS, hours=52, run=7),
        person(3, ICU),
        person(4, ICU),
        person(5, BLS),
        person(6, BLS),
    ]

    result = run(candidates, headcount=0, roles={}, skills={ICU: 1, BLS: 1})

    assert set(result.first_wave) == {1, 2}


def test_ranking_key_orders_the_wave_not_the_penalty() -> None:
    candidates = [person(1, hours=10, run=5), person(2, hours=12, run=1), person(3, hours=40)]

    result = run(candidates)

    assert set(result.first_wave) == {1, 2}
    assert result.ranked_staff_ids == (1, 2, 3)


def test_ties_go_to_the_lower_staff_ids() -> None:
    result = run([person(5), person(3), person(9)])

    assert list(result.first_wave) == [3, 5]
    assert result.ranked_staff_ids == (3, 5, 9)


def test_the_result_does_not_depend_on_the_input_order() -> None:
    assert run(list(reversed(golden()))) == run(golden())


def test_a_duplicate_staff_id_raises() -> None:
    with pytest.raises(ValueError):
        run([person(1), person(1)])


def test_a_candidate_with_mismatched_ids_raises() -> None:
    with pytest.raises(ValueError):
        SolverCandidate(
            filler=GapFiller(staff_id=1, role_id=RN, skill_ids=frozenset()),
            metrics=person(2).metrics,
        )
