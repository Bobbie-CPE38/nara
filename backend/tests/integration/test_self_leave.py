"""Own leave and the Demo event adapter (docs/workflow.md 6.33.3-4, round 6 PR AU2).

POST /me/unavailability reports the signed-in user's own leave with the STAFF_UNAVAILABLE
flow as it is: no approval of the leave, the same merge window, dedup and roster rules.
POST /demo/events is the Demo control's way to simulate events now that POST /events
refuses web accounts: SYSTEM actor, payload.source SIMULATED, no session.

ICU night shift (1): 105 and 101 are rostered on it, 301 (Medicine) is not.
"""

import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api import rate_limit
from app.api.dependencies import get_db
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    AuditLog,
    CandidateOutreach,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import ActorName, AuditAction
from app.main import app
from app.seed import load
from app.services import actor_service, auth_service

NIGHT_SHIFT = 1
PASSWORD = "self leave test password"
ORIGIN = settings.cors_origins[0]
WRITTEN = (StaffingEvent, StaffUnavailability, StaffingCase, AuditLog, CandidateOutreach)

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture(autouse=True)
def session_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "auth_mode", "session")
    rate_limit.limiter.clear()
    yield
    rate_limit.limiter.clear()


def _counts(db: Session) -> list[int]:
    db.expire_all()
    return [db.scalar(select(func.count()).select_from(model)) or 0 for model in WRITTEN]


@pytest.fixture
def db(production_seeded: Session) -> Session:
    for staff_id in (101, 105, 301, 900, 950):
        auth_service.create_account(
            production_seeded, staff_id, PASSWORD, must_change_password=False
        )
    production_seeded.commit()
    return production_seeded


@pytest.fixture
def anonymous(db: Session) -> Iterator[TestClient]:
    def request_db() -> Iterator[Session]:
        with Session(
            bind=db.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            yield session

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def as_(anonymous: TestClient) -> Callable[[int], TestClient]:
    def client_of(staff_id: int) -> TestClient:
        client = TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN})
        response = client.post("/auth/login", json={"staff_id": staff_id, "password": PASSWORD})
        assert response.status_code == 200
        return client

    return client_of


# --------------------------------------------------------------------------- #
# POST /me/unavailability
# --------------------------------------------------------------------------- #
def test_own_leave_runs_the_leave_flow_as_the_user(
    as_: Callable[[int], TestClient], db: Session
) -> None:
    response = as_(105).post("/me/unavailability", json={"shift_id": NIGHT_SHIFT})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"event_id", "event_status", "case_id", "case_status"}
    db.expire_all()
    event = db.get(StaffingEvent, body["event_id"])
    assert event is not None
    assert (event.staff_id, event.shift_id, event.payload) == (105, NIGHT_SHIFT, {})
    received = db.scalars(
        select(AuditLog).where(
            AuditLog.event_id == event.id, AuditLog.action == AuditAction.EVENT_RECEIVED
        )
    ).one()
    # The user's own actor, from the session; not the SYSTEM actor of the Demo adapter
    assert received.actor_id == actor_service.user_id(db, 105)


@pytest.mark.parametrize(
    ("staff_id", "body", "status_code"),
    [
        (301, {"shift_id": NIGHT_SHIFT}, 403),  # no roster row in the shift
        (105, {"shift_id": 999999}, 404),
        (105, {"shift_id": NIGHT_SHIFT, "staff_id": 101}, 422),  # someone else
        (105, {"shift_id": NIGHT_SHIFT, "event_type": "PATIENT_SURGE"}, 422),
        (105, {"shift_id": NIGHT_SHIFT, "reason": "sick"}, 422),  # no free text
        (105, {"shift_id": NIGHT_SHIFT, "end_at": "2026-10-10T21:00:00"}, 422),  # naive
        (105, {}, 422),
    ],
)
def test_refused_leave_writes_nothing(
    as_: Callable[[int], TestClient],
    db: Session,
    staff_id: int,
    body: dict[str, Any],
    status_code: int,
) -> None:
    before = _counts(db)

    response = as_(staff_id).post("/me/unavailability", json=body)

    assert response.status_code == status_code
    if status_code == 403:
        assert response.json() == {"detail": "AUTH_FORBIDDEN"}
    assert _counts(db) == before


def test_anonymous_leave_is_401(anonymous: TestClient, db: Session) -> None:
    before = _counts(db)
    response = anonymous.post(
        "/me/unavailability", json={"shift_id": NIGHT_SHIFT}, headers={"X-Demo-User": "105"}
    )
    assert response.status_code == 401
    assert _counts(db) == before


def test_repeated_leave_is_refused_like_no_row_and_opens_no_second_case(
    as_: Callable[[int], TestClient], db: Session
) -> None:
    client = as_(105)
    first = client.post("/me/unavailability", json={"shift_id": NIGHT_SHIFT})
    after_first = _counts(db)

    second = client.post("/me/unavailability", json={"shift_id": NIGHT_SHIFT})

    assert first.status_code == 201
    # The first report already cancelled the row. The answer is the one a person with no row
    # gets (403), decided from the state the intake saw, so it tells nothing about the past
    assert second.status_code == 403
    assert second.json() == {"detail": "AUTH_FORBIDDEN"}
    assert _counts(db) == after_first
    assert db.scalar(select(func.count()).select_from(StaffingCase)) == 1
    assert db.scalar(select(func.count()).select_from(StaffUnavailability)) == 1


