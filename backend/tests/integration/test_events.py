"""POST /events on the seeded Golden Case (docs/workflow.md, section 3)."""

import contextlib
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.base import Base
from app.db.models import (
    Actor,
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorName,
    AuditAction,
    AvailabilityReason,
    CaseStatus,
    EntityType,
    EventStatus,
    RosterStatus,
    StaffStatus,
)
from app.main import app
from app.seed import load
from app.services import gap_service
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult

NIGHT_SHIFT, DAY_SHIFT = 1, 2
LEAVE = {"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT}
AS_105 = {"X-Demo-User": "105"}
WRITTEN_TABLES = (StaffingEvent, StaffUnavailability, StaffingCase, AuditLog)

# Event intake ends when it hands the case to the orchestrator. What the steps
# after it write is tested with those steps, so here each one is a stub that
# only moves the case along the golden path. Without this, every step 4 handler
# that becomes real would change what these tests see.
pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _row_counts(db: Session) -> list[int | None]:
    return [db.scalar(select(func.count()).select_from(model)) for model in WRITTEN_TABLES]


def _roster_status(db: Session, staff_id: int, shift_id: int) -> RosterStatus:
    db.expire_all()
    return db.scalars(
        select(RosterAssignment.status).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


def _timeline(db: Session, case_id: int) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.id))
    )


# --------------------------------------------------------------------------- #
# Golden path: 105 reports leave for the night shift
# --------------------------------------------------------------------------- #
def test_leave_that_opens_a_gap_creates_a_case_and_runs_it(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/events", headers=AS_105, json=LEAVE)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"event_id", "event_status", "case_id", "case_status"}
    assert body["event_status"] == "PROCESSED"
    assert body["case_status"] == "WAITING_RESPONSE"
    seeded.expire_all()
    event = seeded.get(StaffingEvent, body["event_id"])
    case = seeded.get(StaffingCase, body["case_id"])
    assert event is not None
    assert case is not None
    assert (event.staff_id, event.shift_id, event.status) == (
        105,
        NIGHT_SHIFT,
        EventStatus.PROCESSED,
    )
    assert event.payload == {}
    assert (case.event_id, case.shift_id) == (event.id, NIGHT_SHIFT)


def test_leave_cancels_the_roster_row_and_records_the_unavailability(
    client: TestClient, seeded: Session
) -> None:
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None

    client.post("/events", headers=AS_105, json=LEAVE)

    assert _roster_status(seeded, 105, NIGHT_SHIFT) is RosterStatus.CANCELLED
    assert _roster_status(seeded, 104, NIGHT_SHIFT) is RosterStatus.ASSIGNED
    unavailability = seeded.scalars(select(StaffUnavailability)).one()
    assert unavailability.staff_id == 105
    assert unavailability.reason is AvailabilityReason.UNPLANNED_LEAVE
    assert unavailability.start_at == shift.start_at
    assert unavailability.end_at == shift.end_at
    # Leave is not an employment status (database-schema.md)
    staff = seeded.get(Staff, 105)
    assert staff is not None
    assert staff.status is StaffStatus.ACTIVE


def test_case_must_be_replaced_by_the_start_of_the_shift(
    client: TestClient, seeded: Session
) -> None:
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None

    body = client.post("/events", headers=AS_105, json=LEAVE).json()

    case = seeded.get(StaffingCase, body["case_id"])
    assert case is not None
    assert case.required_replacement_time == shift.start_at


def test_timeline_starts_with_the_golden_path_audit_rows(
    client: TestClient, seeded: Session
) -> None:
    body = client.post("/events", headers=AS_105, json=LEAVE).json()

    rows = _timeline(seeded, body["case_id"])
    assert [row.action for row in rows[:3]] == [
        AuditAction.EVENT_RECEIVED,
        AuditAction.UNAVAILABILITY_CREATED,
        AuditAction.CASE_OPENED,
    ]
    assert {row.action for row in rows[3:]} == {AuditAction.CASE_STATUS_CHANGED}
    received, unavailable, opened = rows[:3]
    user_actor = seeded.scalar(select(Actor.id).where(Actor.staff_id == 105))
    orchestrator_actor = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.WORKFLOW_ORCHESTRATOR.value)
    )
    assert (received.actor_id, unavailable.actor_id, opened.actor_id) == (
        user_actor,
        user_actor,
        orchestrator_actor,
    )
    assert received.entity_type is EntityType.STAFFING_EVENTS
    assert received.entity_id == body["event_id"]
    assert received.payload == {
        "event_type": "STAFF_UNAVAILABLE",
        "shift_id": NIGHT_SHIFT,
        "staff_id": 105,
    }
    assert unavailable.entity_type is EntityType.STAFF_UNAVAILABILITY
    assert set(unavailable.payload) == {
        "unavailability_id",
        "staff_id",
        "reason",
        "start_at",
        "end_at",
    }
    assert unavailable.payload["reason"] == "UNPLANNED_LEAVE"
    # Times in a payload are ISO strings, never datetime objects
    assert datetime.fromisoformat(unavailable.payload["start_at"]).utcoffset() is not None
    assert opened.entity_type is EntityType.STAFFING_CASES
    assert opened.entity_id == body["case_id"]
    assert opened.payload == {
        "event_id": body["event_id"],
        "shift_id": NIGHT_SHIFT,
        "headcount_gap": 1,
    }


