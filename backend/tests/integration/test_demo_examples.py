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
from app.main import app
from app.seed import hospital_demo
from app.services import auth_service, demo_account_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

client = TestClient(app)


def _cases() -> dict[int, str]:
    with SessionLocal() as db:
        return {case.id: case.status.value for case in db.scalars(select(StaffingCase))}


def test_a_reset_with_the_hospital_plays_one_case_of_every_kind() -> None:
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    statuses = Counter(_cases().values())
    assert statuses == Counter(
        {
            "RESOLVED": 2,  # approved, and staffed by hand from the handoff page
            "MANUAL_HANDOFF": 1,
            "UNRESOLVED": 1,
            "WAITING_APPROVAL": 1,
            "WAITING_RESPONSE": 1,
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
    approved = next(view for view in resolved if view["replacements"][0]["how"] == "APPROVED")
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
    assert by_hand["outcome"]["kind"] == "MANUAL_HANDOFF"

    assert closed["outcome"]["kind"] == "CLOSED_UNRESOLVED"
    assert closed["outcome"]["reason"].startswith("Nobody could come")
    assert closed["outcome"]["by"]["role"] == "HEAD_NURSE"
    assert closed["replacements"] == []

    assert handoff["outcome"]["kind"] == "MANUAL_HANDOFF"
    assert handoff["outcome"]["reason"] in {"NO_CANDIDATE_LEFT", "WAVE_LIMIT_REACHED"}


def test_without_the_hospital_a_reset_plays_nothing() -> None:
    assert client.post("/demo/reset", json={"hospital": False}).status_code == 200

    assert _cases() == {}


def test_the_test_accounts_log_in_without_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_account_password", SecretStr("demo-pass-1234"))
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    with SessionLocal() as db:
        for staff_id in (900, 950, 105, hospital_demo.STAFF_BASE + 1):
            assert auth_service.login(db, staff_id, "demo-pass-1234") is not None
        # A second reset keeps them and makes none twice
        assert demo_account_service.ensure(db) == []


def test_no_password_no_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_account_password", None)
    assert client.post("/demo/reset").status_code == 200

    with SessionLocal() as db:
        assert auth_service.login(db, 900, "demo-pass-1234") is None
