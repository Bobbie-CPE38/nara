"""The hospital demo's example cases and the test accounts of a demo reset
(round 6 PR EV7, docs/workflow.md 6.37.1 and 6.37.9). These tests commit."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.db.models import StaffingCase
from app.db.session import SessionLocal
from app.domain.enums import ActorName, AuditAction, EntityType
from app.main import app
from app.seed import hospital_demo
from app.services import actor_service, audit_service, auth_service, demo_account_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

client = TestClient(app)


def _cases() -> dict[int, str]:
    with SessionLocal() as db:
        return {
            case.id: case.status.value
            for case in db.scalars(select(StaffingCase).order_by(StaffingCase.id))
        }


def test_a_reset_with_the_hospital_plays_one_case_of_every_kind() -> None:
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    statuses = Counter(_cases().values())
    assert statuses == Counter(
        {
            # approved, staffed by hand, and (round 6 PR EV8) moved with both wards'
            # approval and a free nurse borrowed from another ward
            "RESOLVED": 4,
            "MANUAL_HANDOFF": 1,
            "UNRESOLVED": 1,
            # one for its head nurse; a move waiting for its source ward, and for both
            "WAITING_APPROVAL": 3,
            # offers out; and the move the source ward refused, which asks the next people
            "WAITING_RESPONSE": 2,
        }
    )


def test_the_case_page_says_who_came_who_decided_and_why_it_stopped() -> None:
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200
    by_status: dict[str, list[int]] = {}
    for case_id, status in _cases().items():
        by_status.setdefault(status, []).append(case_id)

    resolved = [
        client.get(f"/cases/{case_id}").json()["overview"] for case_id in by_status["RESOLVED"]
    ]
    approved = next(
        view
        for view in resolved
        if view["replacements"][0]["how"] == "APPROVED" and view["shift"]["ward_name"] == "Surgery"
    )
    by_hand = next(view for view in resolved if view["replacements"][0]["how"] == "MANUAL")
    closed = client.get(f"/cases/{by_status['UNRESOLVED'][0]}").json()["overview"]
    handoff = client.get(f"/cases/{by_status['MANUAL_HANDOFF'][0]}").json()["overview"]

    surgery_head = hospital_demo.STAFF_BASE + 1
    decision = approved["decisions"][0]
    assert decision["kind"] == "APPROVED" and decision["by"]["staff_id"] == surgery_head
    assert decision["by"]["role"] == "HEAD_NURSE" and decision["ward_name"] == "Surgery"
    assert decision["side"] == "DESTINATION"
    assert approved["events"][0]["event_type"] == "STAFF_UNAVAILABLE"
    assert approved["events"][0]["staff"]["ward_name"] == "Surgery"
    assert approved["outcome"] is None

    assert by_hand["decisions"][-1]["kind"] == "MANUAL_ASSIGNMENT"
    assert by_hand["decisions"][-1]["reason"] == "Called in by the head nurse"
    # The handoff before the manual assignment is history: the case did not stop there
    assert by_hand["outcome"] is None

    assert closed["outcome"]["kind"] == "CLOSED_UNRESOLVED"
    assert closed["outcome"]["reason"].startswith("Nobody could come")
    assert closed["outcome"]["by"]["role"] == "HEAD_NURSE"
    assert closed["replacements"] == []

    assert handoff["outcome"]["kind"] == "MANUAL_HANDOFF"
    assert handoff["outcome"]["reason"] in {"NO_CANDIDATE_LEFT", "WAVE_LIMIT_REACHED"}


def test_the_cross_ward_examples_show_each_ward_of_the_move() -> None:
    """Round 6 PR EV8 (6.38.5, 6.38.6): a move needs both wards, a free nurse one."""
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200
    details = [client.get(f"/cases/{case_id}").json() for case_id in _cases()]
    requests = [
        (detail["status"], request)
        for detail in details
        for request in detail["overview"]["requests"]
    ]

    def sides(request: dict) -> list[tuple[str, str]]:
        return [(side["side"], side["status"]) for side in request["sides"]]

    moves = [(status, request) for status, request in requests if request["moved_from"]]
    approved = next(request for status, request in moves if status == "RESOLVED")
    assert sides(approved) == [("DESTINATION", "APPROVED"), ("SOURCE", "APPROVED")]
    assert approved["assigned"] is True
    assert {side["by"]["role"] for side in approved["sides"]} == {"HEAD_NURSE"}
    assert approved["moved_from"]["ward_name"] in {"Emergency", "Cardiology"}
    assert approved["candidate"]["ward_name"] == approved["moved_from"]["ward_name"]

    waiting = sorted(sides(request) for status, request in moves if status == "WAITING_APPROVAL")
    assert waiting == [
        [("DESTINATION", "APPROVED"), ("SOURCE", "PENDING")],
        [("DESTINATION", "PENDING"), ("SOURCE", "PENDING")],
    ]
    pending = next(
        side
        for status, request in moves
        for side in request["sides"]
        if status == "WAITING_APPROVAL" and side["status"] == "PENDING"
    )
    # Who it waits for: the active head nurse of that ward, and the Supervisor's time
    assert [person["role"] for person in pending["waiting_for"]] == ["HEAD_NURSE"]
    assert pending["waiting_for"][0]["ward_name"] == pending["ward_name"]
    assert pending["supervisor_from"] is not None

    refused = next(request for status, request in moves if request["status"] == "REJECTED")
    assert sides(refused) == [("DESTINATION", "APPROVED"), ("SOURCE", "REJECTED")]
    assert refused["sides"][1]["reason"] == "We cannot spare a nurse from our shift"

    borrowed = next(
        detail
        for detail in details
        if detail["status"] == "RESOLVED"
        and any(
            request["moved_from"] is None
            and request["candidate"]["ward_name"] != detail["overview"]["shift"]["ward_name"]
            for request in detail["overview"]["requests"]
        )
    )
    (request,) = borrowed["overview"]["requests"]
    assert sides(request) == [("DESTINATION", "APPROVED")]
    assert borrowed["overview"]["replacements"][0]["how"] == "APPROVED"


def test_a_staff_id_that_is_not_an_id_does_not_break_the_case_page() -> None:
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200
    case_id = next(case_id for case_id, status in _cases().items() if status == "RESOLVED")
    with SessionLocal() as db:
        system = actor_service.component_id(db, ActorName.SYSTEM)
        for action, value in (
            (AuditAction.ASSIGNMENT_CREATED, None),
            (AuditAction.APPROVAL_TIMEOUT, "not-an-id"),
            (AuditAction.MANUAL_ASSIGNMENT_CREATED, True),
        ):
            audit_service.log(
                db,
                case_id=case_id,
                actor_id=system,
                action=action,
                entity_type=EntityType.STAFFING_CASES,
                entity_id=case_id,
                payload={"staff_id": value},
            )
        db.commit()

    answer = client.get(f"/cases/{case_id}")

    assert answer.status_code == 200, answer.text
    overview = answer.json()["overview"]
    assert len(overview["replacements"]) == 1
    timeout = next(row for row in overview["decisions"] if row["kind"] == "APPROVAL_TIMEOUT")
    assert timeout["candidate"] is None


def test_without_the_hospital_a_reset_plays_nothing() -> None:
    assert client.post("/demo/reset", json={"hospital": False}).status_code == 200

    assert _cases() == {}


def test_the_test_accounts_are_nurses_who_log_in_without_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "demo_account_password", SecretStr("demo-pass-1234"))
    monkeypatch.setattr(settings, "demo_manager_accounts", False)
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    with SessionLocal() as db:
        for staff_id in (105, 201, hospital_demo.STAFF_BASE + 2):
            assert auth_service.login(db, staff_id, "demo-pass-1234") is not None
        # The known password never opens a manager's account unless that is turned on
        for staff_id in (900, 950, hospital_demo.STAFF_BASE + 1):
            assert auth_service.login(db, staff_id, "demo-pass-1234") is None
        # A second reset keeps them and makes none twice
        assert demo_account_service.ensure(db) == []


def test_manager_accounts_only_when_turned_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_account_password", SecretStr("demo-pass-1234"))
    monkeypatch.setattr(settings, "demo_manager_accounts", True)
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    with SessionLocal() as db:
        for staff_id in (900, 902, 950, hospital_demo.STAFF_BASE + 1, 105):
            assert auth_service.login(db, staff_id, "demo-pass-1234") is not None


def test_the_reset_answers_200_when_the_accounts_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_db: object) -> list[int]:
        raise auth_service.AccountError("made by an overlapping reset")

    monkeypatch.setattr(demo_account_service, "ensure", broken)

    assert client.post("/demo/reset", json={"hospital": False}).status_code == 200


def test_no_password_no_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_account_password", None)
    assert client.post("/demo/reset").status_code == 200

    with SessionLocal() as db:
        assert auth_service.login(db, 900, "demo-pass-1234") is None
