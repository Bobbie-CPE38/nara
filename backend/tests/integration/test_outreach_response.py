"""Wave responses through real HTTP routes, rollback and independent DB connections."""

import threading
from collections.abc import Iterator
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.constants import MAX_BIGINT
from app.db.base import Base
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateOutreach,
    SafetyValidation,
    StaffingCase,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import AuditAction, CandidateResponse, CaseStatus, OutreachStatus
from app.main import app
from app.seed import load
from app.services import outreach_service
from tests.integration.case_rows import offer as make_offer
from tests.integration.case_rows import short_case

URL = "/demo/line-sim/respond"
HEADERS = {"X-Demo-User": "201"}


def _make_offer(db: Session, *, staff_id: int = 201) -> CandidateOutreach:
    case, items = short_case(db)
    return make_offer(db, case, items[staff_id])


@pytest.fixture
def offer(production_seeded: Session) -> CandidateOutreach:
    row = _make_offer(production_seeded)
    production_seeded.commit()
    return row


@pytest.fixture
def client(production_seeded: Session, offer: CandidateOutreach) -> Iterator[TestClient]:
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
        app.dependency_overrides.clear()


def _post(client: TestClient, row: CandidateOutreach, response: str = "ACCEPT", staff: int = 201):
    return client.post(
        URL, headers={"X-Demo-User": str(staff)}, json={"outreach_id": row.id, "response": response}
    )


