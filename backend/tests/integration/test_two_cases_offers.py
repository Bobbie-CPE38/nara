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

    sent = {
        case_id: (outreach_id, staff_id)
        for case_id, outreach_id, staff_id in seeded.execute(
            select(CandidateOutreach.case_id, CandidateOutreach.id, CandidateItem.staff_id)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(CandidateOutreach.status == OutreachStatus.SENT)
        )
    }
    assert set(sent) == {night["case_id"], day["case_id"]}
    assert sent[night["case_id"]][1] == 201
    # 201 is the cheapest candidate of the day shift too, but already holds an offer
    assert sent[day["case_id"]][1] != 201

    for outreach_id, staff_id in sent.values():
        answer = client.post(
            "/demo/line-sim/respond",
            headers={"X-Demo-User": str(staff_id)},
            json={"outreach_id": outreach_id, "response": "ACCEPT"},
        )
        assert answer.status_code == 200, answer.text
