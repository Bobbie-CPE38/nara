"""Check-in routes and service (docs/workflow.md, section 6.24 and 9.3).

Shift 1 is the ICU night D 23:00 - D+1 07:00 with staff 101-105 REGULAR ASSIGNED.
The clock is frozen, so every test moves it to the moment it checks.
"""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.core.constants import CHECK_IN_EARLIEST_SECONDS, MAX_BIGINT, NO_SHOW_GRACE_SECONDS
from app.db.models import Actor, Attendance, AuditLog, RosterAssignment, Shift
from app.db.session import SessionLocal
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    CheckInSource,
    EntityType,
    RosterStatus,
)
from app.main import app
from app.seed import check_ins, load
from app.services import actor_service, attendance_service, working_time_service
from tests.integration.case_rows import DAY_SHIFT, NIGHT_SHIFT, cancel_roster
from tests.integration.conftest import DEMO_NOW

ME = "/me/attendance/check-in"
DEMO = "/demo/attendance/check-in"
HEADERS = {"X-Demo-User": "101"}
START = DEMO_NOW.replace(hour=23)  # shift 1 starts
END = START + timedelta(hours=8)
DEADLINE = START + timedelta(seconds=NO_SHOW_GRACE_SECONDS)
EARLIEST = START - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)


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
        app.dependency_overrides.pop(get_db, None)


def at(moment: datetime) -> None:
    clock.set_time(moment)


def me(client: TestClient, shift_id: int = NIGHT_SHIFT, staff: str = "101"):
    return client.post(ME, headers={"X-Demo-User": staff}, json={"shift_id": shift_id})


def simulate(client: TestClient, staff_id: int = 101, shift_id: int = NIGHT_SHIFT):
    return client.post(DEMO, json={"staff_id": staff_id, "shift_id": shift_id})


def attendance_rows(db: Session, staff_id: int | None = None) -> list[Attendance]:
    query = select(Attendance).where(Attendance.shift_id.is_not(None))
    if staff_id is not None:
        query = query.where(Attendance.staff_id == staff_id)
    return list(db.scalars(query.order_by(Attendance.id)))


def audit_rows(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.ATTENDANCE_CHECKED_IN)
            .order_by(AuditLog.id)
        )
    )


def roster_of(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> RosterAssignment:
    return db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


# ---- identity -------------------------------------------------------------------------------


def test_me_records_only_the_caller(client: TestClient, production_seeded: Session) -> None:
    at(START + timedelta(minutes=5))
    response = me(client, staff="102")
    assert response.status_code == 200
    assert [row.staff_id for row in attendance_rows(production_seeded)] == [102]


def test_staff_id_in_the_query_is_ignored(client: TestClient, production_seeded: Session) -> None:
    at(START + timedelta(minutes=5))
    response = client.post(
        ME, params={"staff_id": 102}, headers=HEADERS, json={"shift_id": NIGHT_SHIFT}
    )
    assert response.status_code == 200
    assert [row.staff_id for row in attendance_rows(production_seeded)] == [101]


def test_staff_id_in_the_body_is_422_and_records_nothing(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=5))
    response = client.post(ME, headers=HEADERS, json={"shift_id": NIGHT_SHIFT, "staff_id": 102})
    assert response.status_code == 422
    assert attendance_rows(production_seeded) == []
    assert audit_rows(production_seeded) == []


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "999999"}, {"X-Demo-User": "abc"}])
def test_me_without_a_valid_header_is_401(
    client: TestClient, production_seeded: Session, headers: dict[str, str]
) -> None:
    at(START)
    response = client.post(ME, headers=headers, json={"shift_id": NIGHT_SHIFT})
    assert response.status_code == 401
    assert attendance_rows(production_seeded) == []


@pytest.mark.parametrize("shift_id", [0, -1, MAX_BIGINT + 1, "x", None])
def test_shift_id_must_be_a_bounded_positive_integer(client: TestClient, shift_id) -> None:
    response = client.post(ME, headers=HEADERS, json={"shift_id": shift_id})
    assert response.status_code == 422


# ---- source, actor, audit, clock -----------------------------------------------------------


def test_me_audit_has_source_self_the_users_actor_and_all_payload_keys(
    client: TestClient, production_seeded: Session
) -> None:
    now = START + timedelta(minutes=5)
    at(now)
    body = me(client).json()
    (audit,) = audit_rows(production_seeded)
    user_actor = production_seeded.scalars(select(Actor.id).where(Actor.staff_id == 101)).one()
    assert audit.actor_id == user_actor
    assert audit.case_id is None and audit.event_id is None
    assert audit.entity_type == EntityType.ATTENDANCE
    assert audit.entity_id == body["attendance_id"]
    assert audit.payload == {
        "attendance_id": body["attendance_id"],
        "staff_id": 101,
        "shift_id": NIGHT_SHIFT,
        "roster_assignment_id": roster_of(production_seeded, 101).id,
        "check_in_at": now.isoformat(),
        "on_time": True,
        "source": "SELF",
    }