def test_accept_runs_individual_safety_and_recompute(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    result = _post(client, offer)
    assert result.status_code == 200, result.text
    assert result.json()["case_status"] == "WAITING_APPROVAL"
    db = production_seeded
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    assert db.scalar(select(func.count()).select_from(SafetyValidation)) == 1
    actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == [
        AuditAction.OFFER_ACCEPTED,
        AuditAction.SAFETY_PASSED,
        AuditAction.APPROVAL_REQUESTED,
        AuditAction.CASE_STATUS_CHANGED,
    ]


def test_reject_sends_next_wave(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    result = _post(client, offer, "REJECT")
    assert result.status_code == 200, result.text
    assert result.json()["outreach_status"] == "REJECTED"
    rows = list(
        production_seeded.scalars(
            select(CandidateOutreach).where(
                CandidateOutreach.case_id == offer.case_id,
                CandidateOutreach.status == OutreachStatus.SENT,
            )
        )
    )
    assert len(rows) == 2
    assert all(row.candidate_item_id != offer.candidate_item_id for row in rows)


@pytest.mark.parametrize("response", ["ACCEPT", "REJECT"])
def test_repeated_answer_is_409_without_second_audit(
    client: TestClient, offer: CandidateOutreach, response: str, production_seeded: Session
) -> None:
    assert _post(client, offer, response).status_code == 200
    before = production_seeded.scalar(select(func.count()).select_from(AuditLog))
    assert _post(client, offer, response).status_code == 409
    assert production_seeded.scalar(select(func.count()).select_from(AuditLog)) == before


@pytest.mark.parametrize("response", ["ACCEPT", "REJECT"])
def test_other_staff_cannot_answer(
    client: TestClient, offer: CandidateOutreach, response: str
) -> None:
    assert _post(client, offer, response, staff=202).status_code == 409


@pytest.mark.parametrize("state", list(OutreachStatus)[::])
def test_only_sent_can_be_answered(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session, state: OutreachStatus
) -> None:
    if state == OutreachStatus.SENT:
        return
    offer.status = state
    production_seeded.commit()
    assert _post(client, offer).status_code == 409


@pytest.mark.parametrize(
    "state",
    [CaseStatus.FAILED, CaseStatus.RESOLVED, CaseStatus.MANUAL_HANDOFF, CaseStatus.UNRESOLVED],
)
def test_stopped_case_cannot_be_answered(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session, state: CaseStatus
) -> None:
    case = production_seeded.get(StaffingCase, offer.case_id)
    assert case is not None
    case.status = state
    production_seeded.commit()
    assert _post(client, offer).status_code == 409


@pytest.mark.parametrize("value", [None, 0, -1, MAX_BIGINT + 1, True, False, 1.0, "1"])
def test_offer_id_is_strict_bigint(client: TestClient, value: object) -> None:
    assert (
        client.post(
            URL, headers=HEADERS, json={"outreach_id": value, "response": "ACCEPT"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"response": "ACCEPT"},
        {"outreach_id": 1},
        {"outreach_id": 1, "response": "OTHER"},
        {"outreach_id": 1, "response": "ACCEPT", "staff_id": 201},
    ],
)
def test_body_validation(client: TestClient, body: dict[str, object]) -> None:
    assert client.post(URL, headers=HEADERS, json=body).status_code == 422


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_authentication_required(
    client: TestClient, headers: dict[str, str], offer: CandidateOutreach
) -> None:
    assert (
        client.post(
            URL, headers=headers, json={"outreach_id": offer.id, "response": "ACCEPT"}
        ).status_code
        == 401
    )


def test_unknown_id_does_not_answer_another_offer(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    assert (
        client.post(
            URL, headers=HEADERS, json={"outreach_id": 999999, "response": "ACCEPT"}
        ).status_code
        == 409
    )
    production_seeded.refresh(offer)
    assert offer.status == OutreachStatus.SENT
    assert production_seeded.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_multiple_offers_select_by_id_and_pause_accept_only(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    second = _make_offer(production_seeded)
    production_seeded.commit()
    assert _post(client, offer).status_code == 200
    assert _post(client, second).status_code == 409
    offers = client.get("/demo/line-sim/offers", headers=HEADERS, params={"staff_id": 201}).json()
    paused = next(row for row in offers if row["id"] == second.id)
    assert paused["can_accept"] is False
    assert paused["can_reject"] is True
    assert paused["blocked_reason"] == "AWAITING_OTHER_CASE"
    assert _post(client, second, "REJECT").status_code == 200


def test_over_acceptance_stays_as_reserve(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    db = production_seeded
    from app.db.models import CandidateItem

    item = db.scalar(
        select(CandidateItem).where(
            CandidateItem.staff_id == 202,
            CandidateItem.plan_id == db.get(CandidateItem, offer.candidate_item_id).plan_id,
        )
    )
    assert item is not None
    case = db.get(StaffingCase, offer.case_id)
    assert case is not None
    second = make_offer(db, case, item)
    db.commit()
    assert _post(client, offer).status_code == 200
    assert _post(client, second, staff=202).status_code == 200
    db.refresh(second)
    assert second.status == OutreachStatus.ACCEPTED
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    assert (
        db.scalar(select(SafetyValidation.id).where(SafetyValidation.candidate_item_id == item.id))
        is None
    )


def test_delivery_failure_preserves_rejection_but_fails_case(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    with patch(
        "app.integrations.line.mock.send_offer", side_effect=RuntimeError("delivery failed")
    ):
        response = _post(client, offer, "REJECT")
    assert response.status_code == 200
    assert response.json()["case_status"] == "FAILED"
    assert response.json()["outreach_status"] == "REJECTED"
    assert production_seeded.scalar(select(func.count()).select_from(CandidateOutreach)) == 1


@pytest.fixture
def committed_offers(frozen_clock: datetime) -> Iterator[tuple[int, int]]:
    with SessionLocal.begin() as db:
        load(db)
        first = _make_offer(db)
        second = _make_offer(db)
        ids = (first.id, second.id)
    try:
        yield ids
    finally:
        assert (engine.url.database or "").endswith("_test")
        with engine.begin() as conn:
            conn.execute(
                text("TRUNCATE " + ", ".join(Base.metadata.tables) + " RESTART IDENTITY CASCADE")
            )
        engine.dispose()


@pytest.mark.parametrize("same_offer", [True, False])
def test_simultaneous_accepts_only_one_commitment(
    committed_offers: tuple[int, int], same_offer: bool
) -> None:
    barrier = threading.Barrier(2, timeout=10)
    codes: list[int] = []
    errors: list[Exception] = []

    def respond(offer_id: int) -> None:
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                try:
                    outreach_service.record_response(
                        db,
                        staff_id=201,
                        actor_id=actor_id,
                        outreach_id=offer_id,
                        response=CandidateResponse.ACCEPT,
                    )
                    codes.append(200)
                except outreach_service.OpenOfferConflictError:
                    db.rollback()
                    codes.append(409)
        except Exception as error:
            errors.append(error)

    # Use actor IDs from the seed rather than assuming staff ID equals actor ID.
    from app.services import actor_service

    with SessionLocal() as db:
        actor_id = actor_service.user_id(db, 201)
    assert actor_id > 0
    ids = (committed_offers[0], committed_offers[0] if same_offer else committed_offers[1])
    threads = [threading.Thread(target=respond, args=(offer_id,), daemon=True) for offer_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(codes) == [200, 409]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CandidateOutreach)
                .where(CandidateOutreach.status == OutreachStatus.ACCEPTED)
            )
            == 1
        )


def test_stale_id_does_not_answer_replacement(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    old_id = offer.id
    offer.status = OutreachStatus.CANCELLED
    replacement = _make_offer(production_seeded)
    production_seeded.commit()
    result = client.post(URL, headers=HEADERS, json={"outreach_id": old_id, "response": "ACCEPT"})
    assert result.status_code == 409
    production_seeded.refresh(replacement)
    assert replacement.status == OutreachStatus.SENT
    assert production_seeded.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_reserve_is_promoted_after_head_nurse_rejection(production_seeded: Session) -> None:
    from app.domain.enums import CandidateResponse
    from app.services import actor_service
    from app.workflow import orchestrator

    db = production_seeded
    case, items = short_case(db)
    first = make_offer(db, case, items[201])
    second = make_offer(db, case, items[202])
    outreach_service.record_response(
        db,
        staff_id=201,
        actor_id=actor_service.user_id(db, 201),
        outreach_id=first.id,
        response=CandidateResponse.ACCEPT,
    )
    outreach_service.record_response(
        db,
        staff_id=202,
        actor_id=actor_service.user_id(db, 202),
        outreach_id=second.id,
        response=CandidateResponse.ACCEPT,
    )
    request = db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.candidate_item_id == items[201].id)
    )
    assert request is not None
    # PR 4 will perform these rejection writes before calling this public seam.
    request.is_pending = False
    request.is_approved = False
    outreach_service.cancel_offer(db, first)
    db.flush()
    orchestrator.recompute(db, case.id, prepare=outreach_service.promote_reserves)
    assert (
        db.scalar(
            select(ApprovalRequest.id).where(
                ApprovalRequest.candidate_item_id == items[202].id,
                ApprovalRequest.is_pending.is_(True),
            )
        )
        is not None
    )
    assert case.status == CaseStatus.WAITING_APPROVAL


def test_rejecting_shared_pool_cases_concurrently_sends_next_waves(
    committed_offers: tuple[int, int],
) -> None:
    from app.services import actor_service

    with SessionLocal() as db:
        actor_id = actor_service.user_id(db, 201)
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def reject(offer_id: int) -> None:
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                row, case = outreach_service.record_response(
                    db,
                    staff_id=201,
                    actor_id=actor_id,
                    outreach_id=offer_id,
                    response=CandidateResponse.REJECT,
                )
                assert row.status == OutreachStatus.REJECTED
                assert case.status == CaseStatus.WAITING_RESPONSE
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=reject, args=(offer_id,), daemon=True)
        for offer_id in committed_offers
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CandidateOutreach)
                .where(CandidateOutreach.status == OutreachStatus.SENT)
            )
            == 4
        )


