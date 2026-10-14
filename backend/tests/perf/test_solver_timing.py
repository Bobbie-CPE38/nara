"""Timing of the OR-Tools solver on the problem sizes of round 2 contract section 4.6.

Skipped unless the environment has SOLVER_TIMING=1, so the normal suite never runs it:

    SOLVER_TIMING=1 pytest tests/perf -s -q

Two things are measured for each size, on three random data sets each:
  * Part 1: solve() alone with a 3 second limit, on candidates built in memory.
  * Part 2: the whole of create_plan() on the seeded database with that many
    candidates, and how much of it is solve(). The limit bounds only the search,
    while the database locks are held for the whole of create_plan().
The table is printed at the end, and appended to the file named by
GITHUB_STEP_SUMMARY when that is set. It measures: nothing here asserts a speed
or a status, only that a plan that comes back closes the targets it was given.
"""

import os
import platform
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ortools
import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Skill,
    Staff,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffSkill,
)
from app.domain.enums import SolverStatus, StaffStatus
from app.domain.staffing.wave_targets import wave_target
from app.optimization import solver
from app.optimization.solver import SolverCandidate, SolverResult
from app.services import gap_service, optimization_service
from tests.integration.case_rows import leave, make_case, record_gap
from tests.unit.optimization.build_solver_baseline import SEED, SKILLS, Rng, person
from tests.unit.optimization.solver_baseline import Problem

pytestmark = pytest.mark.skipif(
    os.environ.get("SOLVER_TIMING") != "1",
    reason="Timing harness: set SOLVER_TIMING=1 to run it",
)

TIME_LIMIT = 3
# (gap, candidates): the table of contract section 4.6
SIZES = ((1, 3), (1, 300), (2, 300), (5, 60), (5, 300), (10, 30), (10, 300))
DATA_SETS = 3
# Seeds are fixed so the same problems come out on every machine
SEED_BASE = 4600
LEAVING_STAFF_ID = 105
FIRST_NEW_STAFF_ID = 1000
# The Golden Case already has three free RNs on the night shift: 201, 202 and 203
GOLDEN_CANDIDATES = 3
RN = 1
# After 105 leaves, shift 1 has four people on the roster: all RN, two with ICU, three with BLS
ON_ROSTER = 4
SKILLS_ON_ROSTER = {SKILLS[0]: 2, SKILLS[1]: 3}
ROLES = (1, 2)
Size = tuple[int, int]


@dataclass
class Row:
    """Everything measured for one size."""

    solve_ms: list[float] = field(default_factory=list)
    statuses: Counter[str] = field(default_factory=Counter)
    rounds: list[int] = field(default_factory=list)
    plan_ms: list[float] = field(default_factory=list)
    plan_solve_ms: list[float] = field(default_factory=list)
    plan_statuses: Counter[str] = field(default_factory=Counter)


RESULTS: dict[Size, Row] = {size: Row() for size in SIZES}


def _seed_of(size: Size, data_set: int) -> int:
    return SEED_BASE + 100 * SIZES.index(size) + data_set


