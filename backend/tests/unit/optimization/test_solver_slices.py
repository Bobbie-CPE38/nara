"""The Solver per time slice, the exclusive source shift and the partial plan (round 4 PR T4)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource, SolverStatus
from app.domain.staffing.wave_targets import TargetCredit
from app.domain.workflow.case_status import GapFiller, IntervalGap
from app.optimization.solver import SolverCandidate, SolverResult, _Round, solve
from tests.unit.optimization.solver_baseline import load_cases
from tests.unit.optimization.test_solver import ICU, LIMIT, RN, SAME, WEIGHTS
from tests.unit.optimization.test_solver_stages import UNKNOWN, script

ER = 2
OTHER = 3
T0 = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


def at(hour: int) -> datetime:
    return T0 + timedelta(hours=hour)


def cand(
    staff_id: int,
    *skills: int,
    role: int = RN,
    start: int | None = None,
    end: int | None = None,
    shift: int | None = None,
    worse: bool = False,
) -> SolverCandidate:
    """A candidate present from hour `start` to hour `end` (None: the whole shift)."""
    return SolverCandidate(
        filler=GapFiller(
            staff_id=staff_id,
            role_id=role,
            skill_ids=frozenset(skills),
            start_at=None if start is None else at(start),
            end_at=None if end is None else at(end),
        ),
        metrics=SoftMetrics(
            staff_id=staff_id,
            source=SAME,
            hours_this_week=Fraction(8 if worse else 0),
            projected_consecutive_shifts=2 if worse else 1,
            overtime_hours=Fraction(0),
        ),
        source_shift_id=shift,
    )


def piece(
    start: int,
    end: int,
    headcount: int = 1,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
) -> IntervalGap:
    return IntervalGap(at(start), at(end), headcount, roles or {}, skills or {})


def go(candidates: Sequence[SolverCandidate], intervals: Sequence[IntervalGap]) -> SolverResult:
    return solve(
        headcount_gap=0,
        role_gaps={},
        skill_gaps={},
        candidates=candidates,
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
        intervals=intervals,
    )


def keys(result: SolverResult) -> list[tuple[int, list[tuple[object, ...]]]]:
    """first_wave without the credit windows."""
    return [
        (
            staff_id,
            [(c.target_type, c.selection_type, c.role_id, c.skill_id) for c in credits],
        )
        for staff_id, credits in result.first_wave.items()
    ]


def test_one_whole_shift_slice_equals_the_legacy_call_on_every_baseline_case() -> None:
    cases = load_cases()
    assert cases
    for problem, _ in cases:
        base = dict(
            headcount_gap=problem.headcount_gap,
            role_gaps=problem.role_gaps,
            skill_gaps=problem.skill_gaps,
            candidates=problem.candidates,
            weights=problem.weights,
            time_limit_seconds=LIMIT,
        )
        whole = IntervalGap(
            at(0), at(8), problem.headcount_gap, problem.role_gaps, problem.skill_gaps
        )

        legacy = solve(**base)  # type: ignore[arg-type]
        sliced = solve(**base, intervals=[whole])  # type: ignore[arg-type]

        assert sliced.ranked_staff_ids == legacy.ranked_staff_ids, problem.name
        assert keys(sliced) == keys(legacy), problem.name
        assert sliced.objective_score == legacy.objective_score, problem.name
        assert sliced.status == legacy.status, problem.name
        assert sliced.partial is False
        assert legacy.partial is False


def test_a_whole_shift_pair_covers_two_slices_cheaper_than_two_part_timers_and_a_third() -> None:
    result = go(
        [cand(1, start=0, end=4), cand(2, start=4, end=8), cand(3), cand(4)],
        [piece(0, 4), piece(4, 8)],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is False
    assert set(result.first_wave) == {3, 4}


def test_part_timers_are_chosen_when_each_slice_needs_them() -> None:
    result = go(
        [cand(1, start=0, end=4), cand(2, start=4, end=8), cand(3)],
        [piece(0, 4), piece(4, 8)],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert set(result.first_wave) == {1, 2, 3}
    windows = {
        staff_id: {(c.start_at, c.end_at) for c in credits}
        for staff_id, credits in result.first_wave.items()
    }
    assert windows[1] == {(at(0), at(4))}
    assert windows[2] == {(at(4), at(8))}
    # Person 3 is chosen in 00-04 and only counts as selected in 04-08: no new rows
    assert windows[3] == {(at(0), at(4))}


def test_a_part_timer_never_counts_for_a_slice_it_does_not_cover_whole() -> None:
    result = go([cand(1, start=0, end=4), cand(2)], [piece(4, 8)])

    assert result.status is SolverStatus.OPTIMAL
    # Person 1 is not present in 04-08, so the target is lowered to one holder
    assert set(result.first_wave) == {2}
    assert result.ranked_staff_ids == (2, 1)


def test_a_slice_nobody_covers_lowers_its_target_and_keeps_the_plan_optimal() -> None:
    result = go(
        [cand(1, start=0, end=4), cand(2, start=0, end=4)],
        [piece(0, 4), piece(4, 8)],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is False
    assert set(result.first_wave) == {1, 2}


def test_an_exclusive_source_shift_that_is_not_needed_twice_keeps_the_plan_complete() -> None:
    result = go([cand(1, shift=7), cand(2, shift=7), cand(3)], [piece(0, 8)])

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is False
    assert len(set(result.first_wave) & {1, 2}) == 1


def icu_er_pair() -> list[SolverCandidate]:
    # Same source shift, so only one can come. The ICU one costs more points
    return [cand(1, ICU, shift=5, worse=True), cand(2, ER, shift=5)]


def test_two_exclusive_candidates_for_two_skills_give_a_partial_plan_by_points() -> None:
    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={ICU: 1, ER: 1},
        candidates=icu_er_pair(),
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is True
    assert set(result.first_wave) == {2}
    assert result.ranked_staff_ids == (2, 1)


def test_exclusive_candidates_in_different_slices_give_a_partial_plan() -> None:
    result = go(
        [cand(1, start=0, end=4, shift=5, worse=True), cand(2, start=4, end=8, shift=5)],
        [piece(0, 4), piece(4, 8)],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is True
    assert set(result.first_wave) == {2}


def test_headcount_shortage_outranks_role_shortage() -> None:
    # Person 1 covers the long slice, person 2 the short one that also needs an RN
    result = go(
        [
            cand(1, role=OTHER, start=0, end=6, shift=5, worse=True),
            cand(2, role=RN, start=6, end=8, shift=5),
        ],
        [piece(0, 6), piece(6, 8, roles={RN: 1})],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is True
    assert set(result.first_wave) == {1}


def test_role_shortage_outranks_skill_shortage() -> None:
    # Equal headcount seconds; person 1 fills the role, person 2 the skill
    result = go(
        [
            cand(1, role=RN, start=0, end=4, shift=5, worse=True),
            cand(2, ICU, role=OTHER, start=4, end=8, shift=5),
        ],
        [piece(0, 4, roles={RN: 1}), piece(4, 8, skills={ICU: 1})],
    )

    assert result.status is SolverStatus.OPTIMAL
    assert result.partial is True
    assert set(result.first_wave) == {1}


@pytest.mark.parametrize("bad", [_Round(SolverStatus.INFEASIBLE, None)])
def test_without_an_exclusive_constraint_a_first_round_infeasible_is_model_invalid(
    monkeypatch: pytest.MonkeyPatch, bad: _Round
) -> None:
    script(monkeypatch, [bad])

    result = go([cand(1, shift=1), cand(2, shift=2), cand(3)], [piece(0, 8)])

    assert result == SolverResult((), {}, None, SolverStatus.MODEL_INVALID)


def test_a_partial_round_that_ends_unproved_returns_a_legal_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stage 1 is really infeasible, the headcount round is solved, the skill round times out
    script(monkeypatch, ["real", "real", UNKNOWN])

    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={ICU: 1, ER: 1},
        candidates=icu_er_pair(),
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.FEASIBLE
    assert result.partial is True
    assert len(result.first_wave) == 1
    assert set(result.first_wave) <= {1, 2}


def test_a_partial_round_cut_short_with_a_plan_returns_that_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(monkeypatch, ["real", _Round(SolverStatus.FEASIBLE, (1, 0))])

    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={ICU: 1, ER: 1},
        candidates=icu_er_pair(),
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    assert result.status is SolverStatus.FEASIBLE
    assert result.partial is True
    assert set(result.first_wave) == {1}


def test_a_timeout_in_the_partial_path_before_any_plan_gives_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(monkeypatch, ["real", UNKNOWN])

    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={ICU: 1, ER: 1},
        candidates=icu_er_pair(),
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    assert result == SolverResult((), {}, None, SolverStatus.UNKNOWN)


def test_a_best_group_that_covers_nothing_gives_infeasible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _Round(SolverStatus.OPTIMAL, (0, 0))
    script(monkeypatch, ["real", empty, empty])

    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={ICU: 1, ER: 1},
        candidates=icu_er_pair(),
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    assert result == SolverResult((), {}, None, SolverStatus.INFEASIBLE)


def test_credit_windows_default_to_the_whole_input_without_intervals() -> None:
    result = solve(
        headcount_gap=1,
        role_gaps={},
        skill_gaps={},
        candidates=[cand(1), cand(2)],
        weights=WEIGHTS,
        time_limit_seconds=LIMIT,
    )

    credits: tuple[TargetCredit, ...] = result.first_wave[1]
    assert all(c.start_at is None and c.end_at is None for c in credits)
    assert CandidateSource.SAME_WARD is SAME