def test_demo_route_records_the_given_staff_as_simulated_by_system(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=5))
    response = simulate(client, 103)
    assert response.status_code == 200
    (row,) = attendance_rows(production_seeded)
    assert row.staff_id == 103
    (audit,) = audit_rows(production_seeded)
    assert audit.payload["source"] == "SIMULATED"
    assert audit.payload["staff_id"] == 103
    assert audit.actor_id == actor_service.component_id(production_seeded, ActorName.SYSTEM)


def test_check_in_at_is_the_frozen_clock_and_the_response_is_plus_seven(
    client: TestClient, production_seeded: Session
) -> None:
    now = START + timedelta(minutes=7, seconds=30)
    at(now)
    body = me(client).json()
    assert body["check_in_at"] == "2026-10-09T23:07:30+07:00"
    assert body["deadline"] == "2026-10-09T23:15:00+07:00"
    assert body["on_time"] is True
    assert body["shift_id"] == NIGHT_SHIFT
    (row,) = attendance_rows(production_seeded)
    assert row.check_in_at == now and row.synced_at == now
    assert row.check_out_at is None and row.work_minutes is None and row.overtime_minutes is None


# ---- repeats -------------------------------------------------------------------------------


def test_repeats_from_me_then_demo_give_one_row_one_audit_and_the_same_answer(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=5))
    first = me(client)
    at(START + timedelta(minutes=40))
    second = me(client)
    third = simulate(client, 101)
    assert first.status_code == second.status_code == third.status_code == 200
    assert first.json() == second.json() == third.json()
    assert len(attendance_rows(production_seeded)) == 1
    assert len(audit_rows(production_seeded)) == 1


def test_repeat_after_the_deadline_keeps_the_first_on_time_answer(client: TestClient) -> None:
    at(START)
    first = me(client).json()
    at(START + timedelta(hours=3))
    assert me(client).json() == first
    assert first["on_time"] is True


def test_repeat_after_the_effective_end_still_returns_the_row(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=1))
    first = me(client).json()
    at(END + timedelta(hours=5))
    response = me(client)
    assert response.status_code == 200
    assert response.json() == first
    assert len(audit_rows(production_seeded)) == 1


def test_repeat_still_answers_after_the_roster_row_was_cancelled(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=1))
    first = me(client).json()
    cancel_roster(production_seeded, 101)
    production_seeded.commit()
    assert me(client).json() == first


def test_check_ins_do_not_change_weekly_overtime(
    client: TestClient, production_seeded: Session
) -> None:
    at(START + timedelta(minutes=5))
    before = working_time_service.capture(production_seeded, [101], captured_at=clock.now())[
        101
    ].values
    me(client)
    me(client)
    after = working_time_service.capture(production_seeded, [101], captured_at=clock.now())[
        101
    ].values
    assert after.overtime_hours == before.overtime_hours


# ---- window --------------------------------------------------------------------------------


def test_exactly_one_hour_before_arrival_is_accepted(client: TestClient) -> None:
    at(EARLIEST)
    response = me(client)
    assert response.status_code == 200
    assert response.json()["on_time"] is True


def test_one_second_earlier_is_422_and_records_nothing(
    client: TestClient, production_seeded: Session
) -> None:
    at(EARLIEST - timedelta(seconds=1))
    response = me(client)
    assert response.status_code == 422
    assert attendance_rows(production_seeded) == []
    assert audit_rows(production_seeded) == []


def test_first_check_in_exactly_at_the_end_is_422(
    client: TestClient, production_seeded: Session
) -> None:
    at(END - timedelta(seconds=1))
    assert me(client, staff="102").status_code == 200
    at(END)
    response = me(client)
    assert response.status_code == 422
    assert [row.staff_id for row in attendance_rows(production_seeded)] == [102]


def test_end_before_the_shift_end_closes_the_window_earlier(
    client: TestClient, production_seeded: Session
) -> None:
    roster_of(production_seeded, 101).actual_end_at = START + timedelta(hours=2)
    production_seeded.commit()
    at(START + timedelta(hours=2))
    assert me(client).status_code == 422
    assert attendance_rows(production_seeded) == []


def test_check_in_after_a_mid_shift_transfer_out_is_422(
    client: TestClient, production_seeded: Session
) -> None:
    roster_of(production_seeded, 101).actual_end_at = START + timedelta(hours=3)
    production_seeded.commit()
    at(START + timedelta(hours=4))
    response = me(client)
    assert response.status_code == 422
    assert attendance_rows(production_seeded) == []


# ---- on time -------------------------------------------------------------------------------


def test_exactly_at_the_deadline_is_on_time(client: TestClient) -> None:
    at(DEADLINE)
    assert me(client).json()["on_time"] is True


def test_one_second_after_the_deadline_is_late_but_still_recorded(
    client: TestClient, production_seeded: Session
) -> None:
    at(DEADLINE + timedelta(seconds=1))
    response = me(client)
    assert response.status_code == 200
    assert response.json()["on_time"] is False
    (audit,) = audit_rows(production_seeded)
    assert audit.payload["on_time"] is False
    assert len(attendance_rows(production_seeded)) == 1


