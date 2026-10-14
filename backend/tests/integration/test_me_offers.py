"""Nurse page routes: the header is the only identity (docs/workflow.md, section 6.17)."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.constants import MAX_BIGINT
from app.db.models import AuditLog, CandidateOutreach
from app.domain.enums import AuditAction, OutreachStatus
from app.main import app
from app.services import actor_service, outreach_service
from tests.integration.case_rows import offer as make_offer
from tests.integration.case_rows import short_case

URL = "/me/offers"
HEADERS = {"X-Demo-User": "201"}


@pytest.fixture
def offers(production_seeded: Session) -> dict[int, CandidateOutreach]:
    """One open offer each for 201 and 202 in the same case."""
    case, items = short_case(production_seeded)
    rows = {staff: make_offer(production_seeded, case, items[staff]) for staff in (201, 202)}
    production_seeded.commit()
    return rows


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    def request_db() -> Iterator[Session]:
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _answer(client: TestClient, outreach_id: int, body: dict, staff: str = "201"):
    return client.post(f"{URL}/{outreach_id}/response", headers={"X-Demo-User": staff}, json=body)


def test_lists_only_the_header_users_offers(
    client: TestClient, offers: dict[int, CandidateOutreach]
) -> None:
    for staff in (201, 202):
        response = client.get(URL, headers={"X-Demo-User": str(staff)})
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [offers[staff].id]
        assert response.json()[0]["staff_id"] == staff


@pytest.mark.parametrize("staff_id", ["202", "201", "abc", str(MAX_BIGINT + 1)])
def test_staff_id_in_the_query_is_ignored(
    client: TestClient, offers: dict[int, CandidateOutreach], staff_id: str
) -> None:
    # Silent-break check of round 3: the page must not read someone else's offers.
    response = client.get(URL, params={"staff_id": staff_id}, headers=HEADERS)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [offers[201].id]


def test_same_rows_as_the_simulator(
    client: TestClient, offers: dict[int, CandidateOutreach]
) -> None:
    mine = client.get(URL, headers=HEADERS)
    simulator = client.get("/demo/line-sim/offers", params={"staff_id": 201}, headers=HEADERS)
    assert mine.json() == simulator.json()


def test_no_offers_is_an_empty_list(
    client: TestClient, offers: dict[int, CandidateOutreach]
) -> None:
    response = client.get(URL, headers={"X-Demo-User": "203"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "bad"}, {"X-Demo-User": "999"}])
def test_requires_the_demo_header(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get(URL, headers=headers).status_code == 401
    assert (
        client.post(f"{URL}/1/response", headers=headers, json={"response": "REJECT"}).status_code
        == 401
    )


@pytest.mark.parametrize("response", ["ACCEPT", "REJECT"])
def test_answers_through_record_response(
    client: TestClient,
    offers: dict[int, CandidateOutreach],
    production_seeded: Session,
    response: str,
) -> None:
    with patch.object(
        outreach_service, "record_response", wraps=outreach_service.record_response
    ) as spy:
        result = _answer(client, offers[201].id, {"response": response})
    assert result.status_code == 200, result.text
    assert spy.call_args.kwargs["staff_id"] == 201
    body = result.json()
    assert body["outreach_id"] == offers[201].id
    assert body["outreach_status"] == ("ACCEPTED" if response == "ACCEPT" else "REJECTED")
    assert body["case_id"] == offers[201].case_id
    action = AuditAction.OFFER_ACCEPTED if response == "ACCEPT" else AuditAction.OFFER_REJECTED
    actor = production_seeded.scalar(select(AuditLog.actor_id).where(AuditLog.action == action))
    assert actor == actor_service.user_id(production_seeded, 201)


@pytest.mark.parametrize("extra", [{"staff_id": 202}, {"staff_id": 201}, {"outreach_id": 1}])
def test_body_with_any_other_field_is_refused_without_writes(
    client: TestClient,
    offers: dict[int, CandidateOutreach],
    production_seeded: Session,
    extra: dict,
) -> None:
    result = _answer(client, offers[201].id, {"response": "ACCEPT", **extra})
    assert result.status_code == 422
    assert production_seeded.scalar(select(func.count()).select_from(AuditLog)) == 0
    production_seeded.refresh(offers[201])
    assert offers[201].status is OutreachStatus.SENT


def test_someone_elses_offer_is_409(
    client: TestClient, offers: dict[int, CandidateOutreach], production_seeded: Session
) -> None:
    assert _answer(client, offers[202].id, {"response": "ACCEPT"}).status_code == 409
    production_seeded.refresh(offers[202])
    assert offers[202].status is OutreachStatus.SENT


def test_second_answer_is_409(client: TestClient, offers: dict[int, CandidateOutreach]) -> None:
    assert _answer(client, offers[201].id, {"response": "REJECT"}).status_code == 200
    assert _answer(client, offers[201].id, {"response": "ACCEPT"}).status_code == 409


def test_unstable_lock_is_503_with_retry_after(
    client: TestClient, offers: dict[int, CandidateOutreach]
) -> None:
    with patch.object(
        outreach_service,
        "record_response",
        side_effect=outreach_service.OutreachLockRetryError("try again"),
    ):
        result = _answer(client, offers[201].id, {"response": "ACCEPT"})
    assert result.status_code == 503
    assert result.headers["Retry-After"] == "1"


@pytest.mark.parametrize("outreach_id", ["0", "-1", "abc", str(MAX_BIGINT + 1)])
def test_offer_id_validation(client: TestClient, outreach_id: str) -> None:
    result = client.post(
        f"{URL}/{outreach_id}/response", headers=HEADERS, json={"response": "ACCEPT"}
    )
    assert result.status_code == 422


@pytest.mark.parametrize("body", [{}, {"response": "MAYBE"}, {"response": None}])
def test_response_validation(
    client: TestClient, offers: dict[int, CandidateOutreach], body: dict
) -> None:
    assert _answer(client, offers[201].id, body).status_code == 422
