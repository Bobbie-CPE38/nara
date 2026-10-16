"""Scenario no_feasible_solution through the real routes (round 1 contract, case จ)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import CandidateOutreach
from app.main import app
from app.seed.scenarios import no_feasible_solution


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_a_shift_nobody_can_take_stops_at_manual_handoff(
    client: TestClient, seeded: Session
) -> None:
    no_feasible_solution.seed(seeded)

    opened = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )

    assert opened.status_code == 201, opened.text
    assert opened.json()["event_status"] == "PROCESSED"
    assert opened.json()["case_status"] == "MANUAL_HANDOFF"
    case_id = opened.json()["case_id"]

    detail = client.get(f"/cases/{case_id}").json()
    assert detail["status"] == "MANUAL_HANDOFF"
    assert detail["candidates"] == []

    audit = client.get(f"/cases/{case_id}/audit").json()
    rows = [row for row in audit if row["action"] != "CASE_STATUS_CHANGED"]
    assert [row["action"] for row in rows] == [
        "EVENT_RECEIVED",
        "UNAVAILABILITY_CREATED",
        "CASE_OPENED",
        "GAP_ASSESSED",
        "SOLVER_EXECUTED",
        "MANUAL_HANDOFF",
    ]
    assert rows[-1]["payload"]["reason"] == "NO_FEASIBLE_PLAN"
    assert rows[-1]["payload"]["skipped"] == [
        {"staff_id": 101, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 102, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 103, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 104, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 105, "reason": "UNAVAILABLE"},
        {"staff_id": 201, "reason": "UNAVAILABLE"},
        {"staff_id": 202, "reason": "INSUFFICIENT_REST"},
        {"staff_id": 203, "reason": "STAFF_NOT_ACTIVE"},
        {"staff_id": 301, "reason": "SOURCE_WARD_MINIMUM_VIOLATION"},
        {"staff_id": 302, "reason": "SOURCE_WARD_MINIMUM_VIOLATION"},
        {"staff_id": 401, "reason": "SOURCE_WARD_MINIMUM_VIOLATION"},
        {"staff_id": 900, "reason": "ROLE_MISMATCH"},
        {"staff_id": 902, "reason": "ROLE_MISMATCH"},
        {"staff_id": 950, "reason": "ROLE_MISMATCH"},
    ]
    changes = [
        (row["payload"]["from"], row["payload"]["to"])
        for row in audit
        if row["action"] == "CASE_STATUS_CHANGED"
    ]
    assert changes[-1] == ("OPTIMIZING", "MANUAL_HANDOFF")
    assert seeded.scalar(select(CandidateOutreach.id)) is None
