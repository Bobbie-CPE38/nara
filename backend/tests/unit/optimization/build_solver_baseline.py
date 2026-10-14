"""Build data/solver_baseline.jsonl from the Solver that is checked out.

Run from backend/ inside the container:

    python -m tests.unit.optimization.build_solver_baseline

It stops when the file exists, unless --overwrite is given: the file records the
round 1 Solver, and a later Solver is compared with it, not written over it.

The problems are the hand-made ones, each with the wave it must give, followed by
seven random families of 30. Draws use random.Random.random() only, the sequence
Python keeps stable between versions, so the same problems come out everywhere.
"""

import argparse
import random
import time
from collections.abc import Sequence
from fractions import Fraction
from typing import Any

from app.domain.constraints.penalties import SoftWeights
from app.domain.constraints.soft_metrics import SoftMetrics
from app.domain.enums import CandidateSource
from app.domain.workflow.case_status import GapFiller
from app.optimization.solver import SolverCandidate
from tests.unit.optimization.solver_baseline import DATA_FILE, Problem, encode_line, run_case

SAME, FLOAT, CROSS = (
    CandidateSource.SAME_WARD,
    CandidateSource.FLOAT_POOL,
    CandidateSource.CROSS_WARD,
)
ROLES = (1, 2)
SKILLS = (1, 2, 3, 4)
# R2-Q34: the round 1 search finishes quickly up to this size
MAX_CANDIDATES = 30
MAX_GAP = 5
CASES_PER_FAMILY = 30


def soft_weights(
    candidate_count: int | Fraction = 1000,
    consecutive_shift: int | Fraction = 5,
    workload_imbalance: int | Fraction = 1,
    projected_overtime: int | Fraction = 2,
    candidate_source: int | Fraction = 200,
) -> SoftWeights:
    """The seeded SOFT_CONSTRAINT_POLICY weights unless a value is given."""
    return SoftWeights(
        candidate_count=Fraction(candidate_count),
        consecutive_shift=Fraction(consecutive_shift),
        workload_imbalance=Fraction(workload_imbalance),
        projected_overtime=Fraction(projected_overtime),
        roster_change=Fraction(300),
        candidate_source=Fraction(candidate_source),
        source_order=(SAME, FLOAT, CROSS),
    )


SEED = soft_weights()


def person(
    staff_id: int,
    *skills: int,
    role: int = 1,
    hours: int | Fraction = 0,
    run: int = 1,
    overtime: int | Fraction = 0,
    source: CandidateSource = SAME,
) -> SolverCandidate:
    return SolverCandidate(
        filler=GapFiller(staff_id=staff_id, role_id=role, skill_ids=frozenset(skills)),
        metrics=SoftMetrics(
            staff_id=staff_id,
            source=source,
            hours_this_week=Fraction(hours),
            projected_consecutive_shifts=run,
            overtime_hours=Fraction(overtime),
        ),
    )


def problem(
    name: str,
    candidates: Sequence[SolverCandidate],
    *,
    headcount: int = 1,
    roles: dict[int, int] | None = None,
    skills: dict[int, int] | None = None,
    weights: SoftWeights = SEED,
) -> Problem:
    """Defaults are the Golden Case gap: one person and one RN short."""
    return Problem(
        name=name,
        weights=weights,
        headcount_gap=headcount,
        role_gaps={1: 1} if roles is None else roles,
        skill_gaps=skills or {},
        candidates=tuple(candidates),
    )


