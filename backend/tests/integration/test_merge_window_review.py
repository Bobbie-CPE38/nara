"""Guards added after the review of PR M (docs/workflow.md, sections 3.4, 3.5 and 3.8)."""

import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.constants import HEAD_NURSE_ROLE, MAX_EVENT_REASON_LENGTH
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
)
from app.domain.enums import EventStatus, EventType, RosterStatus
from app.jobs import ticker
from app.main import app
from app.services import approval_service, event_service
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT = 1, 2
AS_HEAD_NURSE = {"X-Demo-User": "900"}

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _count(db: Session, model: type) -> int:
    result = db.scalar(select(func.count()).select_from(model))
    assert result is not None
    return result


# --------------------------------------------------------------------------- #
# processed_at is empty exactly while the event is RECEIVED
# --------------------------------------------------------------------------- #
def _event(status: EventStatus, *, closed: bool) -> StaffingEvent:
    return StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=105,
        status=status,
        processed_at=DEMO_NOW if closed else None,
    )


@pytest.mark.parametrize(
    ("status", "closed"),
    [
        (EventStatus.RECEIVED, True),
        (EventStatus.PROCESSED, False),
        (EventStatus.IGNORED, False),
    ],
)
def test_database_rejects_a_close_time_that_does_not_fit_the_status(
    seeded: Session, status: EventStatus, closed: bool
) -> None:
    seeded.add(_event(status, closed=closed))

    with pytest.raises(IntegrityError, match="ck_staffing_events_processed_at_matches_status"):
        seeded.flush()


@pytest.mark.parametrize(
    ("status", "closed"),
    [
        (EventStatus.RECEIVED, False),
        (EventStatus.PROCESSED, True),
        (EventStatus.IGNORED, True),
    ],
)
def test_database_accepts_a_close_time_that_fits_the_status(
    seeded: Session, status: EventStatus, closed: bool
) -> None:
    seeded.add(_event(status, closed=closed))

    seeded.flush()


# --------------------------------------------------------------------------- #
# A shift without a requirement takes no event
# --------------------------------------------------------------------------- #
def _remove_requirement(db: Session, shift_id: int) -> None:
    requirement_ids = select(StaffingRequirement.id).where(StaffingRequirement.shift_id == shift_id)
    for child in (StaffingRequirementRole, StaffingRequirementSkill):
        db.execute(delete(child).where(child.staffing_requirement_id.in_(requirement_ids)))
    db.execute(delete(StaffingRequirement).where(StaffingRequirement.shift_id == shift_id))
    db.flush()


@pytest.mark.parametrize("window", [0, 600])
@pytest.mark.parametrize(
    ("staff_id", "body"),
    [
        (203, {"event_type": "STAFF_UNAVAILABLE"}),
        (900, {"event_type": "ASSIGNMENT_CANCELLED", "staff_id": 203, "reason": "Moved"}),
        (900, {"event_type": "PATIENT_SURGE", "patient_count": 12}),
        (
            900,
            {"event_type": "REQUIREMENT_CHANGED", "roles": [{"role_id": 1, "required_count": 2}]},
        ),
    ],
    ids=["leave", "cancellation", "patient_surge", "requirement_change"],
)
def test_shift_without_a_requirement_refuses_every_event_type(
    client: TestClient, seeded: Session, window: int, staff_id: int, body: dict[str, Any]
) -> None:
    """Its window could never close, so the event would block the shift for good.

    Before the guard this was 201 RECEIVED with a window, and 500 without one.
    """
    shift = seeded.get(Shift, DAY_SHIFT)
    assert shift is not None
    shift.merge_window_seconds = window
    _remove_requirement(seeded, DAY_SHIFT)

    response = client.post(
        "/events", headers={"X-Demo-User": str(staff_id)}, json=body | {"shift_id": DAY_SHIFT}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "No staffing requirement for shift 2"}
    assert _count(seeded, StaffingEvent) == 0
    assert _count(seeded, AuditLog) == 0
    assert _count(seeded, StaffingCase) == 0
    roster = seeded.scalars(
        select(RosterAssignment.status).where(RosterAssignment.shift_id == DAY_SHIFT)
    )
    assert set(roster) == {RosterStatus.ASSIGNED}


