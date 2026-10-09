"""Seam 3: authenticated responses, request rollback, and simultaneous accepts."""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.exception_handlers import register_exception_handlers
from app.api.routes import line_sim
from app.db.base import Base
from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    StaffingCase,
    StaffingEvent,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    AuditAction,
    CandidateResponse,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.domain.workflow.transitions import InvalidTransitionError
from app.seed import load
from app.services import actor_service, outreach_service
from app.services.actor_service import ActorNotFoundError
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult
from tests.integration.conftest import DEMO_NOW

URL = "/demo/line-sim/respond"
HEADERS = {"X-Demo-User": "201"}


@pytest.fixture(autouse=True)
def stub_safety_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Respond owns the handoff to safety; safety's writes have their own tests.

    Stub only safety so the seam 2 integration test still runs real outreach.
    Tests of D11 can replace this handler with a failing one.
    """

    def wait_for_approval(db: Session, case: StaffingCase) -> HandlerResult:
        return HandlerResult(next_status=CaseStatus.WAITING_APPROVAL, wait=True)

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.SAFETY_VALIDATION, wait_for_approval)


def _make_offer(db: Session, *, staff_id: int = 201) -> CandidateOutreach:
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
        status=CaseStatus.WAITING_RESPONSE,
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
        source=CandidateSource.FLOAT_POOL,
        proposed_shift_id=1,
    )
    db.add(item)
    db.flush()
    offer = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        status=OutreachStatus.SENT,
        channel=Channel.LINE,
        sent_at=DEMO_NOW,
    )
    db.add(offer)
    db.flush()
    return offer


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(line_sim.router)
    register_exception_handlers(app)
    return app


@pytest.fixture
def offer(production_seeded: Session) -> CandidateOutreach:
    offer = _make_offer(production_seeded)
    # Commit releases the test session's savepoint, not the outer test transaction.
    # Request sessions can then close/rollback without deleting the fixture.
    production_seeded.commit()
    return offer


@pytest.fixture
def client(production_seeded: Session, offer: CandidateOutreach) -> Iterator[TestClient]:
    app = _app()

    def request_db() -> Iterator[Session]:
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _assert_unchanged(db: Session, offer: CandidateOutreach) -> None:
    db.expire_all()
    assert offer.status is OutreachStatus.SENT
    assert offer.response_at is None
    case = db.get(StaffingCase, offer.case_id)
    assert case is not None
    assert case.status is CaseStatus.WAITING_RESPONSE
    assert db.scalar(select(AuditLog.id)) is None


def test_accept_response_and_audit_contract(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach
) -> None:
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 200
    assert response.json() == {
        "outreach_id": offer.id,
        "outreach_status": "ACCEPTED",
        "case_id": offer.case_id,
        "case_status": "WAITING_APPROVAL",
    }
    db = production_seeded
    db.expire_all()
    assert offer.status is OutreachStatus.ACCEPTED
    assert offer.response_at == DEMO_NOW
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
    assert [row.action for row in rows] == [
        AuditAction.OFFER_ACCEPTED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    assert rows[0].actor_id == actor_service.user_id(db, 201)
    assert rows[0].case_id == offer.case_id
    assert rows[0].entity_type is EntityType.CANDIDATE_OUTREACH
    assert rows[0].entity_id == offer.id
    assert rows[0].created_at == DEMO_NOW
    assert rows[0].payload == {"outreach_id": offer.id, "staff_id": 201}
    assert rows[1].payload == {"from": "WAITING_RESPONSE", "to": "SAFETY_VALIDATION"}
    assert rows[2].payload == {"from": "SAFETY_VALIDATION", "to": "WAITING_APPROVAL"}


def test_service_delegates_status_and_commit_to_resume(
    production_seeded: Session, offer: CandidateOutreach
) -> None:
    db = production_seeded
    with (
        patch.object(orchestrator, "resume") as resume,
        patch.object(db, "commit", wraps=db.commit) as commit,
    ):
        recorded, case = outreach_service.record_response(
            db,
            staff_id=201,
            actor_id=actor_service.user_id(db, 201),
            response=CandidateResponse.ACCEPT,
        )
    resume.assert_called_once_with(db, offer.case_id, CaseStatus.SAFETY_VALIDATION)
    commit.assert_not_called()
    assert recorded.status is OutreachStatus.ACCEPTED
    assert case.status is CaseStatus.WAITING_RESPONSE


def test_other_staff_offers_and_answered_offers_do_not_make_selection_ambiguous(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach
) -> None:
    _make_offer(production_seeded, staff_id=105)
    answered = _make_offer(production_seeded)
    answered.status = OutreachStatus.ACCEPTED
    production_seeded.commit()
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 200
    assert response.json()["outreach_id"] == offer.id


@pytest.mark.parametrize(
    "status", [status for status in CaseStatus if status != CaseStatus.WAITING_RESPONSE]
)
def test_sent_offer_on_another_case_does_not_block_the_waiting_offer(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, status: CaseStatus
) -> None:
    stale = _make_offer(production_seeded)
    stale_case = production_seeded.get(StaffingCase, stale.case_id)
    assert stale_case is not None
    stale_case.status = status
    production_seeded.commit()

    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})

    assert response.status_code == 200
    assert response.json()["outreach_id"] == offer.id
    production_seeded.expire_all()
    assert offer.status is OutreachStatus.ACCEPTED
    assert stale.status is OutreachStatus.SENT
    assert stale.response_at is None
    assert stale_case.status is status
    accepted = list(
        production_seeded.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.OFFER_ACCEPTED)
        )
    )
    assert len(accepted) == 1
    assert accepted[0].entity_id == offer.id


@pytest.mark.parametrize("status", [CaseStatus.FAILED, CaseStatus.RESOLVED])
def test_only_offer_on_a_finished_case_is_conflict_without_writes(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, status: CaseStatus
) -> None:
    case = production_seeded.get(StaffingCase, offer.case_id)
    assert case is not None
    case.status = status
    production_seeded.commit()

    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})

    assert response.status_code == 409
    assert response.json() == {"detail": "No open offer for this staff member"}
    production_seeded.expire_all()
    assert offer.status is OutreachStatus.SENT
    assert offer.response_at is None
    assert case.status is status
    assert production_seeded.scalar(select(AuditLog.id)) is None


@pytest.mark.parametrize("answer", ["ACCEPT", "REJECT"])
def test_other_staff_cannot_answer_offer(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, answer: str
) -> None:
    response = client.post(URL, headers={"X-Demo-User": "105"}, json={"response": answer})
    assert response.status_code == 409
    assert response.json() == {"detail": "No open offer for this staff member"}
    _assert_unchanged(production_seeded, offer)


def test_reject_is_422_without_writes(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach
) -> None:
    response = client.post(URL, headers=HEADERS, json={"response": "REJECT"})
    assert response.status_code == 422
    _assert_unchanged(production_seeded, offer)


def test_reject_works_without_new_starlette_status_constant(
    client: TestClient,
    production_seeded: Session,
    offer: CandidateOutreach,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(line_sim.status, "HTTP_422_UNPROCESSABLE_CONTENT", raising=False)
    response = client.post(URL, headers=HEADERS, json={"response": "REJECT"})
    assert response.status_code == 422
    _assert_unchanged(production_seeded, offer)


def test_real_outreach_then_accept_writes_each_offer_audit_once(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach
) -> None:
    db = production_seeded
    case = db.get(StaffingCase, offer.case_id)
    assert case is not None
    # Replace the fixture's offer with one created by the real seam 2 handler.
    db.delete(offer)
    case.status = CaseStatus.OUTREACH
    orchestrator.advance(db, case.id)
    assert case.status is CaseStatus.WAITING_RESPONSE
    sent = db.scalars(select(CandidateOutreach)).one()
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 200
    assert response.json()["outreach_id"] == sent.id
    assert response.json()["case_status"] == "WAITING_APPROVAL"
    actions = list(db.scalars(select(AuditLog.action)))
    assert actions.count(AuditAction.OFFER_SENT) == 1
    assert actions.count(AuditAction.OFFER_ACCEPTED) == 1


@pytest.mark.parametrize("answer", ["ACCEPT", "REJECT"])
def test_multiple_open_offers_are_conflict_before_answer_check(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, answer: str
) -> None:
    other = _make_offer(production_seeded)
    production_seeded.commit()
    response = client.post(URL, headers=HEADERS, json={"response": answer})
    assert response.status_code == 409
    assert response.json() == {"detail": "Expected exactly one open offer for this staff member"}
    _assert_unchanged(production_seeded, offer)
    assert other.status is OutreachStatus.SENT


@pytest.mark.parametrize("answer", ["ACCEPT", "REJECT"])
def test_repeated_answer_is_409_without_second_audit(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, answer: str
) -> None:
    assert client.post(URL, headers=HEADERS, json={"response": "ACCEPT"}).status_code == 200
    response = client.post(URL, headers=HEADERS, json={"response": answer})
    assert response.status_code == 409
    actions = list(production_seeded.scalars(select(AuditLog.action)))
    assert actions.count(AuditAction.OFFER_ACCEPTED) == 1


@pytest.mark.parametrize(
    "status", [status for status in OutreachStatus if status != OutreachStatus.SENT]
)
def test_only_sent_offers_can_be_answered(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach, status: OutreachStatus
) -> None:
    offer.status = status
    production_seeded.commit()
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 409
    production_seeded.expire_all()
    assert offer.status is status
    assert offer.response_at is None
    assert production_seeded.scalar(select(AuditLog.id)) is None


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_authentication_is_required(
    client: TestClient,
    production_seeded: Session,
    offer: CandidateOutreach,
    headers: dict[str, str],
) -> None:
    assert client.post(URL, headers=headers, json={"response": "ACCEPT"}).status_code == 401
    _assert_unchanged(production_seeded, offer)


@pytest.mark.parametrize(
    "body", [{}, {"response": "MAYBE"}, {"response": "ACCEPT", "outreach_id": 1}]
)
def test_body_only_accepts_a_response(
    client: TestClient,
    production_seeded: Session,
    offer: CandidateOutreach,
    body: dict[str, object],
) -> None:
    assert client.post(URL, headers=HEADERS, json=body).status_code == 422
    _assert_unchanged(production_seeded, offer)


def test_invalid_case_transition_rolls_back_answer_and_audit(
    client: TestClient,
    production_seeded: Session,
    offer: CandidateOutreach,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A case can change after offer selection; resume must still reject it and
    # the request must roll back the already-flushed answer and audit.
    def conflict(db: Session, case_id: int, next_status: CaseStatus) -> None:
        assert db.scalar(select(AuditLog.action)) is AuditAction.OFFER_ACCEPTED
        raise InvalidTransitionError("case changed after offer selection")

    monkeypatch.setattr(orchestrator, "resume", conflict)
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 409
    _assert_unchanged(production_seeded, offer)


def test_handler_failure_returns_200_failed_and_preserves_answer(
    client: TestClient,
    production_seeded: Session,
    offer: CandidateOutreach,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(db: Session, case: StaffingCase) -> None:
        raise RuntimeError("safety failed")

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.SAFETY_VALIDATION, fail)
    response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 200
    assert response.json()["case_status"] == "FAILED"
    production_seeded.expire_all()
    assert offer.status is OutreachStatus.ACCEPTED
    assert offer.response_at == DEMO_NOW
    actions = list(production_seeded.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == [
        AuditAction.OFFER_ACCEPTED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.WORKFLOW_FAILED,
    ]


def test_unrecordable_workflow_error_returns_500_and_rolls_back(
    client: TestClient, production_seeded: Session, offer: CandidateOutreach
) -> None:
    with patch.object(
        actor_service, "component_id", side_effect=ActorNotFoundError("missing actor")
    ):
        response = client.post(URL, headers=HEADERS, json={"response": "ACCEPT"})
    assert response.status_code == 500
    _assert_unchanged(production_seeded, offer)


@pytest.fixture
def committed_offer(frozen_clock: datetime) -> Iterator[int]:
    """Only the test DB: committed rows let two request connections race."""
    with SessionLocal.begin() as db:
        load(db)
        offer_id = _make_offer(db).id
    try:
        yield offer_id
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_simultaneous_accepts_record_one_answer(committed_offer: int) -> None:
    barrier = threading.Barrier(2, timeout=10)
    responses: list[int] = []
    errors: list[Exception] = []

    def accept() -> None:
        try:
            with TestClient(_app()) as client:
                barrier.wait()
                responses.append(
                    client.post(URL, headers=HEADERS, json={"response": "ACCEPT"}).status_code
                )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=accept) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(responses) == [200, 409]
    with SessionLocal() as db:
        offer = db.get(CandidateOutreach, committed_offer)
        assert offer is not None
        assert offer.status is OutreachStatus.ACCEPTED
        assert offer.response_at == DEMO_NOW
        case = db.get(StaffingCase, offer.case_id)
        assert case is not None
        assert case.status is CaseStatus.WAITING_APPROVAL
        actions = list(db.scalars(select(AuditLog.action)))
        assert actions.count(AuditAction.OFFER_ACCEPTED) == 1
        assert actions.count(AuditAction.CASE_STATUS_CHANGED) == 2
