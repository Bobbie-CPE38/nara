"""The status changes of whole cases stay as they were before LangGraph (round 5 PR G).

docs/workflow.md 6.23 and R5-Q6: the real handlers run through the real HTTP
routes on the round 4 seed (the Golden Case with the second ward, the Float Pool
and the Supervisor). Each expected list was recorded from the orchestrator
before PR G, as (from, to) pairs of the CASE_STATUS_CHANGED rows in id order.
The last tests check that LINE delivery still starts only after the round's
commit, and finds nothing to send after a round that failed.
"""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import AuditLog, CandidateOutreach, StaffingCase
from app.domain.enums import AuditAction, CaseStatus
from app.main import app
from app.seed.scenarios import (
    candidate_reject,
    head_nurse_reject,
    merge_gap,
    no_feasible_solution,
    safety_failure,
)
from app.services import line_delivery_service
from app.workflow import orchestrator
from app.workflow.handlers import contact_candidate
from app.workflow.handlers.base import HandlerResult

RESPOND = "/demo/line-sim/respond"
LEAVE = {"event_type": "STAFF_UNAVAILABLE", "shift_id": 1}
APPROVER = {"X-Demo-User": "900"}

Transitions = list[tuple[str, str]]

GOLDEN: Transitions = [
    ("OPEN", "ASSESSING"),
    ("ASSESSING", "OPTIMIZING"),
    ("OPTIMIZING", "OUTREACH"),
    ("OUTREACH", "WAITING_RESPONSE"),
    ("WAITING_RESPONSE", "WAITING_APPROVAL"),
    ("WAITING_APPROVAL", "EXECUTING"),
    ("EXECUTING", "RESOLVED"),
]
FIRST_WAVE: Transitions = GOLDEN[:4]
CLOSE: Transitions = GOLDEN[-3:]


class Driver:
    """The calls a scenario makes, all through the HTTP routes."""

    def __init__(self, client: TestClient, db: Session) -> None:
        self.client = client
        self.db = db
        self.case_id = 0

    def report_leave(self) -> dict[str, Any]:
        response = self.client.post("/events", headers={"X-Demo-User": "105"}, json=LEAVE)
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        if body["case_id"] is not None:
            self.case_id = body["case_id"]
        return body

    def answer(self, staff_id: int, response: str) -> str:
        rows = self.client.get(
            "/demo/line-sim/offers",
            headers={"X-Demo-User": str(staff_id)},
            params={"staff_id": staff_id},
        ).json()
        offer = next(
            row for row in rows if row["case_id"] == self.case_id and row["status"] == "SENT"
        )
        result = self.client.post(
            RESPOND,
            headers={"X-Demo-User": str(staff_id)},
            json={"outreach_id": offer["id"], "response": response},
        )
        assert result.status_code == 200, result.text
        return str(result.json()["case_status"])

    def decide(self, staff_id: int, approved: bool, reason: str | None = None) -> str:
        pending = self.client.get("/approvals", params={"pending": "true"}, headers=APPROVER)
        request = next(row for row in pending.json() if row["staff_id"] == staff_id)
        body: dict[str, Any] = {"approved": approved}
        if reason is not None:
            body["reason"] = reason
        result = self.client.post(
            f"/approvals/{request['id']}/decision", headers=APPROVER, json=body
        )
        assert result.status_code == 200, result.text
        return str(result.json()["case_status"])

    def transitions(self) -> Transitions:
        self.db.expire_all()
        rows = self.db.scalars(
            select(AuditLog)
            .where(
                AuditLog.case_id == self.case_id,
                AuditLog.action == AuditAction.CASE_STATUS_CHANGED,
            )
            .order_by(AuditLog.id)
        )
        return [(row.payload["from"], row.payload["to"]) for row in rows]


def _golden(run: Driver) -> None:
    assert run.report_leave()["case_status"] == "WAITING_RESPONSE"
    assert run.answer(201, "ACCEPT") == "WAITING_APPROVAL"
    assert run.decide(201, approved=True) == "RESOLVED"


def _candidate_reject(run: Driver) -> None:
    candidate_reject.seed(run.db)
    run.db.commit()
    run.report_leave()
    for staff_id, response in candidate_reject.RESPONSES:
        run.answer(staff_id, response)
    assert run.decide(203, approved=True) == "RESOLVED"


def _head_nurse_reject(run: Driver) -> None:
    head_nurse_reject.seed(run.db)
    run.db.commit()
    run.report_leave()
    run.answer(head_nurse_reject.REJECTED_STAFF_ID, "ACCEPT")
    run.decide(
        head_nurse_reject.REJECTED_STAFF_ID,
        approved=False,
        reason=head_nurse_reject.REJECTION_REASON,
    )
    run.answer(head_nurse_reject.REPLACEMENT_STAFF_ID, "ACCEPT")
    assert run.decide(head_nurse_reject.REPLACEMENT_STAFF_ID, approved=True) == "RESOLVED"


