"""Test runs through the routes (round 6 PR EV5a, docs/workflow.md 6.35).

Rows of the silent-failure table of 6.35.6. Every run starts with a real demo reset,
so these tests commit, like test_demo_reset.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import clock
from app.db.models import Actor, AuditLog, CandidateItem, Ward
from app.db.session import SessionLocal
from app.domain.enums import ApprovalSide, AuditAction, EntityType
from app.main import app
from app.seed.large_demo import STAFF_BASE, WARD_BASE, generate
from app.seed.reset import reset_demo
from app.services import approval_wards, auth_service, test_run_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

HEAD_NURSE = {"X-Demo-User": "900"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    try:
        yield TestClient(app)
    finally:
        clock.reset()


def _start(client: TestClient, scenario: str = "golden", **body: Any) -> dict[str, Any]:
    answer = client.post(
        "/demo/test-runs",
        json={"tester_code": "T01", "scenario": scenario, "auto_nurses": True} | body,
    )
    assert answer.status_code == 201, answer.text
    return answer.json()


def _play(client: TestClient, minutes: int, side: str | None = None) -> None:
    """Move the run a minute at a time; the tester approves as 900 whenever asked."""
    for _ in range(minutes):
        assert client.post("/demo/clock/advance", json={"seconds": 60}).status_code == 200
        for request in client.get("/approvals?pending=true", headers=HEAD_NURSE).json():
            if any(
                ward["side"] == "DESTINATION" and ward["status"] == "PENDING"
                for ward in request["wards"]
            ):
                body = {"approved": True} | ({} if side is None else {"side": side})
                decided = client.post(
                    f"/approvals/{request['id']}/decision", headers=HEAD_NURSE, json=body
                )
                assert decided.status_code == 200, decided.text


def _rows(action: AuditAction) -> list[tuple[str, dict[str, Any]]]:
    """(actor name, payload) of every row with this action."""
    with SessionLocal() as db:
        return [
            (name, payload)
            for name, payload in db.execute(
                select(Actor.name, AuditLog.payload)
                .join(Actor, Actor.id == AuditLog.actor_id)
                .where(AuditLog.action == action)
                .order_by(AuditLog.id)
            )
        ]


def test_a_golden_run_with_simulated_nurses_fills_and_stores_the_kpi(client: TestClient) -> None:
    run = _start(client)
    shown = client.get("/clock").json()
    assert shown["mode"] == "scenario" and shown["test_run_id"] == run["test_run_id"]
    assert run["case_id"] is not None

    _play(client, 3)
    finished = client.post(f"/demo/test-runs/{run['test_run_id']}/finish")

    assert finished.status_code == 200
    kpi = finished.json()["result"]
    assert kpi["invalid"] is False and kpi["advanced_seconds"] == 180
    # 201 accepts 120 s after the offer: system time, then the time the tester really spent
    assert 120 <= kpi["time_to_fill_system_s"] < 125
    assert 0 <= kpi["time_to_fill_s"] < 5
    assert kpi["filled_before_shift_start"] is True and kpi["from_other_ward"] is False
    assert kpi["offers_sent"] >= 1
    assert client.get("/clock").json()["mode"] == "frozen"
    # The scripted nurses answered in their own names, marked as simulated
    assert [(name, p["source"]) for name, p in _rows(AuditAction.OFFER_REJECTED)] == [
        ("202", "SIMULATED")
    ]
    assert [(name, p["source"]) for name, p in _rows(AuditAction.OFFER_ACCEPTED)] == [
        ("201", "SIMULATED")
    ]


def test_a_cross_ward_run_needs_both_wards_and_reports_another_ward(client: TestClient) -> None:
    run = _start(client, "cross_ward")

    _play(client, 6, side="DESTINATION")
    kpi = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]

    assert kpi["from_other_ward"] is True
    assert kpi["time_to_fill_s"] is not None
    (transferred,) = _rows(AuditAction.ASSIGNMENT_TRANSFERRED)
    assert transferred[1]["staff_id"] == 301
    # The scripted Medicine head nurse decided the source side, the tester the destination
    decisions = _rows(AuditAction.APPROVAL_WARD_APPROVED) + _rows(AuditAction.APPROVAL_APPROVED)
    assert {name for name, _ in decisions} == {"900", "902"}
    assert [p.get("source") for name, p in decisions if name == "902"] == ["SIMULATED"]


def test_while_a_run_is_open_the_buttons_that_would_spoil_it_are_refused(
    client: TestClient,
) -> None:
    run = _start(client)
    with SessionLocal() as db:
        rows_before = db.scalar(select(func.count()).select_from(AuditLog))

    for path in ("/demo/reset", "/demo/clock/freeze", "/demo/clock/unfreeze"):
        refused = client.post(path)
        assert refused.status_code == 409, path
        assert f"Test run {run['test_run_id']} is in progress" in refused.json()["detail"]
    another = client.post("/demo/test-runs", json={"tester_code": "T02", "scenario": "golden"})
    assert another.status_code == 409

    assert clock.mode() == clock.ClockMode.SCENARIO
    assert clock.test_run_id() == run["test_run_id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog)) == rows_before


def test_abort_closes_without_kpi_and_lets_the_demo_go_on(client: TestClient) -> None:
    run = _start(client)
    run_id = run["test_run_id"]

    aborted = client.post(f"/demo/test-runs/{run_id}/abort", json={"reason": "tester left"})

    assert aborted.json()["result"] == {"invalid": True, "reason": "tester left"}
    assert clock.mode() == clock.ClockMode.FROZEN
    assert client.post(f"/demo/test-runs/{run_id}/abort").status_code == 409
    assert client.post(f"/demo/test-runs/{run_id}/finish").status_code == 409
    assert client.post("/demo/test-runs/999999/finish").status_code == 404
    assert client.post("/demo/reset").status_code == 200
    (listed,) = client.get("/demo/test-runs").json()
    assert listed["invalid"] is True and listed["kpi"] is None


def test_an_abort_without_a_body_says_aborted(client: TestClient) -> None:
    run = _start(client)

    aborted = client.post(f"/demo/test-runs/{run['test_run_id']}/abort")

    assert aborted.json()["result"] == {"invalid": True, "reason": "ABORTED"}


def test_a_run_whose_clock_was_lost_closes_as_clock_lost(client: TestClient) -> None:
    first = _start(client)
    clock.reset()  # what an API restart does to the scenario clock

    # Still open in the database, so still guarded
    assert client.post("/demo/reset").status_code == 409
    finished = client.post(f"/demo/test-runs/{first['test_run_id']}/finish")

    assert finished.json()["result"] == {"invalid": True, "reason": "CLOCK_LOST"}
    second = _start(client)
    assert second["test_run_id"] > first["test_run_id"]


def test_results_survive_the_next_run_and_reach_the_csv(client: TestClient) -> None:
    first = _start(client)
    _play(client, 3)
    stored = client.post(f"/demo/test-runs/{first['test_run_id']}/finish").json()["result"]

    second = _start(client, tester_code="T02")

    runs = client.get("/demo/test-runs").json()
    assert [run["test_run_id"] for run in runs] == [first["test_run_id"], second["test_run_id"]]
    assert runs[0]["kpi"]["time_to_fill_s"] == stored["time_to_fill_s"]
    assert runs[1]["open"] is True and runs[1]["elapsed_seconds"] >= 0
    lines = client.get("/demo/test-runs.csv").text.splitlines()
    assert lines[0].split(",") == list(test_run_service.CSV_COLUMNS)
    assert len(lines) == 2 and lines[1].startswith(f"{first['test_run_id']},T01,golden,")


def test_without_simulated_people_nobody_answers(client: TestClient) -> None:
    _start(client, auto_nurses=False)

    _play(client, 3)

    assert _rows(AuditAction.OFFER_ACCEPTED) == []
    assert _rows(AuditAction.OFFER_REJECTED) == []


def test_every_run_row_is_a_test_run_row() -> None:
    """The reset keeps rows by entity type: every action of a run must carry it."""
    client = TestClient(app)
    try:
        run = _start(client)
        client.post("/demo/clock/advance", json={"seconds": 60})
        client.post(f"/demo/test-runs/{run['test_run_id']}/abort")
    finally:
        clock.reset()
    run_actions = (
        AuditAction.TEST_RUN_STARTED,
        AuditAction.TEST_RUN_CLOCK_ADVANCED,
        AuditAction.TEST_RUN_FINISHED,
    )
    with SessionLocal() as db:
        found = db.execute(
            select(AuditLog.action, AuditLog.entity_type).where(AuditLog.action.in_(run_actions))
        ).all()
    assert {action for action, _ in found} == set(run_actions)
    types = {entity_type for _, entity_type in found}
    assert types == {EntityType.TEST_RUN}


@pytest.mark.parametrize("code", ["", "Somchai Jaidee", "T" * 17, "ทดสอบ"])
def test_the_tester_is_a_code_never_a_name(client: TestClient, code: str) -> None:
    answer = client.post("/demo/test-runs", json={"tester_code": code, "scenario": "golden"})

    assert answer.status_code == 422
    with SessionLocal() as db:
        assert test_run_service.open_run_id(db) is None


def test_cross_ward_runs_one_after_another(client: TestClient) -> None:
    """Review of #143: the scenario's own person (303) keeps their subject across the
    reset of the next run, so a second run starts."""
    first = _start(client, "cross_ward")
    client.post(f"/demo/test-runs/{first['test_run_id']}/abort")

    second = _start(client, "cross_ward")
    _play(client, 6, side="DESTINATION")
    kpi = client.post(f"/demo/test-runs/{second['test_run_id']}/finish").json()["result"]

    assert kpi["from_other_ward"] is True


def test_with_the_large_profile_the_scenario_stays_the_same(client: TestClient) -> None:
    """Review of #143: the profile's wards are paused for the run, so only the scripted
    people are candidates, each needs both wards, and the same playback fills."""
    reset_demo()
    with SessionLocal() as db:
        auth_service.hold_auth_gate(db)
        generate(db, clock.now())
        db.commit()

    run = _start(client, "cross_ward")

    with SessionLocal() as db:
        items = list(
            db.scalars(
                select(CandidateItem)
                .where(CandidateItem.plan_id.is_not(None))
                .order_by(CandidateItem.id)
            )
        )
        assert items and all(item.staff_id < STAFF_BASE for item in items)
        for item in items:
            assert set(approval_wards.required_wards(db, item)) == {
                ApprovalSide.DESTINATION,
                ApprovalSide.SOURCE,
            }
    _play(client, 6, side="DESTINATION")
    kpi = client.post(f"/demo/test-runs/{run['test_run_id']}/finish").json()["result"]
    assert kpi["time_to_fill_s"] is not None and kpi["from_other_ward"] is True

    # A plain reset brings the profile back as it was
    assert client.post("/demo/reset").status_code == 200
    with SessionLocal() as db:
        paused = db.scalar(
            select(func.count()).select_from(Ward).where(Ward.id > WARD_BASE, ~Ward.is_active)
        )
        assert paused == 0


def test_a_start_that_fails_after_the_run_is_written_closes_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(db: object) -> None:
        raise RuntimeError("job round failed")

    monkeypatch.setattr(test_run_service.job_service, "run_due_work", broken)
    with pytest.raises(RuntimeError, match="job round failed"):
        client.post("/demo/test-runs", json={"tester_code": "T01", "scenario": "golden"})
    monkeypatch.undo()

    (failed,) = client.get("/demo/test-runs").json()
    assert failed["open"] is False
    assert (failed["invalid"], failed["reason"]) == (True, "START_FAILED")
    assert clock.mode() == clock.ClockMode.FROZEN
    _start(client)


def test_the_csv_never_hands_a_formula_to_a_spreadsheet(client: TestClient) -> None:
    run = _start(client, tester_code="-T1")
    client.post(f"/demo/test-runs/{run['test_run_id']}/abort", json={"reason": '=HYPERLINK("x")'})

    (row,) = client.get("/demo/test-runs.csv").text.splitlines()[1:]

    assert ",'-T1," in row
    assert "'=HYPERLINK" in row
    assert test_run_service.csv_cell(12.5) == 12.5
    assert test_run_service.csv_cell("@x") == "'@x"


def test_an_advance_after_the_clock_left_its_mode_is_a_conflict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of #143: unfrozen between the mode check and the move: 409, not 500."""
    assert client.post("/demo/reset").status_code == 200

    def unfrozen(delta: object) -> None:
        raise RuntimeError("clock follows real time")

    monkeypatch.setattr(clock, "advance", unfrozen)
    answer = client.post("/demo/clock/advance", json={"seconds": 60})

    assert answer.status_code == 409