def test_audit_payload_times_are_plus_seven_after_a_database_round_trip(
    client: TestClient, seeded: Session
) -> None:
    """PostgreSQL returns the shift times in UTC. Without expire_all() the service
    would copy the +07:00 objects the seed created, and the test would prove nothing."""
    seeded.expire_all()

    body = client.post("/events", headers=AS_105, json=LEAVE).json()

    unavailable = _timeline(seeded, body["case_id"])[1]
    assert unavailable.action is AuditAction.UNAVAILABILITY_CREATED
    assert unavailable.payload["start_at"] == "2026-10-09T23:00:00+07:00"
    assert unavailable.payload["end_at"] == "2026-10-10T07:00:00+07:00"


def test_return_time_ends_the_unavailability_early(client: TestClient, seeded: Session) -> None:
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    back_at = shift.start_at + timedelta(hours=4)

    response = client.post("/events", headers=AS_105, json=LEAVE | {"end_at": back_at.isoformat()})

    assert response.status_code == 201
    assert seeded.scalars(select(StaffUnavailability.end_at)).one() == back_at


def test_workflow_failure_is_a_recorded_result_not_an_http_error(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_optimize(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("solver crashed")

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.OPTIMIZING, failing_optimize)

    response = client.post("/events", headers=AS_105, json=LEAVE)

    assert response.status_code == 201
    body = response.json()
    assert body["event_status"] == "PROCESSED"
    assert body["case_status"] == "FAILED"
    # The event, the leave and the case survive the failed round
    assert _roster_status(seeded, 105, NIGHT_SHIFT) is RosterStatus.CANCELLED
    actions = [row.action for row in _timeline(seeded, body["case_id"])]
    assert actions[:3] == [
        AuditAction.EVENT_RECEIVED,
        AuditAction.UNAVAILABILITY_CREATED,
        AuditAction.CASE_OPENED,
    ]
    assert actions[-1] is AuditAction.WORKFLOW_FAILED


# --------------------------------------------------------------------------- #
# Requests that are rejected: nothing may be written
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("headers", "body", "status_code"),
    [
        ({}, LEAVE, 401),
        (AS_105, LEAVE | {"shift_id": 999}, 404),
        # 105 is not on the day shift
        (AS_105, LEAVE | {"shift_id": DAY_SHIFT}, 409),
        # 900 (head nurse) is on no shift
        ({"X-Demo-User": "900"}, LEAVE, 409),
        (AS_105, LEAVE | {"event_type": "PATIENT_SURGE"}, 422),
        (AS_105, LEAVE | {"event_type": "ASSIGNMENT_CANCELLED"}, 422),
        (AS_105, LEAVE | {"event_type": "NOT_AN_EVENT"}, 422),
        (AS_105, LEAVE | {"shift_id": 0}, 422),
        # One above PostgreSQL bigint: must be rejected before the database sees it
        (AS_105, LEAVE | {"shift_id": 2**63}, 422),
        (AS_105, {"event_type": "STAFF_UNAVAILABLE"}, 422),
        # A return time without a timezone
        (AS_105, LEAVE | {"end_at": "2026-10-10T03:00:00"}, 422),
        # A return time before the shift starts
        (AS_105, LEAVE | {"end_at": "2026-10-09T22:00:00+07:00"}, 422),
    ],
    ids=[
        "no_header",
        "unknown_shift",
        "not_on_that_shift",
        "not_on_any_shift",
        "patient_surge",
        "assignment_cancelled",
        "unknown_event_type",
        "shift_id_zero",
        "shift_id_above_bigint",
        "missing_shift_id",
        "naive_end_at",
        "end_at_before_shift",
    ],
)
def test_rejected_request_writes_nothing(
    client: TestClient,
    seeded: Session,
    headers: dict[str, str],
    body: dict[str, Any],
    status_code: int,
) -> None:
    before = _row_counts(seeded)

    response = client.post("/events", headers=headers, json=body)

    assert response.status_code == status_code
    assert _row_counts(seeded) == before
    assert _roster_status(seeded, 105, NIGHT_SHIFT) is RosterStatus.ASSIGNED


