"""An event that leaves no gap is IGNORED and opens no case (workflow.md D5, section 10.4).

203 reports leave for the day shift. 202 is still assigned and the shift needs
one RN for its 2 patients, so the shift stays covered.
"""

from collections.abc import Iterator
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    Actor,
    AuditLog,
    RosterAssignment,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import ActorName, AuditAction, EntityType, EventStatus, RosterStatus
from app.main import app

DAY_SHIFT = 2
LEAVE = {"event_type": "STAFF_UNAVAILABLE", "shift_id": DAY_SHIFT}
AS_203 = {"X-Demo-User": "203"}


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_event_without_a_gap_is_ignored_and_opens_no_case(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/events", headers=AS_203, json=LEAVE)

    assert response.status_code == 201
    body = response.json()
    assert body["event_status"] == "IGNORED"
    assert body["case_id"] is None
    assert body["case_status"] is None
    seeded.expire_all()
    event = seeded.get(StaffingEvent, body["event_id"])
    assert event is not None
    assert event.status is EventStatus.IGNORED
    assert seeded.scalar(select(func.count()).select_from(StaffingCase)) == 0


def test_ignored_event_still_records_the_leave(client: TestClient, seeded: Session) -> None:
    """The person is absent either way. Only the search for a replacement is skipped."""
    client.post("/events", headers=AS_203, json=LEAVE)

    seeded.expire_all()
    roster = dict(
        seeded.execute(
            select(RosterAssignment.staff_id, RosterAssignment.status).where(
                RosterAssignment.shift_id == DAY_SHIFT
            )
        ).all()
    )
    assert roster == {202: RosterStatus.ASSIGNED, 203: RosterStatus.CANCELLED}
    assert seeded.scalars(select(StaffUnavailability.staff_id)).all() == [203]


def test_ignored_event_writes_three_audit_rows_without_a_case(
    client: TestClient, seeded: Session
) -> None:
    body = client.post("/events", headers=AS_203, json=LEAVE).json()

    rows = list(seeded.scalars(select(AuditLog).order_by(AuditLog.id)))
    assert [row.action for row in rows] == [
        AuditAction.EVENT_RECEIVED,
        AuditAction.UNAVAILABILITY_CREATED,
        AuditAction.EVENT_IGNORED,
    ]
    assert all(row.case_id is None for row in rows)
    ignored = rows[-1]
    orchestrator_actor = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.WORKFLOW_ORCHESTRATOR.value)
    )
    assert ignored.actor_id == orchestrator_actor
    assert ignored.entity_type is EntityType.STAFFING_EVENTS
    assert ignored.entity_id == body["event_id"]
    assert ignored.payload == {"event_id": body["event_id"], "shift_id": DAY_SHIFT}


def test_ignored_event_is_committed_once(client: TestClient, seeded: Session) -> None:
    """No orchestrator round runs for an ignored event, so event intake commits itself."""
    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        response = client.post("/events", headers=AS_203, json=LEAVE)

    assert response.status_code == 201
    assert commit.call_count == 1