def test_unrecordable_workflow_failure_rolls_back_answer(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    from app.services.actor_service import ActorNotFoundError

    with patch(
        "app.services.actor_service.component_id", side_effect=ActorNotFoundError("missing actor")
    ):
        result = _post(client, offer)
    assert result.status_code == 500
    production_seeded.refresh(offer)
    assert offer.status == OutreachStatus.SENT
    assert offer.response_at is None
    assert production_seeded.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_waiting_other_case_releases_offer_after_rejection(
    client: TestClient, offer: CandidateOutreach, production_seeded: Session
) -> None:
    second = _make_offer(production_seeded)
    production_seeded.commit()
    assert _post(client, offer).status_code == 200
    assert _post(client, second).status_code == 409
    request = production_seeded.scalar(
        select(ApprovalRequest).where(ApprovalRequest.candidate_item_id == offer.candidate_item_id)
    )
    assert request is not None
    request.is_pending = False
    request.is_approved = False
    outreach_service.cancel_offer(production_seeded, offer)
    production_seeded.commit()
    assert _post(client, second).status_code == 200


@pytest.mark.parametrize("final_answer", ["ACCEPT", "REJECT"])
def test_candidate_reject_scenario_reaches_second_wave(
    production_seeded: Session, final_answer: str
) -> None:
    from app.seed.scenarios import candidate_reject

    db = production_seeded
    candidate_reject.seed(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            opened = client.post(
                "/events",
                headers={"X-Demo-User": "105"},
                json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
            )
            assert opened.status_code == 201, opened.text
            case_id = opened.json()["case_id"]
            for staff_id, answer in candidate_reject.RESPONSES:
                if staff_id == 203:
                    answer = final_answer
                rows = client.get(
                    "/demo/line-sim/offers",
                    headers={"X-Demo-User": str(staff_id)},
                    params={"staff_id": staff_id},
                ).json()
                current = next(
                    row for row in rows if row["case_id"] == case_id and row["status"] == "SENT"
                )
                result = client.post(
                    URL,
                    headers={"X-Demo-User": str(staff_id)},
                    json={"outreach_id": current["id"], "response": answer},
                )
                assert result.status_code == 200, result.text
            assert result.json()["case_status"] == (
                "WAITING_APPROVAL" if final_answer == "ACCEPT" else "MANUAL_HANDOFF"
            )
            audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.entity_id == current["id"], AuditLog.action == AuditAction.OFFER_SENT
                )
            )
            assert audit is not None and audit.payload["wave"] == 2
    finally:
        app.dependency_overrides.clear()