def hand_made() -> list[tuple[Problem, list[int]]]:
    """Problems with a known answer, each with the staff IDs of the wave it must give."""
    x, y, k, z = SKILLS
    tired = {"hours": 52, "run": 7, "overtime": 12}
    only_skills: dict[str, Any] = {"headcount": 0, "roles": {}}
    four_skills = {x: 1, y: 1, k: 1, z: 1}
    only_hours = soft_weights(0, 0, 1, 0, 0)
    no_weights = soft_weights(0, 0, 0, 0, 0)
    small_fractions = soft_weights(0, 0, Fraction(1, 3), Fraction(1, 7), 0)
    return [
        # The six pairs the seeded weights were set with (round 1 contract, 8.3).
        # The cheaper side has the higher IDs, so the ID tie-break cannot be what picks it.
        (
            problem(
                "pair/one_tired_over_two_fresh",
                [
                    person(1, x),
                    person(2, x),
                    person(3, y),
                    person(4, y),
                    person(11, x, y, **tired),
                    person(12, x, y, **tired),
                ],
                skills={x: 1, y: 1},
                **only_skills,
            ),
            [11, 12],
        ),
        (
            problem(
                "pair/same_ward_over_float",
                [
                    person(1, source=FLOAT),
                    person(2, source=FLOAT),
                    person(11, **tired),
                    person(12, **tired),
                ],
            ),
            [11, 12],
        ),
        (
            problem(
                "pair/float_over_cross",
                [
                    person(1, source=CROSS),
                    person(2, source=CROSS),
                    person(11, source=FLOAT),
                    person(12, source=FLOAT),
                ],
            ),
            [11, 12],
        ),
        (
            problem(
                "pair/hours",
                [
                    person(1, hours=40),
                    person(2, hours=40),
                    person(11, hours=24),
                    person(12, hours=24),
                ],
            ),
            [11, 12],
        ),
        (
            problem(
                "pair/run",
                [person(1, hours=16), person(2, hours=16), person(11, run=3), person(12, run=3)],
            ),
            [11, 12],
        ),
        (
            problem(
                "pair/ot",
                [
                    person(1, run=3),
                    person(2, run=3),
                    person(11, overtime=4),
                    person(12, overtime=4),
                ],
            ),
            [11, 12],
        ),
        # Problems the round 1 tests already use.
        (
            problem(
                "golden", [person(201), person(202, hours=8, run=2), person(203, hours=8, run=2)]
            ),
            [201, 202],
        ),
        (
            problem(
                "skill_gap",
                [
                    person(201, x, y),
                    person(202, y, hours=8, run=2),
                    person(203, x, hours=8, run=2),
                ],
                skills={x: 1},
            ),
            [201, 203],
        ),
        (
            problem(
                "rank_disagrees_with_penalty",
                [person(1, hours=10, run=5), person(2, hours=12, run=1), person(3, hours=40)],
            ),
            [1, 2],
        ),
        # Ties: fewer people first, then the lower staff IDs.
        (problem("tie/lower_ids", [person(5), person(3), person(9)]), [3, 5]),
        # 200 is the only holder of z, so every group has 200. Three groups cost the same:
        # 201+204, 202+203 and 202+204. The first two have the same ID sum.
        (
            problem(
                "tie/equal_id_sum",
                [
                    person(200, x, y, k, z),
                    person(201, x),
                    person(204, y, k),
                    person(202, x, k),
                    person(203, y),
                ],
                skills=four_skills,
                **only_skills,
            ),
            [200, 201, 204],
        ),
        # 209+203 and 201+202 cost the same. The round 1 search meets 209+203 first,
        # because 209 is the cheapest person, and must still end on 201+202.
        (
            problem(
                "tie/search_order_differs",
                [
                    person(200, x, y, k, z),
                    person(209, x),
                    person(203, y, k, hours=16),
                    person(201, x, k, hours=8),
                    person(202, y, hours=8),
                ],
                skills=four_skills,
                **only_skills,
            ),
            [200, 201, 202],
        ),
        # 2, 3 and 4 people cost 32 each: {21, 22}, {1, 3, 21} and {1, 2, 3, 4}.
        (
            problem(
                "tie/fewer_people",
                [
                    person(1, x, hours=8),
                    person(2, x, hours=8),
                    person(3, y, hours=8),
                    person(4, y, hours=8),
                    person(21, x, y, hours=16),
                    person(22, x, y, hours=16),
                ],
                skills={x: 1, y: 1},
                weights=only_hours,
                **only_skills,
            ),
            [21, 22],
        ),
        (
            problem(
                "tie/all_weights_zero",
                [person(7, x), person(3), person(5, x, y), person(9, y), person(4, x, y)],
                headcount=2,
                roles={},
                skills={x: 1, y: 1},
                weights=no_weights,
            ),
            [3, 4, 5],
        ),
        # Targets nobody can reach are lowered to the people who match.
        (problem("lowered/one_candidate", [person(201)]), [201]),
        (
            problem(
                "lowered/skill_nobody_holds",
                [person(1), person(2, role=2), person(3)],
                headcount=2,
                roles={2: 2},
                skills={9: 1},
            ),
            [1, 2, 3],
        ),
        (problem("edge/no_candidates", []), []),
        (
            problem(
                "edge/nothing_to_fill", [person(2, hours=8), person(1, hours=16)], **only_skills
            ),
            [],
        ),
        # Penalties 7/2, 43/12 and 43/12 again: close, and not whole numbers.
        (
            problem(
                "fraction/close_scores",
                [
                    person(1, hours=Fraction(21, 2)),
                    person(2, hours=10, overtime=Fraction(7, 4)),
                    person(3, hours=Fraction(43, 4)),
                ],
                weights=small_fractions,
            ),
            [1, 2],
        ),
    ]


