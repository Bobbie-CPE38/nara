"""solve() against the recorded round 1 results (round 2 contract, sections 4.5 and 6)."""

from collections import Counter

import pytest

from app.domain.enums import SolverStatus
from app.domain.staffing.wave_targets import wave_target
from tests.unit.optimization.build_solver_baseline import (
    MAX_CANDIDATES,
    MAX_GAP,
    build_problems,
    hand_made,
)
from tests.unit.optimization.solver_baseline import (
    Problem,
    Recorded,
    encode_problem,
    load_cases,
    run_case,
)

CASES = load_cases()

# The least each kind of problem must appear. The recorded file has, in this order:
# 86, 57, 84, 196, 147, 96, 45, 1, 2.
MINIMUM = {
    "lowered_target": 50,
    "fractional_score": 35,
    "several_sources": 50,
    "people_outside_the_wave": 120,
    "wave_of_five_or_more": 90,
    "gap_of_five": 60,
    "25_or_more_candidates": 25,
    "no_candidates": 1,
    "empty_wave_with_candidates": 1,
}


def _largest_gap(problem: Problem) -> int:
    return max([problem.headcount_gap, *problem.role_gaps.values(), *problem.skill_gaps.values()])


def _has_a_lowered_target(problem: Problem) -> bool:
    fillers = [candidate.filler for candidate in problem.candidates]
    return (
        wave_target(problem.headcount_gap) > len(fillers)
        or any(
            wave_target(gap) > sum(filler.role_id == role_id for filler in fillers)
            for role_id, gap in problem.role_gaps.items()
        )
        or any(
            wave_target(gap) > sum(skill_id in filler.skill_ids for filler in fillers)
            for skill_id, gap in problem.skill_gaps.items()
        )
    )


@pytest.mark.parametrize(("problem", "recorded"), CASES, ids=[problem.name for problem, _ in CASES])
def test_solve_returns_the_recorded_result(problem: Problem, recorded: Recorded) -> None:
    result = run_case(problem)

    assert result.first_wave == recorded.first_wave
    assert result.ranked_staff_ids == recorded.ranked_staff_ids
    assert result.objective_score == recorded.objective_score
    assert result.status is (
        SolverStatus.OPTIMAL if problem.candidates else SolverStatus.INFEASIBLE
    )


def test_the_file_holds_the_problems_the_builder_makes() -> None:
    in_the_file = [encode_problem(problem) for problem, _ in CASES]

    assert in_the_file == [encode_problem(problem) for problem in build_problems()]


def test_every_problem_is_within_the_agreed_size() -> None:
    """R2-Q34: no gap above 5 and no more than 30 candidates."""
    names = [problem.name for problem, _ in CASES]

    assert len(names) == len(set(names)) == 229
    for problem, _ in CASES:
        assert len(problem.candidates) <= MAX_CANDIDATES, problem.name
        assert _largest_gap(problem) <= MAX_GAP, problem.name


def test_the_hand_made_problems_give_the_wave_they_were_built_for() -> None:
    recorded = {problem.name: result for problem, result in CASES}

    for problem, wave in hand_made():
        in_the_wave = sorted(staff_id for staff_id, _ in recorded[problem.name].first_wave)
        assert in_the_wave == wave, problem.name


def test_the_problems_cover_what_a_new_solver_must_get_right() -> None:
    counts: Counter[str] = Counter()
    for problem, recorded in CASES:
        score = recorded.objective_score
        people, wave = len(problem.candidates), len(recorded.first_wave)
        sources = {candidate.metrics.source for candidate in problem.candidates}
        counts["lowered_target"] += _has_a_lowered_target(problem)
        counts["fractional_score"] += score is not None and score.denominator != 1
        counts["several_sources"] += len(sources) > 1
        counts["people_outside_the_wave"] += wave < people
        counts["wave_of_five_or_more"] += wave >= 5
        counts["gap_of_five"] += _largest_gap(problem) == MAX_GAP
        counts["25_or_more_candidates"] += people >= 25
        counts["no_candidates"] += people == 0
        counts["empty_wave_with_candidates"] += people > 0 and wave == 0

    for kind, least in MINIMUM.items():
        assert counts[kind] >= least, (kind, counts[kind])
