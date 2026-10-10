"""Walking-skeleton step 6: recover a shift through the real HTTP routes.

No handler, service or dependency is replaced. Requests use SessionLocal and
commit to the dedicated test database selected by tests/conftest.py. Since
/demo/reset rebuilds the schema, this test cannot use the rollback-only db
fixture; cleanup restores the empty migrated schema for the rest of the suite.
"""

from collections.abc import Iterator
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from app.db.session import engine
from app.domain.enums import (
    GOLDEN_PATH_AUDIT_ACTIONS,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    RosterStatus,
)
from app.main import app
from app.schemas.case import CaseDetail
from app.schemas.roster import ShiftRoster


@pytest.fixture
def client(restore_empty_database: None) -> Iterator[TestClient]:
    # Fail before calling the destructive reset if the test DB guard or request
    # wiring ever changes. The real app must run without dependency overrides.
    assert (engine.url.database or "").endswith("_test")
    assert not app.dependency_overrides
    with TestClient(app) as request_client:
        yield request_client


def _case(client: TestClient, case_id: int) -> CaseDetail:
    response = client.get(f"/cases/{case_id}")
    assert response.status_code == 200, response.text
    return CaseDetail.model_validate(response.json())


def _roster(client: TestClient) -> ShiftRoster:
    response = client.get("/roster", params={"shift_id": 1}, headers={"X-Demo-User": "900"})
    assert response.status_code == 200, response.text
    return ShiftRoster.model_validate(response.json())


def test_golden_path_recovers_workforce(client: TestClient) -> None:
    reset = client.post("/demo/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["status"] == "ok"

    initial_roster = _roster(client)
    assert {row.staff_id for row in initial_roster.assignments} == {101, 102, 103, 104, 105}
    assert all(row.status is RosterStatus.ASSIGNED for row in initial_roster.assignments)

    # 105 reports leave. All real automatic handlers run up to the first wait.
    event = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert event.status_code == 201, event.text
    opened = event.json()
    assert opened["event_status"] == "PROCESSED"
    assert opened["case_status"] == "WAITING_RESPONSE"
    case_id = opened["case_id"]
    assert isinstance(case_id, int)
    case = _case(client, case_id)
    assert case.status is CaseStatus.WAITING_RESPONSE
    assert case.event_id == opened["event_id"]
    assert case.shift_id == 1
    assert case.gap is not None
    assert case.gap.headcount_gap == 1
    assert case.candidates[0].rank == 1
    assert case.candidates[0].staff_id == 201
    absent = [row for row in _roster(client).assignments if row.staff_id == 105]
    assert len(absent) == 1
    assert absent[0].status is RosterStatus.CANCELLED

    offers = client.get(
        "/demo/line-sim/offers", params={"staff_id": 201}, headers={"X-Demo-User": "201"}
    )
    assert offers.status_code == 200, offers.text
    assert len(offers.json()) == 1
    offer = offers.json()[0]
    assert offer["case_id"] == case_id
    assert offer["staff_id"] == 201
    assert offer["proposed_shift_id"] == 1
    assert offer["status"] == "SENT"

    # Acceptance alone must not create the replacement roster assignment.
    accepted = client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": "201"},
        json={"outreach_id": offer["id"], "response": "ACCEPT"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["outreach_id"] == offer["id"]
    assert accepted.json()["outreach_status"] == "ACCEPTED"
    assert accepted.json()["case_id"] == case_id
    assert accepted.json()["case_status"] == "WAITING_APPROVAL"
    assert _case(client, case_id).status is CaseStatus.WAITING_APPROVAL
    assert all(row.staff_id != 201 for row in _roster(client).assignments)

    pending = client.get("/approvals", params={"pending": "true"}, headers={"X-Demo-User": "900"})
    assert pending.status_code == 200, pending.text
    assert len(pending.json()) == 1
    approval = pending.json()[0]
    assert approval["case_id"] == case_id
    assert approval["staff_id"] == 201
    assert approval["candidate_item_id"] == offer["candidate_item_id"]
    assert approval["proposed_shift_id"] == 1
    assert approval["is_pending"] is True

    approved = client.post(
        f"/approvals/{approval['id']}/decision",
        headers={"X-Demo-User": "900"},
        json={"approved": True},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_id"] == approval["id"]
    assert approved.json()["is_approved"] is True
    assert approved.json()["case_id"] == case_id
    assert approved.json()["case_status"] == "RESOLVED"
    assert _case(client, case_id).status is CaseStatus.RESOLVED

    final_roster = _roster(client)
    replacement = [row for row in final_roster.assignments if row.staff_id == 201]
    assert len(replacement) == 1
    assert replacement[0].status is RosterStatus.ASSIGNED
    assert replacement[0].assignment_type is AssignmentType.REPLACEMENT
    assert replacement[0].candidate_source is CandidateSource.SAME_WARD
    assert {
        row.staff_id for row in final_roster.assignments if row.status is RosterStatus.ASSIGNED
    } == {101, 102, 103, 104, 201}
    assert next(row for row in final_roster.assignments if row.staff_id == 105).status is (
        RosterStatus.CANCELLED
    )
    remaining = client.get("/approvals", params={"pending": "true"}, headers={"X-Demo-User": "900"})
    assert remaining.status_code == 200, remaining.text
    assert remaining.json() == []

    # Compare the actual persisted timeline, not synthetic audit rows. Frozen
    # timestamps are equal; IDs establish order but need not be contiguous.
    audit = client.get(f"/cases/{case_id}/audit")
    assert audit.status_code == 200, audit.text
    timeline = audit.json()
    ids = [row["id"] for row in timeline]
    assert ids == sorted(set(ids))
    actions = [
        row["action"] for row in timeline if row["action"] != AuditAction.CASE_STATUS_CHANGED
    ]
    assert actions == [action.value for action in GOLDEN_PATH_AUDIT_ACTIONS]
    transitions = [
        (row["payload"]["from"], row["payload"]["to"])
        for row in timeline
        if row["action"] == AuditAction.CASE_STATUS_CHANGED
    ]
    path = [
        "OPEN",
        "ASSESSING",
        "OPTIMIZING",
        "OUTREACH",
        "WAITING_RESPONSE",
        "SAFETY_VALIDATION",
        "WAITING_APPROVAL",
        "EXECUTING",
        "RESOLVED",
    ]
    assert transitions == list(pairwise(path))