def test_unknown_shift_is_still_404_not_409(client: TestClient) -> None:
    response = client.post(
        "/events",
        headers=AS_HEAD_NURSE,
        json={"event_type": "PATIENT_SURGE", "shift_id": 999, "patient_count": 1},
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# The reason of a cancellation has a length limit
# --------------------------------------------------------------------------- #
def _cancel(client: TestClient, reason: str) -> Any:
    return client.post(
        "/events",
        headers=AS_HEAD_NURSE,
        json={
            "event_type": "ASSIGNMENT_CANCELLED",
            "shift_id": NIGHT_SHIFT,
            "staff_id": 104,
            "reason": reason,
        },
    )


def test_reason_at_the_limit_is_stored_whole(client: TestClient, seeded: Session) -> None:
    reason = "x" * MAX_EVENT_REASON_LENGTH

    response = _cancel(client, reason)

    assert response.status_code == 201
    event = seeded.get(StaffingEvent, response.json()["event_id"])
    assert event is not None
    assert event.payload["reason"] == reason


def test_reason_above_the_limit_is_rejected_and_writes_nothing(
    client: TestClient, seeded: Session
) -> None:
    response = _cancel(client, "x" * (MAX_EVENT_REASON_LENGTH + 1))

    assert response.status_code == 422
    assert _count(seeded, StaffingEvent) == 0
    assert _count(seeded, AuditLog) == 0


def test_service_applies_the_same_limit_without_the_route(seeded: Session) -> None:
    with pytest.raises(event_service.InvalidEventDetailsError, match="at most 500"):
        event_service.receive_event(
            seeded,
            staff_id=900,
            actor_id=1,
            role_id=2,
            event_type=EventType.ASSIGNMENT_CANCELLED,
            shift_id=NIGHT_SHIFT,
            target_staff_id=104,
            reason="x" * (MAX_EVENT_REASON_LENGTH + 1),
        )


# --------------------------------------------------------------------------- #
# One name for the head nurse role
# --------------------------------------------------------------------------- #
def test_approval_and_event_intake_share_the_head_nurse_role_name() -> None:
    assert approval_service.HEAD_NURSE_ROLE is HEAD_NURSE_ROLE
    assert event_service.HEAD_NURSE_ROLE is HEAD_NURSE_ROLE


# --------------------------------------------------------------------------- #
# The job service survives a backend that goes away
# --------------------------------------------------------------------------- #
def test_ticker_survives_a_connection_closed_without_an_answer() -> None:
    """What a backend restart in the middle of a call looks like: RemoteDisconnected."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    def accept_and_hang_up() -> None:
        connection, _ = server.accept()
        connection.recv(1024)
        connection.close()

    thread = threading.Thread(target=accept_and_hang_up)
    thread.start()
    try:
        port = server.getsockname()[1]
        result = ticker.tick(f"http://127.0.0.1:{port}{ticker.CLOSE_DUE_PATH}", "secret")
    finally:
        thread.join(timeout=10)
        server.close()

    assert result.startswith("backend not reachable: ")


@pytest.mark.parametrize(("value", "seconds"), [("30", 30.0), ("1", 1.0), ("2.5", 2.5)])
def test_ticker_interval_accepts_one_second_or_more(value: str, seconds: float) -> None:
    assert ticker.interval_seconds(value) == seconds


@pytest.mark.parametrize("value", ["0", "-5", "0.5", "", "soon", "nan", "inf"])
def test_ticker_interval_rejects_values_that_would_spin_or_crash(value: str) -> None:
    with pytest.raises(SystemExit, match="JOB_INTERVAL_SECONDS"):
        ticker.interval_seconds(value)