def test_two_staff_accept_same_case_concurrently_one_is_reserve(
    committed_offers: tuple[int, int],
) -> None:
    from app.db.models import CandidateItem
    from app.services import actor_service

    with SessionLocal.begin() as db:
        first = db.get(CandidateOutreach, committed_offers[0])
        assert first is not None
        case = db.get(StaffingCase, first.case_id)
        original = db.get(CandidateItem, first.candidate_item_id)
        assert case is not None and original is not None
        second_item = db.scalar(
            select(CandidateItem).where(
                CandidateItem.plan_id == original.plan_id, CandidateItem.staff_id == 202
            )
        )
        assert second_item is not None
        second = make_offer(db, case, second_item)
        case_id = case.id
        requests = [
            (201, first.id, actor_service.user_id(db, 201)),
            (202, second.id, actor_service.user_id(db, 202)),
        ]
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def accept(staff_id: int, offer_id: int, actor_id: int) -> None:
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                result, _ = outreach_service.record_response(
                    db,
                    staff_id=staff_id,
                    actor_id=actor_id,
                    outreach_id=offer_id,
                    response=CandidateResponse.ACCEPT,
                )
                assert result.status == OutreachStatus.ACCEPTED
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=accept, args=values, daemon=True) for values in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CandidateOutreach)
                .where(
                    CandidateOutreach.case_id == case_id,
                    CandidateOutreach.status == OutreachStatus.ACCEPTED,
                )
            )
            == 2
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ApprovalRequest)
                .where(ApprovalRequest.case_id == case_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SafetyValidation)
                .where(SafetyValidation.case_id == case_id)
            )
            == 1
        )