def test_repeated_leave_report_is_409_and_opens_no_second_case(
    client: TestClient, seeded: Session
) -> None:
    first = client.post("/events", headers=AS_105, json=LEAVE)
    after_first = _row_counts(seeded)

    second = client.post("/events", headers=AS_105, json=LEAVE)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"detail": "Staff 105 has no assigned roster row in shift 1"}
    assert _row_counts(seeded) == after_first
    assert seeded.scalar(select(func.count()).select_from(StaffingCase)) == 1


# --------------------------------------------------------------------------- #
# Two real connections: the same leave reported twice at once
# --------------------------------------------------------------------------- #
@pytest.fixture
def committed_seed(frozen_clock: datetime) -> Iterator[None]:
    """The Golden Case committed for real, so separate connections see it."""
    with SessionLocal.begin() as db:
        load(db)
    try:
        yield
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_same_leave_reported_twice_at_once_opens_one_case(committed_seed: None) -> None:
    """The shift lock lets one request through; the other then finds the roster row cancelled."""
    start = threading.Barrier(2, timeout=10)
    statuses: list[int] = []

    def report_leave() -> None:
        with TestClient(app) as real_client:
            start.wait()
            statuses.append(real_client.post("/events", headers=AS_105, json=LEAVE).status_code)

    threads = [threading.Thread(target=report_leave) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(statuses) == [201, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StaffingEvent)) == 1
        assert db.scalar(select(func.count()).select_from(StaffUnavailability)) == 1
        assert db.scalar(select(func.count()).select_from(StaffingCase)) == 1


def test_largest_bigint_shift_id_reaches_the_lookup(client: TestClient) -> None:
    """The upper bound is the bigint maximum itself, which is a valid (unknown) shift ID."""
    response = client.post("/events", headers=AS_105, json=LEAVE | {"shift_id": 2**63 - 1})

    assert response.status_code == 404


def test_two_people_leaving_the_same_shift_at_once_do_not_hide_the_gap(
    committed_seed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """202 and 203 are the whole day shift, which needs one nurse.

    Without a lock on the shift, each request cancels its own roster row, still
    sees the other person as ASSIGNED (that cancellation is not committed yet),
    and marks its event IGNORED. The shift ends up empty with no case.

    The barrier holds both requests just before the gap check, which is the
    moment they would both read the stale roster. With the shift lock only one
    request gets that far at a time, so the barrier times out and lets it go on.
    """
    both_cancelled = threading.Barrier(2, timeout=10)
    real_assess = gap_service.assess_shift

    def assess_when_both_are_ready(db: Session, shift: Shift) -> gap_service.ShiftAssessment:
        with contextlib.suppress(threading.BrokenBarrierError):
            both_cancelled.wait(timeout=1.5)
        return real_assess(db, shift)

    monkeypatch.setattr(gap_service, "assess_shift", assess_when_both_are_ready)
    start = threading.Barrier(2, timeout=10)
    answers: dict[int, tuple[int, dict[str, Any]]] = {}

    def report_leave(staff_id: int) -> None:
        with TestClient(app) as real_client:
            start.wait()
            response = real_client.post(
                "/events",
                headers={"X-Demo-User": str(staff_id)},
                json=LEAVE | {"shift_id": DAY_SHIFT},
            )
            answers[staff_id] = (response.status_code, response.json())

    threads = [threading.Thread(target=report_leave, args=(staff_id,)) for staff_id in (202, 203)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert [status_code for status_code, _ in answers.values()] == [201, 201]
    # The first one leaves the shift covered. The second one must see it empty
    assert sorted(body["event_status"] for _, body in answers.values()) == ["IGNORED", "PROCESSED"]
    with SessionLocal() as db:
        roster = set(
            db.scalars(
                select(RosterAssignment.status).where(RosterAssignment.shift_id == DAY_SHIFT)
            )
        )
        assert roster == {RosterStatus.CANCELLED}
        assert db.scalar(select(func.count()).select_from(StaffingCase)) == 1
