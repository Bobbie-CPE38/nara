"""GET /roster?shift_id= on the seeded Golden Case (docs/workflow.md, section 9.3)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import AuditLog, RosterAssignment, Shift, Staff, Ward
from app.domain.enums import (
    AssignmentType,
    CandidateSource,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.main import app
from app.services import roster_service
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT, EMPTY_SHIFT = 1, 2, 3
URL = f"/roster?shift_id={NIGHT_SHIFT}"
HEADERS = {"X-Demo-User": "900"}
ROW_KEYS = {
    "id",
    "status",
    "assignment_type",
    "candidate_source",
    "staff_id",
    "first_name",
    "last_name",
    "staff_status",
    "role_id",
    "role_name",
    "home_ward_id",
    "home_ward_name",
    "created_at",
    "updated_at",
}


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: production_seeded
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _row(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> RosterAssignment:
    return db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


def _assign(
    db: Session,
    staff_id: int,
    *,
    shift_id: int = NIGHT_SHIFT,
    status: RosterStatus = RosterStatus.ASSIGNED,
    assignment_type: AssignmentType = AssignmentType.REPLACEMENT,
    source: CandidateSource | None = CandidateSource.SAME_WARD,
    row_id: int | None = None,
    created_at: datetime = DEMO_NOW,
) -> RosterAssignment:
    row = RosterAssignment(
        id=row_id,
        staff_id=staff_id,
        shift_id=shift_id,
        status=status,
        assignment_type=assignment_type,
        candidate_source=source,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _empty_shift(db: Session) -> Shift:
    shift = Shift(
        id=EMPTY_SHIFT,
        ward_id=1,
        patient_count=0,
        start_at=DEMO_NOW + timedelta(days=3),
        end_at=DEMO_NOW + timedelta(days=3, hours=8),
        shift_type=ShiftType.EVENING,
        is_active=True,
    )
    db.add(shift)
    db.flush()
    return shift


def _assignments(client: TestClient, url: str = URL) -> list[dict[str, Any]]:
    response = client.get(url, headers=HEADERS)
    assert response.status_code == 200
    rows: list[dict[str, Any]] = response.json()["assignments"]
    return rows


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
def test_golden_roster_contract(client: TestClient, production_seeded: Session) -> None:
    response = client.get(URL, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"shift", "assignments"}
    assert body["shift"] == {
        "id": NIGHT_SHIFT,
        "ward_id": 1,
        "ward_name": "ICU",
        "shift_type": "NIGHT",
        "start_at": "2026-10-09T23:00:00+07:00",
        "end_at": "2026-10-10T07:00:00+07:00",
        "is_active": True,
    }
    assert [row["staff_id"] for row in body["assignments"]] == [101, 102, 103, 104, 105]
    assert all(set(row) == ROW_KEYS for row in body["assignments"])
    assert body["assignments"][0] == {
        "id": _row(production_seeded, 101).id,
        "status": "ASSIGNED",
        "assignment_type": "REGULAR",
        "candidate_source": None,
        "staff_id": 101,
        "first_name": "Pimchanok",
        "last_name": "Demo",
        "staff_status": "ACTIVE",
        "role_id": 1,
        "role_name": "RN",
        "home_ward_id": 1,
        "home_ward_name": "ICU",
        "created_at": DEMO_NOW.isoformat(),
        "updated_at": DEMO_NOW.isoformat(),
    }


def test_only_rows_of_the_asked_shift_are_returned(client: TestClient) -> None:
    response = client.get(f"/roster?shift_id={DAY_SHIFT}", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert (body["shift"]["id"], body["shift"]["shift_type"]) == (DAY_SHIFT, "DAY")
    assert [row["staff_id"] for row in body["assignments"]] == [202, 203]


def test_private_staff_fields_are_not_sent(client: TestClient) -> None:
    response = client.get(URL, headers=HEADERS)

    assert response.status_code == 200
    for private in ("email", "password_hash", "@demo.local"):
        assert private not in response.text


def test_times_are_sent_as_plus_seven_after_a_database_round_trip(
    client: TestClient, production_seeded: Session
) -> None:
    """PostgreSQL returns timestamptz in UTC. Without expire_all() the route would
    serialize the +07:00 shift this session seeded, and never see what the DB returns."""
    production_seeded.expire_all()

    body = client.get(URL, headers=HEADERS).json()

    assert body["shift"]["start_at"] == "2026-10-09T23:00:00+07:00"
    assert body["shift"]["end_at"] == "2026-10-10T07:00:00+07:00"
    assert body["assignments"][0]["created_at"] == "2026-10-09T21:00:00+07:00"
    assert body["assignments"][0]["updated_at"] == "2026-10-09T21:00:00+07:00"


# --------------------------------------------------------------------------- #
# The shift_id parameter
# --------------------------------------------------------------------------- #
def test_shift_without_rows_is_an_empty_list_not_404(
    client: TestClient, production_seeded: Session
) -> None:
    _empty_shift(production_seeded)

    response = client.get(f"/roster?shift_id={EMPTY_SHIFT}", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["shift"]["id"] == EMPTY_SHIFT
    assert response.json()["assignments"] == []


def test_unknown_shift_is_404(client: TestClient) -> None:
    response = client.get("/roster?shift_id=999999", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "No shift 999999"}


def test_shift_id_is_required(client: TestClient) -> None:
    response = client.get("/roster", headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "shift_id"]


@pytest.mark.parametrize("shift_id", ["abc", "0", "-1", "1.5", "", str(2**63)])
def test_shift_id_outside_the_bigint_range_is_422(client: TestClient, shift_id: str) -> None:
    """Rejected by validation. 2**63 would otherwise fail inside PostgreSQL as a 500."""
    response = client.get(f"/roster?shift_id={shift_id}", headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "shift_id"]


def test_largest_bigint_shift_id_reaches_the_lookup(client: TestClient) -> None:
    assert client.get(f"/roster?shift_id={2**63 - 1}", headers=HEADERS).status_code == 404


def test_inactive_shift_still_answers_with_its_rows(
    client: TestClient, production_seeded: Session
) -> None:
    shift = production_seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    shift.is_active = False
    shift.deactivated_at = DEMO_NOW
    production_seeded.flush()

    body = client.get(URL, headers=HEADERS).json()

    assert body["shift"]["is_active"] is False
    assert len(body["assignments"]) == 5


# --------------------------------------------------------------------------- #
# Rows of the shift
# --------------------------------------------------------------------------- #
def test_every_status_is_returned_as_stored(client: TestClient, production_seeded: Session) -> None:
    """Nothing is hidden: the page must show 105 as CANCELLED. PENDING_APPROVAL
    comes back as it is, the route does not count coverage."""
    db = production_seeded
    _row(db, 104).status = RosterStatus.COMPLETED
    _row(db, 105).status = RosterStatus.CANCELLED
    _assign(db, 201, status=RosterStatus.PENDING_APPROVAL)

    rows = _assignments(client)

    assert {row["staff_id"]: row["status"] for row in rows} == {
        101: "ASSIGNED",
        102: "ASSIGNED",
        103: "ASSIGNED",
        104: "COMPLETED",
        105: "CANCELLED",
        201: "PENDING_APPROVAL",
    }


def test_replacement_follows_the_cancelled_row_with_its_source(
    client: TestClient, production_seeded: Session
) -> None:
    """The end of the golden path: 105 is cancelled and 201 took the shift."""
    db = production_seeded
    _row(db, 105).status = RosterStatus.CANCELLED
    _assign(db, 201)

    rows = _assignments(client)

    assert [
        (row["staff_id"], row["status"], row["assignment_type"], row["candidate_source"])
        for row in rows[-2:]
    ] == [
        (105, "CANCELLED", "REGULAR", None),
        (201, "ASSIGNED", "REPLACEMENT", "SAME_WARD"),
    ]
    # REGULAR rows have no source
    assert all(row["candidate_source"] is None for row in rows[:-1])


def test_a_staff_member_with_two_rows_appears_twice(
    client: TestClient, production_seeded: Session
) -> None:
    """ROSTER_ASSIGNMENT has no UNIQUE on (staff_id, shift_id). The list is rows, not people."""
    db = production_seeded
    cancelled = _row(db, 105)
    cancelled.status = RosterStatus.CANCELLED
    again = _assign(db, 105)

    rows = _assignments(client)

    assert len(rows) == 6
    assert [(row["id"], row["status"]) for row in rows if row["staff_id"] == 105] == [
        (cancelled.id, "CANCELLED"),
        (again.id, "ASSIGNED"),
    ]


def test_rows_are_sorted_by_id_not_by_time_or_insertion_order(
    client: TestClient, production_seeded: Session
) -> None:
    """The rows go in with descending ids and ascending times, so only ORDER BY id
    returns them as 9001, 9002, 9003."""
    db = production_seeded
    _empty_shift(db)
    for minutes, (row_id, staff_id) in enumerate([(9003, 201), (9002, 202), (9001, 203)]):
        _assign(
            db,
            staff_id,
            shift_id=EMPTY_SHIFT,
            row_id=row_id,
            created_at=DEMO_NOW + timedelta(minutes=minutes),
        )

    rows = _assignments(client, f"/roster?shift_id={EMPTY_SHIFT}")

    assert [(row["id"], row["staff_id"]) for row in rows] == [(9001, 203), (9002, 202), (9003, 201)]


# --------------------------------------------------------------------------- #
# Stale data
# --------------------------------------------------------------------------- #
def test_inactive_staff_keep_their_row_and_show_their_status(
    client: TestClient, production_seeded: Session
) -> None:
    staff = production_seeded.get(Staff, 103)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    production_seeded.flush()

    rows = _assignments(client)

    assert [(row["status"], row["staff_status"]) for row in rows if row["staff_id"] == 103] == [
        ("ASSIGNED", "INACTIVE")
    ]


def test_cross_ward_staff_show_their_home_ward(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    db.add(Ward(id=2, name="ER", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    db.add(
        Staff(
            id=301,
            first_name="Niran",
            last_name="Demo",
            email="301@demo.local",
            password_hash="!",
            role_id=1,
            home_ward_id=2,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    _assign(db, 301, source=CandidateSource.CROSS_WARD)

    body = client.get(URL, headers=HEADERS).json()

    assert (body["shift"]["ward_id"], body["shift"]["ward_name"]) == (1, "ICU")
    row = body["assignments"][-1]
    assert (row["staff_id"], row["home_ward_id"], row["home_ward_name"]) == (301, 2, "ER")
    assert row["candidate_source"] == "CROSS_WARD"


@pytest.mark.usefixtures("stub_handlers")
def test_reported_leave_shows_as_cancelled(client: TestClient) -> None:
    reported = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT},
    )
    assert reported.status_code == 201

    rows = _assignments(client)

    assert [(row["staff_id"], row["status"]) for row in rows] == [
        (101, "ASSIGNED"),
        (102, "ASSIGNED"),
        (103, "ASSIGNED"),
        (104, "ASSIGNED"),
        (105, "CANCELLED"),
    ]


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("staff_id", [105, 201, 900])
def test_any_active_staff_member_reads_the_roster(client: TestClient, staff_id: int) -> None:
    """No role or ward check in the skeleton: 201 is not even on this shift."""
    response = client.get(URL, headers={"X-Demo-User": str(staff_id)})

    assert response.status_code == 200
    assert len(response.json()["assignments"]) == 5


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_authentication_is_required(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get(URL, headers=headers).status_code == 401


def test_inactive_user_cannot_read(client: TestClient, production_seeded: Session) -> None:
    staff = production_seeded.get(Staff, 900)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    production_seeded.flush()

    assert client.get(URL, headers=HEADERS).status_code == 401


@pytest.mark.parametrize("url", ["/roster", "/roster?shift_id=abc", "/roster?shift_id=999999"])
def test_authentication_is_checked_before_the_shift(client: TestClient, url: str) -> None:
    """401 comes before 422 and 404, so an anonymous caller learns nothing about shifts."""
    assert client.get(url).status_code == 401


# --------------------------------------------------------------------------- #
# Read-only, two statements
# --------------------------------------------------------------------------- #
def test_get_is_read_only(client: TestClient, production_seeded: Session) -> None:
    db = production_seeded
    row = _row(db, 105)
    before = dict(vars(row))
    with (
        patch.object(db, "commit", wraps=db.commit) as commit,
        patch.object(db, "flush", wraps=db.flush) as flush,
    ):
        response = client.get(URL, headers=HEADERS)

    assert response.status_code == 200
    commit.assert_not_called()
    flush.assert_not_called()
    assert vars(row) == before
    assert not db.new
    assert not db.dirty
    assert db.scalar(select(AuditLog.id)) is None


def _statement_count(db: Session, shift_id: int) -> int:
    statements: list[str] = []

    def record(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        roster_service.get_shift_roster(db, shift_id)
    finally:
        event.remove(connection, "before_cursor_execute", record)
    return len(statements)


def test_the_read_takes_two_statements_whatever_the_number_of_rows(
    production_seeded: Session,
) -> None:
    """Staff, role and home ward are joined, not loaded row by row."""
    db = production_seeded
    _empty_shift(db)
    assert _statement_count(db, EMPTY_SHIFT) == 2
    assert _statement_count(db, NIGHT_SHIFT) == 2

    for staff_id in (201, 202, 203):
        _assign(db, staff_id)

    assert _statement_count(db, NIGHT_SHIFT) == 2
    assert len(roster_service.get_shift_roster(db, NIGHT_SHIFT).assignments) == 8
