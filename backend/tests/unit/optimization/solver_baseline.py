"""Recorded results of the round 1 Solver (round 2 contract, sections 4.5 and 6, PR A).

data/solver_baseline.jsonl holds one problem per line with what solve() returned
for it at staging 01bf04b, SOLVER_VERSION "weighted-v1". Round 2 replaces the
search with OR-Tools and must still return these results when its status is
OPTIMAL (R2-Q3). No problem has a gap above 5 or more than 30 candidates (R2-Q34).

The file is a record: build_solver_baseline.py does not replace it unless told to.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.domain.constraints.penalties import SoftWeights
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource, SelectionType, SolverStatus, TargetType
from app.domain.staffing.wave_targets import TargetCredit
from app.domain.workflow.case_status import GapFiller
from app.optimization.solver import SolverCandidate, SolverResult, solve

DATA_FILE = Path(__file__).parent / "data" / "solver_baseline.jsonl"
# Generous, so the status of a real search never depends on machine speed
LIMIT = 60

_WEIGHT_NAMES = (
    "candidate_count",
    "consecutive_shift",
    "workload_imbalance",
    "projected_overtime",
    "roster_change",
    "candidate_source",
)


@dataclass(frozen=True)
class Problem:
    """The arguments of one solve() call."""

    name: str
    weights: SoftWeights
    headcount_gap: int
    role_gaps: dict[int, int]
    skill_gaps: dict[int, int]
    candidates: tuple[SolverCandidate, ...]


@dataclass(frozen=True)
class Recorded:
    """The three SolverResult values a plan stores. first_wave keeps its order.

    status is set by run_case only: the file records the round 1 results, which had none.
    """

    ranked_staff_ids: tuple[int, ...]
    first_wave: tuple[tuple[int, tuple[TargetCredit, ...]], ...]
    objective_score: Fraction | None
    status: SolverStatus | None = None


def run_case(problem: Problem, *, solver: Callable[..., SolverResult] = solve) -> Recorded:
    """Solve one problem. The only place the baseline calls the Solver."""
    result = solver(
        headcount_gap=problem.headcount_gap,
        role_gaps=problem.role_gaps,
        skill_gaps=problem.skill_gaps,
        candidates=problem.candidates,
        weights=problem.weights,
        time_limit_seconds=LIMIT,
    )
    return Recorded(
        ranked_staff_ids=tuple(result.ranked_staff_ids),
        first_wave=tuple(
            (staff_id, tuple(credits)) for staff_id, credits in result.first_wave.items()
        ),
        objective_score=result.objective_score,
        status=result.status,
    )


def encode_problem(problem: Problem) -> dict[str, Any]:
    weights: dict[str, Any] = {name: str(getattr(problem.weights, name)) for name in _WEIGHT_NAMES}
    weights["source_order"] = [source.value for source in problem.weights.source_order]
    return {
        "name": problem.name,
        "weights": weights,
        "headcount_gap": problem.headcount_gap,
        "role_gaps": [list(pair) for pair in sorted(problem.role_gaps.items())],
        "skill_gaps": [list(pair) for pair in sorted(problem.skill_gaps.items())],
        "candidates": [
            [
                candidate.filler.staff_id,
                candidate.filler.role_id,
                sorted(candidate.filler.skill_ids),
                candidate.metrics.source.value,
                str(candidate.metrics.hours_this_week),
                candidate.metrics.projected_consecutive_shifts,
                str(candidate.metrics.overtime_hours),
            ]
            for candidate in problem.candidates
        ],
    }


def encode_recorded(recorded: Recorded) -> dict[str, Any]:
    score = recorded.objective_score
    return {
        "ranked_staff_ids": list(recorded.ranked_staff_ids),
        "first_wave": [
            [
                staff_id,
                [
                    [
                        credit.target_type.value,
                        credit.selection_type.value,
                        credit.role_id,
                        credit.skill_id,
                    ]
                    for credit in credits
                ],
            ]
            for staff_id, credits in recorded.first_wave
        ],
        "objective_score": None if score is None else str(score),
    }


def encode_line(problem: Problem, recorded: Recorded) -> str:
    row = {**encode_problem(problem), "expected": encode_recorded(recorded)}
    return json.dumps(row, separators=(",", ":"))


def decode_line(line: str) -> tuple[Problem, Recorded]:
    row = json.loads(line)
    weights = row["weights"]
    problem = Problem(
        name=row["name"],
        weights=SoftWeights(
            **{name: Fraction(weights[name]) for name in _WEIGHT_NAMES},
            source_order=tuple(CandidateSource(value) for value in weights["source_order"]),
        ),
        headcount_gap=row["headcount_gap"],
        role_gaps={role_id: gap for role_id, gap in row["role_gaps"]},
        skill_gaps={skill_id: gap for skill_id, gap in row["skill_gaps"]},
        candidates=tuple(
            SolverCandidate(
                filler=GapFiller(
                    staff_id=staff_id, role_id=role_id, skill_ids=frozenset(skill_ids)
                ),
                metrics=SoftMetrics(
                    staff_id=staff_id,
                    source=CandidateSource(source),
                    hours_this_week=Fraction(hours),
                    projected_consecutive_shifts=run,
                    overtime_hours=Fraction(overtime),
                ),
            )
            for staff_id, role_id, skill_ids, source, hours, run, overtime in row["candidates"]
        ),
    )
    expected = row["expected"]
    score = expected["objective_score"]
    recorded = Recorded(
        ranked_staff_ids=tuple(expected["ranked_staff_ids"]),
        first_wave=tuple(
            (
                staff_id,
                tuple(
                    TargetCredit(
                        TargetType(target),
                        SelectionType(selection),
                        role_id=role_id,
                        skill_id=skill_id,
                    )
                    for target, selection, role_id, skill_id in credits
                ),
            )
            for staff_id, credits in expected["first_wave"]
        ),
        objective_score=None if score is None else Fraction(score),
    )
    return problem, recorded


def load_cases() -> list[tuple[Problem, Recorded]]:
    lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    return [decode_line(line) for line in lines if line.strip()]
