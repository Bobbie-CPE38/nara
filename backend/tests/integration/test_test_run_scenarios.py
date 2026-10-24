"""The test-run scenarios of round 6 PR EV7 (docs/workflow.md 6.37.10): surge, no_show,
handoff and supervisor, each played with the simulated people. These tests commit."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import clock
from app.db.models import AuditLog, StaffingCase, StaffingEvent
from app.db.session import SessionLocal
from app.main import app
from app.services import simulated_replies_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

HEAD_NURSE = {"X-Demo-User": "900"}
SUPERVISOR = {"X-Demo-User": "950"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    try:
        yield TestClient(app)
    finally:
        clock.reset()


def _start(client: TestClient, scenario: str) -> dict[str, Any]:
    answer = client.post(
        "/demo/test-runs",
        json={"tester_code": "T01", "scenario": scenario, "auto_nurses": True},
    )
    assert answer.status_code == 201, answer.text
    return answer.json()


def _advance(client: TestClient, minutes: int) -> None:
    for _ in range(minutes):
        assert client.post("/demo/clock/advance", json={"seconds": 60}).status_code == 200


def _status(case_id: int) -> str:
    with SessionLocal() as db:
        case = db.get(StaffingCase, case_id)
        assert case is not None
        return case.status.value


def _decide_all(client: TestClient, headers: dict[str, str]) -> int:
    decided = 0
    for request in client.get("/approvals?pending=true", headers=headers).json():
        answer = client.post(
            f"/approvals/{request['id']}/decision", headers=headers, json={"approved": True}
        )
        assert answer.status_code == 200, answer.text
        decided += 1
    return decided


def test_surge_needs_two_more_and_both_come(client: TestClient) -> None:
    run = _start(client, "surge")
    gap = client.get(f"/cases/{run['case_id']}").json()["gap"]
    assert gap["headcount_gap"] == 2

    _advance(client, 2)
    assert _decide_all(client, HEAD_NURSE) == 2

    assert _status(run["case_id"]) == "RESOLVED"
    kpi = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]
    assert kpi["invalid"] is False


def test_no_show_opens_the_case_by_itself(client: TestClient) -> None:
    run = _start(client, "no_show")
    assert run["case_id"] is None
    assert client.get("/clock").json()["now"].startswith(run["started_at"][:11])

    _advance(client, 2)
    with SessionLocal() as db:
        event = db.scalars(select(StaffingEvent).where(StaffingEvent.staff_id == 104)).one()
        case_id = event.case_id
    assert event.payload.get("reason") == "NO_SHOW" and case_id is not None

    _advance(client, 3)
    assert _decide_all(client, HEAD_NURSE) == 1
    assert _status(case_id) == "RESOLVED"
    # The run finds its case without a starting event
    kpi = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]
    assert kpi["invalid"] is False and kpi["time_to_fill_system_s"] is not None


def test_a_no_show_run_finished_before_its_case_opens_is_invalid(client: TestClient) -> None:
    run = _start(client, "no_show")

    result = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]

    assert result == {"invalid": True, "reason": "NO_CASE"}


def test_a_no_show_run_keeps_its_own_case_when_another_is_reported(client: TestClient) -> None:
    run = _start(client, "no_show")
    # Reported by hand from the Demo control on the same shift, before the NO_SHOW is found
    surge = client.post(
        "/demo/events",
        json={
            "reporter_staff_id": 900,
            "event_type": "PATIENT_SURGE",
            "shift_id": 1,
            "patient_count": 14,
        },
    )
    assert surge.status_code == 201, surge.text
    surge_case = surge.json()["case_id"]

    _advance(client, 10)
    with SessionLocal() as db:
        no_show = db.scalars(select(StaffingEvent).where(StaffingEvent.staff_id == 104)).one()
        started = db.get(AuditLog, run["test_run_id"])
        assert started is not None and no_show.case_id not in (None, surge_case)
        # The first case of the shift is the surge's: the run must not take it
        assert simulated_replies_service.run_case_id(db, started.payload) == no_show.case_id


def test_handoff_ends_with_the_tester_staffing_the_shift(client: TestClient) -> None:
    run = _start(client, "handoff")

    _advance(client, 2)
    assert _status(run["case_id"]) == "MANUAL_HANDOFF"
    free = next(
        row
        for row in client.get(
            f"/cases/{run['case_id']}/handoff/candidates", headers=HEAD_NURSE
        ).json()
        if not row["blocking_rules"]
    )
    assigned = client.post(
        f"/cases/{run['case_id']}/handoff/assignments",
        headers=HEAD_NURSE,
        json={"staff_id": free["staff_id"], "confirm_conflicts": True},
    )

    assert assigned.status_code == 200, assigned.text
    assert _status(run["case_id"]) == "RESOLVED"
    kpi = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]
    assert kpi["invalid"] is False and kpi["time_to_fill_system_s"] is not None


def test_supervisor_decides_once_the_head_nurse_had_her_time(client: TestClient) -> None:
    run = _start(client, "supervisor")

    _advance(client, 3)
    assert _status(run["case_id"]) == "WAITING_APPROVAL"
    assert len(client.get("/approvals?pending=true", headers=HEAD_NURSE).json()) == 1

    _advance(client, 10)
    assert _decide_all(client, SUPERVISOR) == 1
    assert _status(run["case_id"]) == "RESOLVED"


def test_a_cross_ward_case_names_who_decided_for_each_ward(client: TestClient) -> None:
    """Round 6 PR EV7 (6.37.2): the case page names the approver of both sides."""
    run = _start(client, "cross_ward")

    for _ in range(6):
        _advance(client, 1)
        for request in client.get("/approvals?pending=true", headers=HEAD_NURSE).json():
            client.post(
                f"/approvals/{request['id']}/decision",
                headers=HEAD_NURSE,
                json={"approved": True, "side": "DESTINATION"},
            )

    overview = client.get(f"/cases/{run['case_id']}").json()["overview"]
    sides = {
        (decision["side"], decision["ward_name"], decision["by"]["staff_id"])
        for decision in overview["decisions"]
        if decision["kind"] == "APPROVED"
    }
    assert sides == {("DESTINATION", "ICU", 900), ("SOURCE", "Medicine", 902)}
    assert [row["how"] for row in overview["replacements"]] == ["TRANSFERRED"]
    assert overview["replacements"][0]["staff"]["ward_name"] == "Medicine"
