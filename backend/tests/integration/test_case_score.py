"""`score` of GET /cases/{id} (docs/workflow.md, section 6.15), on real plans of the Solver.

The score is rebuilt from the plan's snapshot alone, so it must survive a policy
edit, and a plan without stored weights must answer null.
"""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Attendance, CandidatePlan, SoftConstraintPolicy, StaffingCase
from app.domain.constraints.score_breakdown import ScoreMismatchError, display_number
from app.domain.enums import CaseStatus
from app.main import app
from app.seed.scenarios import soft_constraint
from app.services import case_service
from app.workflow.handlers import optimize
from tests.integration.case_rows import leave, make_case, record_gap
from tests.integration.conftest import DEMO_NOW

TERM_NAMES = [
    "candidate_count",
    "consecutive_shift",
    "workload_imbalance",
    "projected_overtime",
    "candidate_source",
]


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _planned_case(db: Session) -> StaffingCase:
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    return case


def _plan(db: Session, case: StaffingCase) -> CandidatePlan:
    return db.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()


def _candidates(client: TestClient, case: StaffingCase) -> list[dict[str, Any]]:
    response = client.get(f"/cases/{case.id}")
    assert response.status_code == 200
    candidates: list[dict[str, Any]] = response.json()["candidates"]
    return candidates


def _snapshot_by_staff(plan: CandidatePlan) -> dict[int, dict[str, Any]]:
    return {row["staff_id"]: row for row in plan.input_snapshot["candidates"]}


def test_the_golden_case_explains_the_rank(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)

    candidates = _candidates(client, case)

    assert [c["staff_id"] for c in candidates] == [201, 202, 203]
    assert [c["score"]["first_wave"] for c in candidates] == [True, True, False]
    first = candidates[0]["score"]
    assert first["total"] == 1005
    assert [term["name"] for term in first["terms"]] == TERM_NAMES
    assert [(t["value"], t["weight"], t["points"]) for t in first["terms"]] == [
        (1, 1000, 1000),
        (1, 5, 5),
        (0, 1, 0),
        (0, 2, 0),
        (0, 200, 0),
    ]
    assert [c["score"]["total"] for c in candidates] == [1005, 1018, 1018]


def test_a_policy_edit_after_planning_does_not_change_the_score(
    client: TestClient, seeded: Session
) -> None:
    """Row E-1: the weights come from the snapshot, never from the current policy."""
    case = _planned_case(seeded)
    before = _candidates(client, case)

    soft_constraint.ignore_workload(seeded)
    policy = seeded.get(SoftConstraintPolicy, 1)
    assert policy is not None
    policy.consecutive_shift_weight = Decimal(9)
    seeded.flush()

    after = _candidates(client, case)
    assert [c["score"] for c in after] == [c["score"] for c in before]
    by_staff = _snapshot_by_staff(_plan(seeded, case))
    for candidate in after:
        exact = Fraction(by_staff[candidate["staff_id"]]["penalty_exact"])
        assert candidate["score"]["total"] == display_number(exact)


def test_fractional_weights_and_overtime_sum_exactly(client: TestClient, seeded: Session) -> None:
    """Row E-2: 20 minutes of overtime and fractional weights give a total that is no int."""
    policy = seeded.get(SoftConstraintPolicy, 1)
    assert policy is not None
    policy.projected_overtime_weight = Decimal("0.3")
    policy.workload_imbalance_weight = Decimal("0.25")
    seeded.add(
        Attendance(
            staff_id=202,
            check_in_at=DEMO_NOW - timedelta(hours=12),
            check_out_at=DEMO_NOW - timedelta(hours=3),
            work_minutes=540,
            overtime_minutes=20,
            synced_at=DEMO_NOW,
        )
    )
    seeded.flush()
    case = _planned_case(seeded)

    candidates = _candidates(client, case)

    by_staff = _snapshot_by_staff(_plan(seeded, case))
    candidate = next(c for c in candidates if c["staff_id"] == 202)
    exact = Fraction(by_staff[202]["penalty_exact"])
    assert exact.denominator != 1
    assert candidate["score"]["total"] == display_number(exact)
    terms = {term["name"]: term for term in candidate["score"]["terms"]}
    assert isinstance(terms["projected_overtime"]["value"], float)
    assert terms["projected_overtime"]["weight"] == 0.3
    assert isinstance(terms["projected_overtime"]["points"], float)


def test_a_plan_without_stored_weights_has_no_score(client: TestClient, seeded: Session) -> None:
    """Row E-3: never fall back to the current policy, even though it exists."""
    case = _planned_case(seeded)
    plan = _plan(seeded, case)
    plan.input_snapshot = {k: v for k, v in plan.input_snapshot.items() if k != "weights"}
    seeded.flush()

    candidates = _candidates(client, case)

    assert [c["staff_id"] for c in candidates] == [201, 202, 203]
    assert [c["score"] for c in candidates] == [None, None, None]


def test_a_tampered_penalty_is_a_loud_error(seeded: Session) -> None:
    """Service level: TestClient would re-raise the error instead of answering 500."""
    case = _planned_case(seeded)
    plan = _plan(seeded, case)
    snapshot = dict(plan.input_snapshot)
    rows = [dict(row) for row in snapshot["candidates"]]
    rows[0]["penalty_exact"] = "1006/1"
    snapshot["candidates"] = rows
    plan.input_snapshot = snapshot
    seeded.flush()

    with pytest.raises(ScoreMismatchError):
        case_service.get_case_detail(seeded, case.id)
