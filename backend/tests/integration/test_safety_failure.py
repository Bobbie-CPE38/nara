"""A candidate who fails Safety is dropped and the case goes on (workflow.md 7.3, case ข)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateOutreach,
    SafetyValidation,
    Shift,
    StaffUnavailability,
)
from app.domain.enums import AuditAction, AvailabilityReason, OutreachStatus
from app.main import app
from app.seed.scenarios import safety_failure
from app.services import hard_rule_service
from tests.integration.case_rows import (
    NIGHT_SHIFT,
    cancel_roster,
    make_case,
    make_plan,
    offer,
    record_gap,
    short_case,
)

URL = "/demo/line-sim/respond"


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
        app.dependency_overrides.clear()


def _post(client: TestClient, row: CandidateOutreach, response: str = "ACCEPT", staff: int = 201):
    return client.post(
        URL, headers={"X-Demo-User": str(staff)}, json={"outreach_id": row.id, "response": response}
    )


def _make_unavailable(db: Session, staff_id: int) -> None:
    """Leave over the night shift that starts after the offer was sent."""
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    db.add(
        StaffUnavailability(
            staff_id=staff_id,
            start_at=shift.start_at - timedelta(hours=1),
            end_at=None,
            reason=AvailabilityReason.UNPLANNED_LEAVE,
        )
    )
    db.flush()


def _audit(db: Session, case_id: int) -> list[AuditLog]:
    db.expire_all()
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.id))
    )


def _actions(db: Session, case_id: int, *, with_status_changes: bool = False) -> list[AuditAction]:
    return [
        row.action
        for row in _audit(db, case_id)
        if with_status_changes or row.action is not AuditAction.CASE_STATUS_CHANGED
    ]


def _status_changes(db: Session, case_id: int) -> list[tuple[str, str]]:
    return [
        (row.payload["from"], row.payload["to"])
        for row in _audit(db, case_id)
        if row.action is AuditAction.CASE_STATUS_CHANGED
    ]


def test_another_open_offer_keeps_the_case_waiting(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case, items = short_case(db)
    first = offer(db, case, items[201])
    second = offer(db, case, items[202])
    _make_unavailable(db, 201)
    db.commit()

    result = _post(client, first)

    assert result.status_code == 200, result.text
    assert result.json()["outreach_status"] == "CANCELLED"
    assert result.json()["case_status"] == "WAITING_RESPONSE"
    db.expire_all()
    [validation] = db.scalars(select(SafetyValidation).where(SafetyValidation.case_id == case.id))
    assert validation.is_passed is False
    assert validation.failure_reason == "UNAVAILABLE"
    assert db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == case.id)).all() == []
    still_open = db.get(CandidateOutreach, second.id)
    assert still_open is not None
    assert still_open.status is OutreachStatus.SENT
    assert _actions(db, case.id, with_status_changes=True) == [
        AuditAction.OFFER_ACCEPTED,
        AuditAction.SAFETY_FAILED,
    ]


def test_without_an_open_offer_the_next_wave_goes_out(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case, items = short_case(db)
    first = offer(db, case, items[201])
    offer(db, case, items[202], OutreachStatus.REJECTED)
    _make_unavailable(db, 201)
    db.commit()

    result = _post(client, first)

    assert result.status_code == 200, result.text
    assert result.json()["case_status"] == "WAITING_RESPONSE"
    db.expire_all()
    sent = list(
        db.scalars(
            select(CandidateOutreach).where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.status == OutreachStatus.SENT,
            )
        )
    )
    assert [row.candidate_item_id for row in sent] == [items[203].id]
    assert _status_changes(db, case.id) == [
        ("WAITING_RESPONSE", "OUTREACH"),
        ("OUTREACH", "WAITING_RESPONSE"),
    ]
    wave = next(row for row in _audit(db, case.id) if row.action is AuditAction.OFFER_SENT)
    assert wave.payload["wave"] == 2


def test_nobody_left_stops_at_manual_handoff_not_failed(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    cancel_roster(db, 105)
    case = make_case(db)
    record_gap(db, case)
    items = make_plan(db, case, (201,))
    only = offer(db, case, items[201])
    _make_unavailable(db, 201)
    db.commit()

    result = _post(client, only)

    assert result.status_code == 200, result.text
    assert result.json()["case_status"] == "MANUAL_HANDOFF"
    assert _actions(db, case.id) == [
        AuditAction.OFFER_ACCEPTED,
        AuditAction.SAFETY_FAILED,
        AuditAction.MANUAL_HANDOFF,
    ]
    handoff = next(row for row in _audit(db, case.id) if row.action is AuditAction.MANUAL_HANDOFF)
    assert handoff.payload["reason"] == "NO_CANDIDATE_LEFT"


def test_a_system_fault_still_fails_the_case_and_keeps_the_answer(
    client: TestClient, production_seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = production_seeded
    case, items = short_case(db)
    only = offer(db, case, items[201])
    db.commit()

    def broken_loader(*args: object, **kwargs: object) -> None:
        raise RuntimeError("loader down")

    monkeypatch.setattr(hard_rule_service, "check_items", broken_loader)

    result = _post(client, only)

    assert result.status_code == 200, result.text
    assert result.json()["outreach_status"] == "ACCEPTED"
    assert result.json()["case_status"] == "FAILED"
    assert db.scalars(select(SafetyValidation)).all() == []
    actions = _actions(db, case.id)
    assert actions[0] is AuditAction.OFFER_ACCEPTED
    assert actions[-1] is AuditAction.WORKFLOW_FAILED
    assert _audit(db, case.id)[-1].payload["error_type"] == "RuntimeError"


def test_a_failed_acceptance_does_not_pause_the_offer_of_another_case(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    first_case, first_items = short_case(db)
    first = offer(db, first_case, first_items[201])
    second_case, second_items = short_case(db)
    second = offer(db, second_case, second_items[201])
    _make_unavailable(db, 201)
    db.commit()

    assert _post(client, first).status_code == 200

    rows = client.get(
        "/demo/line-sim/offers", headers={"X-Demo-User": "201"}, params={"staff_id": 201}
    ).json()
    by_id = {row["id"]: row for row in rows}
    assert by_id[first.id]["status"] == "CANCELLED"
    assert by_id[first.id]["cancellation_reason"] == "UNAVAILABLE"
    assert by_id[second.id]["can_accept"] is True
    assert by_id[second.id]["blocked_reason"] is None


def test_safety_failure_scenario_ends_with_the_other_candidate_resolved(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    safety_failure.seed(db)
    db.commit()

    opened = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["case_status"] == "WAITING_RESPONSE"
    case_id = opened.json()["case_id"]

    def sent_offer(staff_id: int) -> dict[str, object]:
        rows = client.get(
            "/demo/line-sim/offers",
            headers={"X-Demo-User": str(staff_id)},
            params={"staff_id": staff_id},
        ).json()
        return next(row for row in rows if row["case_id"] == case_id and row["status"] == "SENT")

    first, second = sent_offer(201), sent_offer(202)

    # The event in the middle: 201 takes a shift that clashes with the night shift
    safety_failure.take_clashing_shift(db)
    db.commit()

    def answer(staff_id: int, offer_id: object) -> dict[str, object]:
        result = client.post(
            URL,
            headers={"X-Demo-User": str(staff_id)},
            json={"outreach_id": offer_id, "response": "ACCEPT"},
        )
        assert result.status_code == 200, result.text
        body: dict[str, object] = result.json()
        return body

    failed = answer(201, first["id"])
    assert failed["outreach_status"] == "CANCELLED"
    assert failed["case_status"] == "WAITING_RESPONSE"
    assert answer(202, second["id"])["case_status"] == "WAITING_APPROVAL"

    pending = client.get("/approvals", params={"pending": "true"}, headers={"X-Demo-User": "900"})
    [request] = pending.json()
    assert request["staff_id"] == 202
    decided = client.post(
        f"/approvals/{request['id']}/decision",
        headers={"X-Demo-User": "900"},
        json={"approved": True},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["case_status"] == "RESOLVED"

    audit = client.get(f"/cases/{case_id}/audit").json()
    rows = [row for row in audit if row["action"] != "CASE_STATUS_CHANGED"]
    assert [row["action"] for row in rows] == [
        "EVENT_RECEIVED",
        "UNAVAILABILITY_CREATED",
        "CASE_OPENED",
        "GAP_ASSESSED",
        "SOLVER_EXECUTED",
        "OFFER_SENT",
        "OFFER_SENT",
        "OFFER_ACCEPTED",
        "SAFETY_FAILED",
        "OFFER_ACCEPTED",
        "SAFETY_PASSED",
        "APPROVAL_REQUESTED",
        "APPROVAL_APPROVED",
        "ASSIGNMENT_CREATED",
        "CASE_RESOLVED",
    ]
    safety = next(row for row in rows if row["action"] == "SAFETY_FAILED")
    assert safety["payload"]["staff_id"] == 201
    assert safety["payload"]["failed_rules"] == ["SHIFT_CONFLICT"]

    roster = client.get("/roster", params={"shift_id": 1}, headers={"X-Demo-User": "900"}).json()
    replacements = [row for row in roster["assignments"] if row["staff_id"] == 202]
    assert [(row["status"], row["assignment_type"]) for row in replacements] == [
        ("ASSIGNED", "REPLACEMENT")
    ]
    assert all(row["staff_id"] != 201 for row in roster["assignments"])