def test_own_leave_also_works_in_demo_mode(
    anonymous: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "demo")
    response = anonymous.post(
        "/me/unavailability", json={"shift_id": NIGHT_SHIFT}, headers={"X-Demo-User": "105"}
    )
    assert response.status_code == 201


# Two real connections: the same own leave twice at once
@pytest.fixture
def committed(frozen_clock: datetime) -> Iterator[None]:
    with SessionLocal.begin() as session:
        load(session)
        auth_service.create_account(session, 105, PASSWORD, must_change_password=False)
    try:
        yield
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_same_own_leave_twice_at_once_opens_one_case(committed: None) -> None:
    clients = []
    for _ in range(2):
        client = TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN})
        assert (
            client.post("/auth/login", json={"staff_id": 105, "password": PASSWORD}).status_code
            == 200
        )
        clients.append(client)
    start = threading.Barrier(2, timeout=10)
    statuses: list[int] = []

    def report(client: TestClient) -> None:
        start.wait()
        statuses.append(
            client.post("/me/unavailability", json={"shift_id": NIGHT_SHIFT}).status_code
        )

    threads = [threading.Thread(target=report, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(statuses) == [201, 403]
    with SessionLocal() as session:
        for model, expected in (
            (StaffingEvent, 1),
            (StaffUnavailability, 1),
            (StaffingCase, 1),
        ):
            assert session.scalar(select(func.count()).select_from(model)) == expected
        received = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.EVENT_RECEIVED)
        )
        assert received == 1
    for client in clients:
        client.close()


# --------------------------------------------------------------------------- #
# POST /demo/events
# --------------------------------------------------------------------------- #
def test_demo_event_is_recorded_by_system_as_simulated(
    as_: Callable[[int], TestClient], db: Session
) -> None:
    response = as_(900).post(
        "/demo/events",
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT, "reporter_staff_id": 105},
    )

    assert response.status_code == 201
    db.expire_all()
    event = db.get(StaffingEvent, response.json()["event_id"])
    assert event is not None
    assert event.staff_id == 105
    assert event.payload == {"source": "SIMULATED"}
    received = db.scalars(
        select(AuditLog).where(
            AuditLog.event_id == event.id, AuditLog.action == AuditAction.EVENT_RECEIVED
        )
    ).one()
    assert received.actor_id == actor_service.component_id(db, ActorName.SYSTEM)


def test_demo_head_nurse_event_keeps_the_reporter(
    as_: Callable[[int], TestClient], db: Session
) -> None:
    response = as_(900).post(
        "/demo/events",
        json={
            "event_type": "PATIENT_SURGE",
            "shift_id": NIGHT_SHIFT,
            "patient_count": 12,
            "reporter_staff_id": 900,
        },
    )

    assert response.status_code == 201
    db.expire_all()
    event = db.get(StaffingEvent, response.json()["event_id"])
    assert event is not None
    assert event.payload["source"] == "SIMULATED"
    assert event.payload["reported_by"] == 900


@pytest.mark.parametrize(
    ("body", "status_code"),
    [
        (
            {
                "event_type": "PATIENT_SURGE",
                "shift_id": NIGHT_SHIFT,
                "patient_count": 9,
                "reporter_staff_id": 101,
            },
            403,
        ),
        (
            {
                "event_type": "STAFF_UNAVAILABLE",
                "shift_id": NIGHT_SHIFT,
                "reporter_staff_id": 999999,
            },
            404,
        ),
        ({"event_type": "STAFF_UNAVAILABLE", "shift_id": 999999, "reporter_staff_id": 105}, 404),
        (
            {"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT, "reporter_staff_id": 301},
            409,
        ),
        ({"event_type": "PATIENT_SURGE", "shift_id": NIGHT_SHIFT, "reporter_staff_id": 900}, 422),
        ({"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT}, 422),
    ],
)
def test_refused_demo_events_write_nothing(
    as_: Callable[[int], TestClient], db: Session, body: dict[str, Any], status_code: int
) -> None:
    before = _counts(db)

    response = as_(900).post("/demo/events", json=body)

    assert response.status_code == status_code
    assert _counts(db) == before


def test_demo_events_need_an_allowed_origin_in_session_mode(
    as_: Callable[[int], TestClient], db: Session
) -> None:
    before = _counts(db)

    response = as_(900).post(
        "/demo/events",
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT, "reporter_staff_id": 105},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    assert _counts(db) == before


def test_system_job_still_runs_in_session_mode(
    anonymous: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "internal_job_secret", "a test job secret")

    response = anonymous.post(
        "/internal/merge-windows/close-due",
        headers={"X-Internal-Secret": "a test job secret", "Origin": ""},
    )

    assert response.status_code == 200