class Rng:
    """Whole-number draws from random(), the one sequence Python keeps stable."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def below(self, limit: int) -> int:
        return int(self._random.random() * limit)

    def between(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def some(self, values: Sequence[int], chance: float) -> list[int]:
        return [value for value in values if self._random.random() < chance]


def random_problem(
    rng: Rng, name: str, weights: SoftWeights, sources: Sequence[CandidateSource], metrics: str
) -> Problem:
    """One random problem. The order of the draws is part of the recorded data."""
    free_ids = list(range(1, 100))
    candidates = []
    for _ in range(rng.between(1, MAX_CANDIDATES)):
        staff_id = free_ids.pop(rng.below(len(free_ids)))
        if metrics == "coarse":
            hours, overtime, run = Fraction(8 * rng.below(2)), Fraction(0), 1
        elif metrics == "fractional":
            hours = Fraction(rng.between(0, 104), 2)
            overtime = Fraction(rng.between(0, 240), 60)
            run = rng.between(1, 7)
        else:
            hours = Fraction(8 * rng.below(7))
            overtime = Fraction((0, 0, 0, 2, 4)[rng.below(5)])
            run = rng.between(1, 7)
        skills = rng.some(SKILLS, 0.35)
        role = ROLES[rng.below(len(ROLES))]
        source = sources[rng.below(len(sources))]
        candidates.append(
            person(
                staff_id,
                *skills,
                role=role,
                hours=hours,
                run=run,
                overtime=overtime,
                source=source,
            )
        )
    headcount = rng.between(0, MAX_GAP)
    role_gaps = {role_id: rng.between(1, MAX_GAP) for role_id in rng.some(ROLES, 0.5)}
    skill_gaps = {skill_id: rng.between(1, MAX_GAP) for skill_id in rng.some(SKILLS, 0.4)}
    return problem(
        name, candidates, headcount=headcount, roles=role_gaps, skills=skill_gaps, weights=weights
    )


EVERY_SOURCE = (SAME, FLOAT, CROSS)
# (name, seed, weights, sources, metrics)
FAMILIES: tuple[tuple[str, int, SoftWeights, tuple[CandidateSource, ...], str], ...] = (
    ("seed_integer", 101, SEED, (SAME,), "integer"),
    ("seed_fractional", 102, SEED, (SAME,), "fractional"),
    ("mixed_source", 103, SEED, EVERY_SOURCE, "integer"),
    (
        "fractional_weights",
        104,
        soft_weights(1000, Fraction(7, 2), Fraction(1, 3), Fraction(5, 4), 200),
        EVERY_SOURCE,
        "fractional",
    ),
    ("zero_weights", 105, soft_weights(0, 0, 0, 0, 0), (SAME,), "integer"),
    ("free_headcount", 106, soft_weights(candidate_count=0), EVERY_SOURCE, "integer"),
    ("coarse_ties", 107, soft_weights(1000, 0, 1, 0, 0), (SAME,), "coarse"),
)


def build_problems() -> list[Problem]:
    problems = [made for made, _ in hand_made()]
    for family, seed, weights, sources, metrics in FAMILIES:
        rng = Rng(seed)
        problems += [
            random_problem(rng, f"{family}/{index:03d}", weights, sources, metrics)
            for index in range(CASES_PER_FAMILY)
        ]
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Record what the checked-out Solver returns.")
    parser.add_argument("--overwrite", action="store_true", help="replace the recorded file")
    arguments = parser.parse_args()
    if DATA_FILE.exists() and not arguments.overwrite:
        parser.error(f"{DATA_FILE} exists and records the round 1 Solver. See --overwrite.")

    waves = {made.name: wave for made, wave in hand_made()}
    started = time.perf_counter()
    lines = []
    for item in build_problems():
        recorded = run_case(item)
        wave = sorted(staff_id for staff_id, _ in recorded.first_wave)
        if item.name in waves and wave != waves[item.name]:
            raise SystemExit(f"{item.name}: wave {wave}, expected {waves[item.name]}")
        lines.append(encode_line(item, recorded))

    DATA_FILE.parent.mkdir(exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")
    print(f"{len(lines)} problems in {time.perf_counter() - started:.1f} s -> {DATA_FILE}")


if __name__ == "__main__":
    main()