def _safety_failure(run: Driver) -> None:
    safety_failure.seed(run.db)
    run.db.commit()
    run.report_leave()
    safety_failure.take_clashing_shift(run.db)
    run.db.commit()
    assert run.answer(201, "ACCEPT") == "WAITING_RESPONSE"
    run.answer(202, "ACCEPT")
    assert run.decide(202, approved=True) == "RESOLVED"


def _no_feasible_solution(run: Driver) -> None:
    no_feasible_solution.seed(run.db)
    run.db.commit()
    assert run.report_leave()["case_status"] == "MANUAL_HANDOFF"


def _merge_gap(run: Driver) -> None:
    merge_gap.seed(run.db)
    run.db.commit()
    event = run.report_leave()
    assert event["event_status"] == "RECEIVED"
    advanced = run.client.post(
        "/demo/clock/advance", json={"seconds": merge_gap.MERGE_WINDOW_SECONDS}
    )
    assert advanced.status_code == 200, advanced.text
    status = run.client.get(f"/events/{event['event_id']}").json()
    assert status["case_status"] == "WAITING_RESPONSE"
    run.case_id = status["case_id"]
    run.answer(201, "ACCEPT")
    assert run.decide(201, approved=True) == "RESOLVED"


SCENARIOS: dict[str, tuple[Callable[[Driver], None], Transitions]] = {
    "golden_case": (_golden, GOLDEN),
    "candidate_reject": (
        _candidate_reject,
        [*FIRST_WAVE, ("WAITING_RESPONSE", "OUTREACH"), ("OUTREACH", "WAITING_RESPONSE"), *CLOSE],
    ),
    "head_nurse_reject": (
        _head_nurse_reject,
        [
            *FIRST_WAVE,
            ("WAITING_RESPONSE", "WAITING_APPROVAL"),
            ("WAITING_APPROVAL", "WAITING_RESPONSE"),
            *CLOSE,
        ],
    ),
    "safety_failure": (_safety_failure, GOLDEN),
    "no_feasible_solution": (
        _no_feasible_solution,
        [("OPEN", "ASSESSING"), ("ASSESSING", "OPTIMIZING"), ("OPTIMIZING", "MANUAL_HANDOFF")],
    ),
    "merge_gap": (_merge_gap, GOLDEN),
}


@pytest.fixture
def driver(production_seeded: Session) -> Iterator[Driver]:
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
        with TestClient(app) as client:
            yield Driver(client, production_seeded)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_case_status_changes_match_the_recording_from_before_langgraph(
    driver: Driver, name: str
) -> None:
    run, expected = SCENARIOS[name]
    run(driver)

    assert driver.transitions() == expected


class _Dispatches:
    """Records what the orchestrator's post-commit LINE dispatch sees."""

    def __init__(self) -> None:
        self.calls: list[tuple[bool, CaseStatus, int]] = []

    def __call__(self, db: Session, *, case_id: int | None = None) -> None:
        assert case_id is not None
        case = db.get(StaffingCase, case_id)
        assert case is not None
        offers = db.scalars(select(CandidateOutreach).where(CandidateOutreach.case_id == case_id))
        self.calls.append((db.in_nested_transaction(), case.status, len(list(offers))))


def test_line_dispatch_runs_after_the_round_commits(
    driver: Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatches = _Dispatches()
    monkeypatch.setattr(line_delivery_service, "dispatch_pending", dispatches)

    driver.report_leave()

    # One round: the savepoint is closed and the case and both offers are in
    assert dispatches.calls == [(False, CaseStatus.WAITING_RESPONSE, 2)]


def test_a_failed_round_leaves_nothing_for_line_to_send(
    driver: Driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    def contact_then_fail(db: Session, case: StaffingCase) -> HandlerResult:
        contact_candidate.handle(db, case)
        raise RuntimeError("after the offers were written")

    dispatches = _Dispatches()
    monkeypatch.setattr(line_delivery_service, "dispatch_pending", dispatches)
    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.OUTREACH, contact_then_fail)

    driver.report_leave()

    # The offers rolled back with the round, so the dispatch finds none (D11)
    assert dispatches.calls == [(False, CaseStatus.FAILED, 0)]
    failure = driver.db.scalars(
        select(AuditLog).where(
            AuditLog.case_id == driver.case_id, AuditLog.action == AuditAction.WORKFLOW_FAILED
        )
    ).one()
    assert failure.payload["failed_at"] == "OUTREACH"
