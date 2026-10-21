"""The frozen case set of the model trial (draft section 3.2, step 3).

Each case is a payload built by explanation_service.build_payload() from a synthetic plan
snapshot, so it has the exact shape the app sends. The generator is deterministic: the same
seed gives the same file. The file is written once, then every model reads that file.

`forbidden` holds names, codes and LINE IDs of the people in the case. They are never in the
payload (build_payload drops staff_id), so a model can only print one by inventing it.
"""

import json
import random
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from app.domain.constraints.penalties import SoftWeights, candidate_penalty
from app.domain.constraints.score_breakdown import exact_fields, fraction_text, weights_snapshot
from app.domain.constraints.soft_metrics import SoftMetrics, source_priority
from app.domain.enums import CandidateSource
from app.domain.staffing.wave_targets import wave_target
from app.services import explanation_service

SEED = 20261021
CASE_COUNT = 30

# Synthetic weights: the trial needs plausible numbers, not the policy row of any ward
WEIGHTS = SoftWeights(
    candidate_count=Fraction(10),
    consecutive_shift=Fraction(5),
    workload_imbalance=Fraction(1, 2),
    projected_overtime=Fraction(3),
    roster_change=Fraction(0),
    candidate_source=Fraction(4),
    source_order=(
        CandidateSource.SAME_WARD,
        CandidateSource.FLOAT_POOL,
        CandidateSource.CROSS_WARD,
    ),
)

_GIVEN = ["สมชาย", "สมหญิง", "วิชัย", "มาลี", "ประยุทธ", "นภา", "อนันต์", "กมล", "สุดา", "ธนา"]
_FAMILY = ["ใจดี", "รักษา", "แสงทอง", "บุญมี", "ศรีสุข", "พึ่งพา", "วงศ์ไทย", "เจริญ"]

# kind -> number of cases. The sum is CASE_COUNT
KINDS = {"normal": 8, "partial": 5, "over_ten": 5, "single": 4, "ties": 4, "mixed_sources": 4}


@dataclass(frozen=True)
class Case:
    key: str
    kind: str
    input_hash: str
    payload: dict[str, Any]
    forbidden: list[str]

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "input_hash": self.input_hash,
            "payload": self.payload,
            "forbidden": self.forbidden,
        }


def _metrics(rng: random.Random, staff_id: int, source: CandidateSource) -> SoftMetrics:
    return SoftMetrics(
        staff_id=staff_id,
        source=source,
        hours_this_week=Fraction(rng.randrange(0, 49 * 4), 4),
        projected_consecutive_shifts=rng.randrange(0, 6),
        overtime_hours=Fraction(rng.randrange(0, 13 * 4), 4),
    )


def _tied(rng: random.Random, staff_id: int, like: SoftMetrics) -> SoftMetrics:
    """Same score and same ranking key as `like`: only staff_id tells them apart."""
    del rng
    return SoftMetrics(
        staff_id=staff_id,
        source=like.source,
        hours_this_week=like.hours_this_week,
        projected_consecutive_shifts=like.projected_consecutive_shifts,
        overtime_hours=like.overtime_hours,
    )


def _ranking_key(m: SoftMetrics) -> tuple[Any, ...]:
    return (
        source_priority(m.source, WEIGHTS.source_order),
        m.hours_this_week,
        m.projected_consecutive_shifts,
        m.overtime_hours,
        m.staff_id,
    )


def _people(rng: random.Random, kind: str) -> list[SoftMetrics]:
    sources = list(CandidateSource)
    if kind == "single":
        return [_metrics(rng, 1, CandidateSource.SAME_WARD)]
    if kind == "over_ten":
        count = rng.randrange(12, 16)
    elif kind == "ties":
        count = rng.randrange(4, 7)
    else:
        count = rng.randrange(3, 9)
    people = []
    for staff_id in range(1, count + 1):
        source = sources[(staff_id - 1) % 3] if kind == "mixed_sources" else rng.choice(sources[:2])
        people.append(_metrics(rng, staff_id, source))
    if kind == "ties":
        people[1] = _tied(rng, 2, people[0])
        people[2] = _tied(rng, 3, people[0])
    return people


def _plan(rng: random.Random, kind: str) -> SimpleNamespace:
    people = sorted(_people(rng, kind), key=_ranking_key)
    wave_size = min(len(people), rng.randrange(1, 4))
    headcount_gap = rng.randrange(1, 4) if kind != "single" else 1
    snapshot_candidates = []
    for position, person in enumerate(people):
        first_wave = position < wave_size
        snapshot_candidates.append(
            {
                "staff_id": person.staff_id,
                "source": person.source.value,
                "first_wave": first_wave,
                "projected_consecutive_shifts": person.projected_consecutive_shifts,
                **exact_fields(person, WEIGHTS),
            }
        )
    penalty = sum((candidate_penalty(p, WEIGHTS) for p in people[:wave_size]), Fraction(0))
    snapshot = {
        "weights": weights_snapshot(WEIGHTS),
        "targets": {
            "headcount": {"gap": headcount_gap, "target": wave_target(headcount_gap)},
            "roles": [{"role_id": 1, "gap": 1, "target": wave_target(1)}],
            "skills": [],
        },
        "partial_plan": kind == "partial",
        "candidates": snapshot_candidates,
    }
    return SimpleNamespace(input_snapshot=snapshot, objective_score=fraction_text(penalty))


def generate_cases(seed: int = SEED) -> list[Case]:
    rng = random.Random(seed)
    cases: list[Case] = []
    for kind, count in KINDS.items():
        for _ in range(count):
            plan = _plan(rng, kind)
            payload = explanation_service.build_payload(cast(Any, plan))
            names = [
                f"{rng.choice(_GIVEN)} {rng.choice(_FAMILY)}"
                for _ in plan.input_snapshot["candidates"]
            ]
            ids = [f"EMP{rng.randrange(10000, 99999)}" for _ in names]
            line = [f"U{rng.getrandbits(128):032x}" for _ in names]
            cases.append(
                Case(
                    key=f"case-{len(cases) + 1:02d}",
                    kind=kind,
                    input_hash=explanation_service.input_hash(payload),
                    payload=payload,
                    forbidden=names + ids + line,
                )
            )
    return cases


def save_cases(cases: list[Case], path: Path) -> None:
    path.write_text(
        json.dumps([c.as_json() for c in cases], ensure_ascii=False, indent=1), encoding="utf-8"
    )


def load_cases(path: Path) -> list[Case]:
    cases = [Case(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
    for case in cases:
        if explanation_service.input_hash(case.payload) != case.input_hash:
            raise ValueError(f"{case.key}: the payload no longer matches its input_hash")
    return cases