def _gaps(gap: int) -> tuple[dict[int, int], dict[int, int]]:
    """Role and skill gaps with the kinds of constraint real cases have.

    One of the two roles is short by the gap. Two of the four skills are short,
    the first by the gap and the second by half of it (at least 1).
    """
    return {RN: gap}, {SKILLS[0]: gap, SKILLS[1]: max(1, gap // 2)}


def _problem(gap: int, count: int, seed: int) -> Problem:
    """Random candidates: whole-number hours and overtime, runs 1 to 7, two roles, four skills."""
    rng = Rng(seed)
    free_ids = list(range(1, 1000))
    candidates = []
    for _ in range(count):
        staff_id = free_ids.pop(rng.below(len(free_ids)))
        hours = 8 * rng.below(7)
        overtime = (0, 0, 0, 2, 4)[rng.below(5)]
        run = rng.between(1, 7)
        skills = rng.some(SKILLS, 0.35)
        role = ROLES[rng.below(len(ROLES))]
        candidates.append(
            person(staff_id, *skills, role=role, hours=hours, run=run, overtime=overtime)
        )
    role_gaps, skill_gaps = _gaps(gap)
    return Problem(
        name=f"timing/g{gap}n{count}s{seed}",
        weights=SEED,
        headcount_gap=gap,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        candidates=tuple(candidates),
    )


def _assert_closes_targets(
    candidates: Sequence[SolverCandidate],
    result: SolverResult,
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
) -> None:
    """A plan that came back covers the wave targets, lowered to what the candidates can give."""
    if result.status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return
    assert set(result.ranked_staff_ids) == {c.filler.staff_id for c in candidates}
    wave = [c for c in candidates if c.filler.staff_id in result.first_wave]
    assert len(wave) >= min(wave_target(headcount_gap), len(candidates))
    for role_id, gap in role_gaps.items():
        holders = sum(1 for c in candidates if c.filler.role_id == role_id)
        in_wave = sum(1 for c in wave if c.filler.role_id == role_id)
        assert in_wave >= min(wave_target(gap), holders)
    for skill_id, gap in skill_gaps.items():
        holders = sum(1 for c in candidates if skill_id in c.filler.skill_ids)
        in_wave = sum(1 for c in wave if skill_id in c.filler.skill_ids)
        assert in_wave >= min(wave_target(gap), holders)


@pytest.fixture
def count_rounds(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """Wrap the one function that runs a CP-SAT round; the callable returns the rounds so far."""
    real = solver._run_cp_sat
    rounds: list[int] = []

    def counted(*args: Any, **kwargs: Any) -> Any:
        rounds.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(solver, "_run_cp_sat", counted)
    return lambda: len(rounds)


@pytest.fixture(scope="module", autouse=True)
def print_table() -> Iterator[None]:
    yield
    lines = _table()
    print("\n" + "\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")


def _slowest(values: Sequence[float]) -> str:
    return f"{max(values):.0f}" if values else "-"


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{name} x{count}" for name, count in sorted(counter.items())) or "-"


def _table() -> list[str]:
    lines = [
        f"### Solver timing: Python {platform.python_version()}, ortools {ortools.__version__}, "
        f"{os.cpu_count()} CPUs, time limit {TIME_LIMIT} s, {DATA_SETS} data sets per size",
        "",
        "| Gap | Candidates | Slowest solve() ms | Statuses | Most rounds in one solve "
        "| Slowest create_plan() ms | solve() inside that create_plan() ms |",
        "|---:|---:|---:|---|---:|---:|---:|",
    ]
    for (gap, count), row in RESULTS.items():
        slowest = max(range(len(row.plan_ms)), key=row.plan_ms.__getitem__, default=None)
        inside = "-" if slowest is None else f"{row.plan_solve_ms[slowest]:.0f}"
        rounds = str(max(row.rounds)) if row.rounds else "-"
        lines.append(
            f"| {gap} | {count} | {_slowest(row.solve_ms)} | {_counts(row.statuses)} | {rounds} "
            f"| {_slowest(row.plan_ms)} | {inside} |"
        )
    plan_statuses = "; ".join(
        f"gap {gap} / {count}: {_counts(row.plan_statuses)}"
        for (gap, count), row in RESULTS.items()
    )
    lines += [
        "",
        "Slowest solve(), statuses and rounds: solve() alone on random in-memory candidates "
        "(2 roles, 4 skills).",
        "create_plan(): the whole function on the seeded test database; the extra staff are all "
        "RN with random skills out of 4, and the solve() time is taken from the same run.",
        f"Statuses of the create_plan() runs: {plan_statuses}.",
    ]
    return lines


@pytest.mark.parametrize("size", SIZES)
def test_solve_alone(size: Size, count_rounds: Callable[[], int]) -> None:
    gap, count = size
    row = RESULTS[size]
    for data_set in range(DATA_SETS):
        problem = _problem(gap, count, _seed_of(size, data_set))
        before = count_rounds()
        started = time.perf_counter()
        result = solver.solve(
            headcount_gap=problem.headcount_gap,
            role_gaps=problem.role_gaps,
            skill_gaps=problem.skill_gaps,
            candidates=problem.candidates,
            weights=problem.weights,
            time_limit_seconds=TIME_LIMIT,
        )
        elapsed = time.perf_counter() - started
        row.solve_ms.append(elapsed * 1000)
        row.statuses[result.status.value] += 1
        row.rounds.append(count_rounds() - before)
        _assert_closes_targets(
            problem.candidates,
            result,
            headcount_gap=problem.headcount_gap,
            role_gaps=problem.role_gaps,
            skill_gaps=problem.skill_gaps,
        )


def _grow_case(db: Session, gap: int, extra_staff: int, seed: int) -> None:
    """Make the gap of shift 1 `gap` people, and give ward 1 `extra_staff` more free RNs.

    A requirement of ON_ROSTER + gap leaves a headcount gap of `gap`. The RN role and
    skills 1 (ICU) and 2 (BLS) are raised to be short by the amounts of _gaps().
    """
    leave(db, LEAVING_STAFF_ID)
    db.add_all(Skill(id=skill_id, name=f"PERF_{skill_id}") for skill_id in SKILLS[2:])
    db.flush()
    rng = Rng(seed)
    staff = [
        Staff(
            id=FIRST_NEW_STAFF_ID + index,
            first_name="Perf",
            last_name=str(FIRST_NEW_STAFF_ID + index),
            email=f"{FIRST_NEW_STAFF_ID + index}@perf.local",
            password_hash="!",
            role_id=RN,
            home_ward_id=1,
            status=StaffStatus.ACTIVE,
        )
        for index in range(extra_staff)
    ]
    db.add_all(staff)
    db.flush()
    db.add_all(
        StaffSkill(staff_id=member.id, skill_id=skill_id)
        for member in staff
        for skill_id in rng.some(SKILLS, 0.35)
    )
    requirement = db.get(StaffingRequirement, 1)
    role = db.get(StaffingRequirementRole, (1, RN))
    icu = db.get(StaffingRequirementSkill, (1, SKILLS[0]))
    assert requirement is not None and role is not None and icu is not None
    role_gaps, skill_gaps = _gaps(gap)
    requirement.required_staff = ON_ROSTER + gap
    requirement.minimum_staff = ON_ROSTER + gap
    role.required_count = ON_ROSTER + role_gaps[RN]
    icu.required_count = SKILLS_ON_ROSTER[SKILLS[0]] + skill_gaps[SKILLS[0]]
    db.add(
        StaffingRequirementSkill(
            staffing_requirement_id=1,
            skill_id=SKILLS[1],
            required_count=SKILLS_ON_ROSTER[SKILLS[1]] + skill_gaps[SKILLS[1]],
        )
    )
    db.flush()


@pytest.mark.parametrize("size", SIZES)
def test_create_plan(
    size: Size,
    seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gap, count = size
    row = RESULTS[size]
    real_solve = optimization_service.solve
    for data_set in range(DATA_SETS):
        # Each data set runs in a savepoint: the next one starts from the seeded database
        with seeded.begin_nested() as savepoint:
            _grow_case(seeded, gap, count - GOLDEN_CANDIDATES, _seed_of(size, data_set))
            case = make_case(seeded, shift_id=1)
            record_gap(seeded, case)
            case_gap = gap_service.get_case_gap(seeded, case.id)
            # A wrong setup must fail here, not time a different problem
            assert case_gap.headcount_gap == gap
            assert (case_gap.role_gaps, case_gap.skill_gaps) == _gaps(gap)

            seen: dict[str, Any] = {"solve_seconds": 0.0}

            def timed_solve(*, seen: dict[str, Any] = seen, **kwargs: Any) -> SolverResult:
                started = time.perf_counter()
                result = real_solve(**kwargs)
                seen["solve_seconds"] += time.perf_counter() - started
                seen["candidates"] = kwargs["candidates"]
                seen["result"] = result
                return result

            monkeypatch.setattr(optimization_service, "solve", timed_solve)
            started = time.perf_counter()
            plan = optimization_service.create_plan(seeded, case)
            elapsed = time.perf_counter() - started
            monkeypatch.setattr(optimization_service, "solve", real_solve)

            assert len(seen["candidates"]) == count
            row.plan_ms.append(elapsed * 1000)
            row.plan_solve_ms.append(seen["solve_seconds"] * 1000)
            row.plan_statuses[plan.plan.solver_status.value] += 1
            _assert_closes_targets(
                seen["candidates"],
                seen["result"],
                headcount_gap=case_gap.headcount_gap,
                role_gaps=case_gap.role_gaps,
                skill_gaps=case_gap.skill_gaps,
            )
            savepoint.rollback()
