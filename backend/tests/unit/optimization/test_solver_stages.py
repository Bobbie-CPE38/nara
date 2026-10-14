"""The stages, the shared time budget and the statuses of solve() (round 2 contract, 4.7).

The status paths run on scripted rounds, not on a short time limit (R2-Q49).
"""

from collections.abc import Sequence
from typing import Any

import pytest
from ortools.sat.python import cp_model

from app.domain.enums import SolverStatus
from app.optimization import solver
from app.optimization.solver import SolverCandidate, SolverResult, _Round
from tests.unit.optimization.test_solver import WEIGHTS, golden, person, run

Entry = str | _Round
UNKNOWN = _Round(SolverStatus.UNKNOWN, None)
INFEASIBLE = _Round(SolverStatus.INFEASIBLE, None)
INVALID = _Round(SolverStatus.MODEL_INVALID, None)


def script(monkeypatch: pytest.MonkeyPatch, entries: Sequence[Entry]) -> list[float]:
    """Replace _run_cp_sat: "real" runs OR-Tools, a _Round is returned as is.

    Returns the list that gets the seconds of every call.
    """
    real = solver._run_cp_sat
    pending = iter(entries)
    seconds: list[float] = []

    def fake(model: cp_model.CpModel, variables: Sequence[Any], budget: float) -> _Round:
        seconds.append(budget)
        entry = next(pending)
        return real(model, variables, budget) if isinstance(entry, str) else entry

    monkeypatch.setattr(solver, "_run_cp_sat", fake)
    return seconds


def clock(monkeypatch: pytest.MonkeyPatch, readings: Sequence[float]) -> list[float]:
    """Replace _monotonic with the readings in order. Returns the readings not yet used."""
    left = list(readings)
    monkeypatch.setattr(solver, "_monotonic", lambda: left.pop(0))
    return left


def three_equal() -> list[SolverCandidate]:
    return [person(3), person(5), person(9)]


def test_the_first_round_unknown_gives_unknown_and_no_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(monkeypatch, [UNKNOWN])

    result = run(golden())

    assert result == SolverResult((), {}, None, SolverStatus.UNKNOWN)


@pytest.mark.parametrize("bad", [INFEASIBLE, INVALID])
def test_the_first_round_infeasible_or_invalid_gives_model_invalid(
    monkeypatch: pytest.MonkeyPatch, bad: _Round
) -> None:
    script(monkeypatch, [bad])

    result = run(golden())

    assert result == SolverResult((), {}, None, SolverStatus.MODEL_INVALID)


def test_a_timeout_after_the_first_round_returns_the_kept_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(monkeypatch, ["real", UNKNOWN])
    # One cheapest group: 3 is the only costly one
    candidates = [person(1), person(2), person(3, hours=40)]

    result = run(candidates)

    assert result.status is SolverStatus.FEASIBLE
    assert set(result.first_wave) == {1, 2}
    assert result.objective_score == 2010


def test_a_later_unknown_keeps_the_plan_of_the_round_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(monkeypatch, ["real", _Round(SolverStatus.OPTIMAL, (0, 1, 1)), UNKNOWN])

    result = run(three_equal())

    assert result.status is SolverStatus.FEASIBLE
    assert set(result.first_wave) == {5, 9}


def test_a_later_feasible_round_is_used_and_stops_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script(
        monkeypatch,
        ["real", _Round(SolverStatus.OPTIMAL, (0, 1, 1)), _Round(SolverStatus.FEASIBLE, (1, 1, 0))],
    )

    result = run(three_equal())

    assert result.status is SolverStatus.FEASIBLE
    assert set(result.first_wave) == {3, 5}


@pytest.mark.parametrize("bad", [INFEASIBLE, INVALID])
def test_a_later_infeasible_or_invalid_round_is_not_hidden_by_the_kept_plan(
    monkeypatch: pytest.MonkeyPatch, bad: _Round
) -> None:
    script(monkeypatch, ["real", bad])

    result = run(golden())

    assert result == SolverResult((), {}, None, SolverStatus.MODEL_INVALID)


def test_without_candidates_the_model_is_never_built(monkeypatch: pytest.MonkeyPatch) -> None:
    seconds = script(monkeypatch, [])

    result = run([])

    assert result == SolverResult((), {}, None, SolverStatus.INFEASIBLE)
    assert seconds == []


def test_every_round_gets_what_is_left_of_one_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    left = clock(monkeypatch, [100.0, 100.5, 102.0, 103.5])
    seconds = script(monkeypatch, ["real", UNKNOWN])

    result = solver.solve(
        headcount_gap=1,
        role_gaps={1: 1},
        skill_gaps={},
        candidates=golden(),
        weights=WEIGHTS,
        time_limit_seconds=3,
    )

    assert seconds == [2.5, 1.0]
    assert result.status is SolverStatus.FEASIBLE
    # One reading for the deadline and one before each of the two rounds
    assert left == [103.5]


def test_a_round_without_budget_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    clock(monkeypatch, [100.0, 103.0])
    seconds = script(monkeypatch, [])

    result = solver.solve(
        headcount_gap=1,
        role_gaps={1: 1},
        skill_gaps={},
        candidates=golden(),
        weights=WEIGHTS,
        time_limit_seconds=3,
    )

    assert seconds == []
    assert result == SolverResult((), {}, None, SolverStatus.UNKNOWN)


def test_the_solver_runs_with_one_worker_the_fixed_seed_and_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[int, int, float]] = []
    real_solver = cp_model.CpSolver

    class Spy(real_solver):
        def solve(self, model: cp_model.CpModel, *args: Any, **kwargs: Any) -> Any:
            parameters = self.parameters
            seen.append(
                (parameters.num_workers, parameters.random_seed, parameters.max_time_in_seconds)
            )
            return super().solve(model, *args, **kwargs)

    readings = iter([100.0] + [100.5] * 100)
    monkeypatch.setattr(solver, "_monotonic", lambda: next(readings))
    monkeypatch.setattr(solver.cp_model, "CpSolver", Spy)

    solver.solve(
        headcount_gap=1,
        role_gaps={1: 1},
        skill_gaps={},
        candidates=golden(),
        weights=WEIGHTS,
        time_limit_seconds=3,
    )

    assert seen
    assert set(seen) == {(1, 0, 2.5)}


def test_the_same_input_twice_gives_equal_results() -> None:
    assert run(golden()) == run(golden())