def test_replacement_arrival_is_the_later_of_start_and_creation(
    client: TestClient, production_seeded: Session
) -> None:
    created = START + timedelta(hours=2)
    production_seeded.add(
        RosterAssignment(
            staff_id=201,
            shift_id=NIGHT_SHIFT,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            created_at=created,
        )
    )
    production_seeded.commit()
    at(created + timedelta(minutes=10))
    body = me(client, staff="201").json()
    assert body["deadline"] == (created + timedelta(seconds=NO_SHOW_GRACE_SECONDS)).isoformat()
    assert body["on_time"] is True


def test_regular_row_ignores_created_at(client: TestClient, production_seeded: Session) -> None:
    roster_of(production_seeded, 101).created_at = START + timedelta(hours=2)
    production_seeded.commit()
    at(START + timedelta(minutes=20))
    body = me(client).json()
    assert body["deadline"] == DEADLINE.isoformat()
    assert body["on_time"] is False


# ---- 404 -----------------------------------------------------------------------------------


def test_unknown_shift_is_404_on_both_routes(client: TestClient) -> None:
    at(START)
    assert me(client, shift_id=9999).status_code == 404
    assert simulate(client, 101, 9999).status_code == 404


def test_staff_without_an_assigned_row_in_the_shift_is_404(
    client: TestClient, production_seeded: Session
) -> None:
    at(START)
    # 202 works only the day shift
    assert me(client, staff="202").status_code == 404
    assert simulate(client, 202).status_code == 404
    assert attendance_rows(production_seeded) == []


def test_cancelled_roster_row_is_404(client: TestClient, production_seeded: Session) -> None:
    cancel_roster(production_seeded, 105)
    production_seeded.commit()
    at(START)
    assert me(client, staff="105").status_code == 404
    assert simulate(client, 105).status_code == 404
    assert attendance_rows(production_seeded) == []


def test_unknown_staff_is_404_on_the_demo_route(client: TestClient) -> None:
    at(START)
    assert simulate(client, 987654).status_code == 404


def test_demo_route_needs_no_header_and_takes_no_extra_field(client: TestClient) -> None:
    at(START)
    response = client.post(DEMO, json={"staff_id": 101, "shift_id": 1, "source": "SELF"})
    assert response.status_code == 422


def test_a_failed_check_in_does_not_leave_the_shift_locked(
    client: TestClient, production_seeded: Session
) -> None:
    at(EARLIEST - timedelta(seconds=1))
    assert me(client).status_code == 422
    at(START)
    assert me(client).status_code == 200


# ---- concurrency ---------------------------------------------------------------------------


def test_two_connections_checking_in_at_once_leave_one_row_and_one_audit(
    frozen_clock, restore_empty_database
) -> None:
    with SessionLocal() as db:
        load(db)
        db.commit()
        actor_id = actor_service.component_id(db, ActorName.SYSTEM)
    clock.set_time(START + timedelta(minutes=5))
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker() -> None:
        try:
            with SessionLocal() as db:
                barrier.wait(timeout=5)
                results.append(
                    attendance_service.check_in(
                        db,
                        staff_id=101,
                        shift_id=NIGHT_SHIFT,
                        source=CheckInSource.SIMULATED,
                        actor_id=actor_id,
                    )
                )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert all(not thread.is_alive() for thread in threads)
    assert not errors
    assert results[0] == results[1]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Attendance)) == 1
        assert len(audit_rows(db)) == 1


# ---- seed ----------------------------------------------------------------------------------


def test_load_at_reset_time_writes_no_attendance(production_seeded: Session) -> None:
    assert production_seeded.scalar(select(func.count()).select_from(Attendance)) == 0
    assert audit_rows(production_seeded) == []


def test_seed_checks_in_every_assigned_row_of_a_started_shift_on_time(
    production_seeded: Session,
) -> None:
    cancel_roster(production_seeded, 105)
    at(START + timedelta(hours=1))
    check_ins.seed(production_seeded)
    production_seeded.flush()
    rows = attendance_rows(production_seeded)
    # The Medicine ward runs shifts at the same times, so more rows than the ICU night
    assert sorted(row.staff_id for row in rows if row.shift_id == NIGHT_SHIFT) == [
        101,
        102,
        103,
        104,
    ]
    assert all(row.check_in_at == START for row in rows)
    audits = audit_rows(production_seeded)
    assert len(audits) == len(rows)
    system = actor_service.component_id(production_seeded, ActorName.SYSTEM)
    assert all(
        audit.actor_id == system
        and audit.payload["source"] == "SIMULATED"
        and audit.payload["on_time"] is True
        for audit in audits
    )
    # Not started: the ICU day shift has none, and the cancelled row got none
    day = production_seeded.get(Shift, DAY_SHIFT)
    assert day is not None and day.start_at > clock.now()
    assert all(row.shift_id != DAY_SHIFT for row in rows)
    assert 105 not in {row.staff_id for row in rows}
