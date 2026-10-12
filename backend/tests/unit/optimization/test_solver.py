"""The round 1 Solver on plain values (round 1 contract, section 8.3)."""

import itertools
import random
import time
from fractions import Fraction

import pytest

from app.domain.constraints.penalties import SoftWeights, plan_penalty
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource, SelectionType, TargetType
from app.domain.staffing.wave_targets import TargetCredit, wave_target
from app.domain.workflow.case_status import GapFiller, gap_closed
from app.optimization.solver import (
    SolverCandidate,
    SolverResult,
    _cheapest_covering_group,
    solve,
)

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


@pytest.mark.parametrize(("gap", "target"), [(4, 5), (6, 7)])
def test_a_ward_of_equal_candidates_is_planned_quickly(gap: int, target: int) -> None:
    candidates = [person(staff_id) for staff_id in range(1, 41)]

    started = time.perf_counter()
    result = run(candidates, headcount=gap, roles={RN: gap})
    elapsed = time.perf_counter() - started

    assert list(result.first_wave) == list(range(1, target + 1))
    assert result.ranked_staff_ids == tuple(range(1, 41))
    assert result.objective_score == 1005 * target
    assert elapsed < 2


def test_equal_candidates_of_two_kinds_are_planned_quickly() -> None:
    candidates = [person(staff_id) for staff_id in range(1, 21)]
    candidates += [person(staff_id, ICU) for staff_id in range(21, 41)]

    started = time.perf_counter()
    result = run(candidates, headcount=4, roles={RN: 4}, skills={ICU: 2})
    elapsed = time.perf_counter() - started

    assert set(result.first_wave) == {1, 2, 21, 22, 23}
    assert result.objective_score == 5025
    assert elapsed < 2


def _every_group_best(
    candidates: list[SolverCandidate],
    headcount: int,
    roles: dict[int, int],
    skills: dict[int, int],
) -> set[int]:
    """The best group by trying every subset: the rule the search must reproduce."""
    fillers = [candidate.filler for candidate in candidates]
    lowered_headcount = min(wave_target(headcount), len(candidates))
    lowered_roles = {
        role_id: min(wave_target(gap), sum(filler.role_id == role_id for filler in fillers))
        for role_id, gap in roles.items()
    }
    lowered_skills = {
        skill_id: min(wave_target(gap), sum(skill_id in filler.skill_ids for filler in fillers))
        for skill_id, gap in skills.items()
    }
    best: tuple[Fraction, int, tuple[int, ...]] | None = None
    for size in range(len(candidates) + 1):
        for group in itertools.combinations(candidates, size):
            if not gap_closed(
                headcount_gap=lowered_headcount,
                role_gaps=lowered_roles,
                skill_gaps=lowered_skills,
                fillers=(candidate.filler for candidate in group),
            ):
                continue
            score = (
                plan_penalty((candidate.metrics for candidate in group), WEIGHTS),
                size,
                tuple(sorted(candidate.filler.staff_id for candidate in group)),
            )
            if best is None or score < best:
                best = score
    assert best is not None
    return set(best[2])


def test_the_search_agrees_with_trying_every_group() -> None:
    """Calls the private search directly: solve() only shows the group after fill_targets()."""
    rng = random.Random(20261012)
    for _ in range(300):
        candidates = [
            person(
                staff_id,
                *rng.sample([ICU, BLS], rng.randint(0, 2)),
                role=rng.choice([RN, 2]),
                hours=rng.choice([0, 8, 16]),
                run=rng.choice([1, 2]),
            )
            for staff_id in rng.sample(range(1, 50), rng.randint(1, 8))
        ]
        headcount = rng.randint(0, 3)
        roles = {role_id: rng.randint(1, 3) for role_id in rng.sample([RN, 2], rng.randint(0, 2))}
        skills = {
            skill_id: rng.randint(1, 2) for skill_id in rng.sample([ICU, BLS], rng.randint(0, 2))
        }

        group = _cheapest_covering_group(
            candidates,
            headcount_gap=headcount,
            role_gaps=roles,
            skill_gaps=skills,
            weights=WEIGHTS,
        )

        found = {candidate.filler.staff_id for candidate in group}
        assert found == _every_group_best(candidates, headcount, roles, skills), (
            candidates,
            headcount,
            roles,
            skills,
        )
