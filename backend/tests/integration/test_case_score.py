"""`score` of GET /cases/{id} (docs/workflow.md, section 6.15), on real plans of the Solver.

The score is rebuilt from the plan's snapshot alone, so it must survive a policy
edit, and a plan without stored weights must answer null. A broken entry of a plan
with weights loses only its own score and is logged.
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
from app.domain.constraints.score_breakdown import display_number
from app.domain.enums import CaseStatus
from app.main import app
from app.seed.scenarios import soft_constraint
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
    assert first["total"] == 10020
    assert [term["name"] for term in first["terms"]] == TERM_NAMES
    assert [(t["value"], t["weight"], t["points"]) for t in first["terms"]] == [
        (1, 10000, 10000),
        (1, 20, 20),
        (0, 20, 0),
        (0, 1, 0),
        (0, 1500, 0),
    ]
    assert [c["score"]["total"] for c in candidates] == [10020, 10200, 10200]


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


def _edit_candidate(db: Session, case: StaffingCase, staff_id: int, change: Any) -> None:
    plan = _plan(db, case)
    snapshot = dict(plan.input_snapshot)
    rows = [dict(row) for row in snapshot["candidates"]]
    change(next(row for row in rows if row["staff_id"] == staff_id))
    snapshot["candidates"] = rows
    plan.input_snapshot = snapshot
    db.flush()


def _tamper(row: dict[str, Any]) -> None:
    row["penalty_exact"] = "1006/1"


def _drop(key: str) -> Any:
    return lambda row: row.pop(key)


@pytest.mark.parametrize(
    "change",
    [
        _tamper,
        _drop("hours_this_week_exact"),
        _drop("overtime_hours_exact"),
        _drop("penalty_exact"),
    ],
    ids=["tampered", "no-hours", "no-overtime", "no-penalty"],
)
def test_a_broken_entry_loses_only_its_own_score_and_is_logged(
    client: TestClient, seeded: Session, caplog: pytest.LogCaptureFixture, change: Any
) -> None:
    """A plan with weights is never read as a legacy plan, and one bad entry
    must not take the whole case page down. Nothing is rounded to fit."""
    case = _planned_case(seeded)
    _edit_candidate(seeded, case, 201, change)

    with caplog.at_level("ERROR", logger="app.services.case_service"):
        candidates = _candidates(client, case)

    assert [c["staff_id"] for c in candidates] == [201, 202, 203]
    assert candidates[0]["score"] is None
    assert candidates[1]["score"] is not None and candidates[2]["score"] is not None
    assert any("staff 201" in record.getMessage() for record in caplog.records)


def test_a_candidate_missing_from_the_snapshot_loses_its_score(
    client: TestClient, seeded: Session, caplog: pytest.LogCaptureFixture
) -> None:
    case = _planned_case(seeded)
    plan = _plan(seeded, case)
    snapshot = dict(plan.input_snapshot)
    snapshot["candidates"] = [r for r in snapshot["candidates"] if r["staff_id"] != 202]
    plan.input_snapshot = snapshot
    seeded.flush()

    with caplog.at_level("ERROR", logger="app.services.case_service"):
        candidates = _candidates(client, case)

    assert [c["score"] is None for c in candidates] == [False, True, False]
    assert any("staff 202" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "change",
    [lambda row: row.pop("staff_id"), lambda row: row.update(staff_id="201")],
    ids=["no-staff-id", "staff-id-not-a-number"],
)
def test_an_entry_without_a_staff_id_loses_only_its_candidate(
    client: TestClient, seeded: Session, caplog: pytest.LogCaptureFixture, change: Any
) -> None:
    case = _planned_case(seeded)
    _edit_candidate(seeded, case, 201, change)

    with caplog.at_level("ERROR", logger="app.services.case_service"):
        candidates = _candidates(client, case)

    assert [c["staff_id"] for c in candidates] == [201, 202, 203]
    assert [c["score"] is None for c in candidates] == [True, False, False]
    messages = [record.getMessage() for record in caplog.records]
    assert any("no staff ID" in message for message in messages)
    assert any("staff 201" in message for message in messages)


def test_a_snapshot_without_a_candidate_list_gives_null_scores(
    client: TestClient, seeded: Session, caplog: pytest.LogCaptureFixture
) -> None:
    case = _planned_case(seeded)
    plan = _plan(seeded, case)
    plan.input_snapshot = {k: v for k, v in plan.input_snapshot.items() if k != "candidates"}
    seeded.flush()

    with caplog.at_level("ERROR", logger="app.services.case_service"):
        candidates = _candidates(client, case)

    assert [c["score"] for c in candidates] == [None, None, None]
    assert any("no list of candidates" in record.getMessage() for record in caplog.records)


def test_unreadable_weights_give_null_scores_and_an_error_log(
    client: TestClient, seeded: Session, caplog: pytest.LogCaptureFixture
) -> None:
    case = _planned_case(seeded)
    plan = _plan(seeded, case)
    snapshot = dict(plan.input_snapshot)
    snapshot["weights"] = {"candidate_count": "1000/1"}
    plan.input_snapshot = snapshot
    seeded.flush()

    with caplog.at_level("ERROR", logger="app.services.case_service"):
        candidates = _candidates(client, case)

    assert [c["score"] for c in candidates] == [None, None, None]
    assert any("weights" in record.getMessage() for record in caplog.records)
