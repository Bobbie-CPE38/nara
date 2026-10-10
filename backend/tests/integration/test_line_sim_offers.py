"""Authenticated offer history reads on the main app, without workflow writes."""

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.constants import MAX_BIGINT
from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    CandidateSource,
    CaseStatus,
    Channel,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.main import app
from app.services import outreach_service
from tests.integration.conftest import DEMO_NOW

URL = "/demo/line-sim/offers"
HEADERS = {"X-Demo-User": "201"}


def _offer(
    db: Session,
    *,
    staff_id: int = 201,
    status: OutreachStatus = OutreachStatus.SENT,
    case_status: CaseStatus = CaseStatus.WAITING_RESPONSE,
) -> CandidateOutreach:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=1,
        staff_id=105,
        occurred_at=DEMO_NOW,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=1,
        status=case_status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="stub",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=staff_id,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=1,
    )
    db.add(item)
    db.flush()
    offer = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        status=status,
        sent_at=DEMO_NOW,
        response_at=None,
    )
    db.add(offer)
    db.flush()
    return offer


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    def request_db() -> Iterator[Session]:
        # Fixture rows are committed to their savepoint before each request.
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_offer_contract_and_demo_staff_selection(
    client: TestClient, production_seeded: Session
) -> None:
    offer = _offer(production_seeded, staff_id=202)
    production_seeded.commit()
    # A demo user may read the selected staff member, but acceptance uses the header.
    response = client.get(URL, params={"staff_id": 202}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": offer.id,
            "case_id": offer.case_id,
            "candidate_item_id": offer.candidate_item_id,
            "staff_id": 202,
            "proposed_shift_id": 1,
            "status": "SENT",
            "case_status": "WAITING_RESPONSE",
            "channel": "LINE",
            "sent_at": DEMO_NOW.isoformat(),
            "response_at": None,
        }
    ]


@pytest.mark.parametrize("staff_id", [201, 999, MAX_BIGINT])
def test_no_offers_returns_empty_list(client: TestClient, staff_id: int) -> None:
    response = client.get(URL, params={"staff_id": staff_id}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_filters_recipient_and_orders_by_id_not_time(
    client: TestClient, production_seeded: Session
) -> None:
    first = _offer(production_seeded)
    _offer(production_seeded, staff_id=202)
    last = _offer(production_seeded)
    first.sent_at = DEMO_NOW + timedelta(minutes=10)
    production_seeded.commit()
    response = client.get(URL, params={"staff_id": 201}, headers=HEADERS)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [first.id, last.id]


@pytest.mark.parametrize("status", list(OutreachStatus))
def test_includes_history_and_nullable_times(
    client: TestClient,
    production_seeded: Session,
    status: OutreachStatus,
) -> None:
    offer = _offer(production_seeded, status=status, case_status=CaseStatus.RESOLVED)
    offer.sent_at = None
    offer.response_at = DEMO_NOW if status is OutreachStatus.ACCEPTED else None
    production_seeded.commit()
    response = client.get(URL, params={"staff_id": 201}, headers=HEADERS)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == status.value
    assert row["case_status"] == "RESOLVED"
    assert row["sent_at"] is None
    assert row["response_at"] == (
        DEMO_NOW.isoformat() if status is OutreachStatus.ACCEPTED else None
    )


@pytest.mark.parametrize("staff_id", [None, "bad", "1.5", "0", "-1", str(MAX_BIGINT + 1)])
def test_staff_query_validation(client: TestClient, staff_id: str | None) -> None:
    response = client.get(
        URL, params={} if staff_id is None else {"staff_id": staff_id}, headers=HEADERS
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "staff_id"]


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "bad"}, {"X-Demo-User": "999"}])
def test_requires_demo_auth(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get(URL, params={"staff_id": 201}, headers=headers).status_code == 401


def test_service_read_does_not_flush_commit_lock_or_audit(production_seeded: Session) -> None:
    db = production_seeded
    offer = _offer(db)
    db.commit()
    offer.status = OutreachStatus.ACCEPTED  # Pending change must not be flushed by a read.
    with (
        patch.object(db, "flush", side_effect=AssertionError("read flushed")),
        patch.object(db, "commit", side_effect=AssertionError("read committed")),
        patch.object(db, "execute", wraps=db.execute) as execute,
    ):
        rows = outreach_service.list_offers(db, staff_id=201)
    assert rows[0].status is OutreachStatus.SENT
    statement = str(execute.call_args.args[0])
    assert "FOR UPDATE" not in statement and "FOR NO KEY UPDATE" not in statement
    db.rollback()
    assert db.scalar(select(AuditLog.id)) is None


def test_real_workflow_offer_is_visible_before_and_after_acceptance(
    client: TestClient, production_seeded: Session
) -> None:
    production_seeded.commit()
    event = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert event.status_code == 201
    assert event.json()["case_status"] == "WAITING_RESPONSE"
    before = client.get(URL, params={"staff_id": 201}, headers=HEADERS)
    assert before.status_code == 200
    assert len(before.json()) == 1
    offer = before.json()[0]
    assert offer["case_id"] == event.json()["case_id"]
    assert offer["status"] == "SENT"
    assert offer["case_status"] == "WAITING_RESPONSE"
    assert client.get(URL, params={"staff_id": 202}, headers=HEADERS).json() == []

    answer = client.post("/demo/line-sim/respond", headers=HEADERS, json={"response": "ACCEPT"})
    assert answer.status_code == 200
    assert answer.json()["case_status"] == "WAITING_APPROVAL"
    after = client.get(URL, params={"staff_id": 201}, headers=HEADERS)
    assert after.status_code == 200
    assert len(after.json()) == 1
    assert after.json()[0]["id"] == offer["id"]
    assert after.json()[0]["status"] == "ACCEPTED"
    assert after.json()[0]["case_status"] == "WAITING_APPROVAL"
    assert after.json()[0]["response_at"] == DEMO_NOW.isoformat()
