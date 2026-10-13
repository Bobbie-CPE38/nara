"""Two cases open at once: every offer the system sends can still be answered."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import CandidateItem, CandidateOutreach
from app.domain.enums import OutreachStatus
from app.main import app


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _report_leave(client: TestClient, staff_id: int, shift_id: int) -> dict[str, object]:
    response = client.post(
        "/events",
        headers={"X-Demo-User": str(staff_id)},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": shift_id},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_offers_of_two_open_cases_can_both_be_answered(client: TestClient, seeded: Session) -> None:
    night = _report_leave(client, 105, 1)
    # Shift 2 needs one RN and has two, so the first leave opens no case
    assert _report_leave(client, 202, 2)["case_id"] is None
    day = _report_leave(client, 203, 2)
    assert night["case_status"] == day["case_status"] == "WAITING_RESPONSE"

    sent = list(
        seeded.execute(
            select(CandidateOutreach.case_id, CandidateOutreach.id, CandidateItem.staff_id)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(CandidateOutreach.status == OutreachStatus.SENT)
        )
    )
    night_offer = next(row for row in sent if row[0] == night["case_id"] and row[2] == 201)
    day_offer = next(row for row in sent if row[0] == day["case_id"] and row[2] == 201)
    accepted = client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": "201"},
        json={"outreach_id": night_offer[1], "response": "ACCEPT"},
    )
    assert accepted.status_code == 200, accepted.text
    blocked = client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": "201"},
        json={"outreach_id": day_offer[1], "response": "ACCEPT"},
    )
    assert blocked.status_code == 409
    other = next(row for row in sent if row[0] == day["case_id"] and row[2] != 201)
    accepted = client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": str(other[2])},
        json={"outreach_id": other[1], "response": "ACCEPT"},
    )
    assert accepted.status_code == 200, accepted.text
