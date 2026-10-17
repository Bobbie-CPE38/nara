"""GET /gap/shifts and GET /gap/shifts/{id} (docs/workflow.md 6.31, 9.8, round 6 PR F1).

The seed: ward 1 (ICU) has night shift 1 (D 23:00 to D+1 07:00, five RNs) and day shift
2 (D+2 07:00); ward 2 (Medicine) mirrors them as shifts 21 and 22. 900 is the ICU head
nurse, 902 the Medicine head nurse and 950 the Supervisor.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    Attendance,
    RosterAssignment,
    Shift,
    StaffingGap,
    StaffingRequirement,
    Ward,
)
from app.domain.enums import AssignmentType, CaseStatus, RosterStatus, ShiftType
from app.main import app
from tests.integration import case_rows
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT, MEDICINE_NIGHT = 1, 2, 21
HEAD_NURSE, MEDICINE_HEAD_NURSE, SUPERVISOR, NURSE = 900, 902, 950, 105
DAY = DEMO_NOW.date()


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _get(client: TestClient, path: str, user: int = HEAD_NURSE, **params: object):
    return client.get(path, params=params, headers={"X-Demo-User": str(user)})


def test_the_day_lists_its_shifts_with_the_gap_now(client: TestClient, seeded: Session) -> None:
    case_rows.leave(seeded, 105)

    response = _get(client, "/gap/shifts", ward_id=1, date=DAY.isoformat())

    assert response.status_code == 200
    assert response.json() == [
        {
            "shift_id": NIGHT_SHIFT,
            "ward_id": 1,
            "start_at": "2026-10-09T23:00:00+07:00",
            "end_at": "2026-10-10T07:00:00+07:00",
            "required_staff": 5,
            "rostered_count": 4,
            "headcount_gap": 1,
            "case_id": None,
        }
    ]


def test_the_date_is_the_start_day_in_bangkok(client: TestClient) -> None:
    """Shift 2 starts D+2 07:00 +07:00, which is D+2 00:00 UTC: still D+2 here."""
    later = (DAY + timedelta(days=2)).isoformat()
    assert [
        row["shift_id"] for row in _get(client, "/gap/shifts", ward_id=1, date=later).json()
    ] == [DAY_SHIFT]
    nothing = (DAY + timedelta(days=1)).isoformat()
    assert _get(client, "/gap/shifts", ward_id=1, date=nothing).json() == []


def test_a_running_case_is_linked_and_an_ended_one_is_not(
    client: TestClient, seeded: Session
) -> None:
    case_rows.make_case(seeded, CaseStatus.RESOLVED)
    running = case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF)

    (row,) = _get(client, "/gap/shifts", ward_id=1, date=DAY.isoformat()).json()
    assert row["case_id"] == running.id
    assert _get(client, f"/gap/shifts/{NIGHT_SHIFT}").json()["case_id"] == running.id


@pytest.mark.parametrize(
    ("user", "allowed"), [(HEAD_NURSE, False), (NURSE, False), (SUPERVISOR, True)]
)
def test_another_ward_needs_a_supervisor(client: TestClient, user: int, allowed: bool) -> None:
    listing = _get(client, "/gap/shifts", user, ward_id=2, date=DAY.isoformat())
    detail = _get(client, f"/gap/shifts/{MEDICINE_NIGHT}", user)

    assert listing.status_code == detail.status_code == (200 if allowed else 403)


def test_the_medicine_head_nurse_sees_only_medicine(client: TestClient) -> None:
    assert _get(client, f"/gap/shifts/{MEDICINE_NIGHT}", MEDICINE_HEAD_NURSE).status_code == 200
    assert _get(client, f"/gap/shifts/{NIGHT_SHIFT}", MEDICINE_HEAD_NURSE).status_code == 403


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"ward_id": 1},
        {"date": "2026-10-09"},
        {"ward_id": 0, "date": "2026-10-09"},
        {"ward_id": 1, "date": "tomorrow"},
    ],
)
def test_missing_or_bad_queries_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert _get(client, "/gap/shifts", **params).status_code == 422


def test_an_unknown_shift_is_404_and_out_of_range_is_422(client: TestClient) -> None:
    assert _get(client, "/gap/shifts/999999").status_code == 404
    assert _get(client, f"/gap/shifts/{2**63}").status_code == 422


@pytest.mark.parametrize("path", ["/gap/shifts?ward_id=1&date=2026-10-09", "/gap/shifts/1"])
def test_routes_need_a_demo_user(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


def test_the_roster_shows_leave_check_in_and_cancelled_rows(
    client: TestClient, seeded: Session
) -> None:
    case_rows.leave(seeded, 105)
    seeded.add(
        Attendance(staff_id=101, shift_id=NIGHT_SHIFT, check_in_at=DEMO_NOW, synced_at=DEMO_NOW)
    )
    seeded.flush()

    body = _get(client, f"/gap/shifts/{NIGHT_SHIFT}").json()

    roster = {row["staff_id"]: row for row in body["roster"]}
    assert sorted(roster) == [101, 102, 103, 104, 105]
    assert roster[105]["status"] == "CANCELLED" and roster[105]["on_leave"] is True
    assert roster[101]["checked_in"] is True and roster[101]["on_leave"] is False
    assert roster[102]["checked_in"] is False
    assert roster[101]["name"] == "Pimchanok Demo"
    assert roster[101]["effective_start_at"] == "2026-10-09T23:00:00+07:00"
    assert roster[101]["effective_end_at"] == "2026-10-10T07:00:00+07:00"
    row_id = seeded.scalar(
        select(RosterAssignment.id).where(
            RosterAssignment.staff_id == 101, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    )
    assert roster[101]["roster_assignment_id"] == row_id


def test_the_gap_matches_the_case_page_of_the_same_shift(
    client: TestClient, seeded: Session
) -> None:
    """Workflow 6.31: with a case on the shift, both pages show the same slices.

    104 leaves at 03:00, so the gap has two slices with different counts.
    """
    case_rows.leave(seeded, 105)
    row = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 104, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()
    row.actual_end_at = DEMO_NOW + timedelta(hours=6)
    case = case_rows.make_case(seeded)
    case_rows.record_gap(seeded, case)

    case_gap = client.get(f"/cases/{case.id}").json()["gap"]
    check = _get(client, f"/gap/shifts/{NIGHT_SHIFT}").json()

    assert len(check["intervals"]) == 2
    assert check["intervals"] == case_gap["intervals"]
    assert check["evaluated_from"] == case_gap["evaluated_from"]
    assert check["case_id"] == case.id


def test_a_started_shift_is_measured_from_the_backend_clock(
    client: TestClient, seeded: Session
) -> None:
    clock.set_time(DEMO_NOW + timedelta(hours=4))  # D+1 01:00, inside the night shift

    body = _get(client, f"/gap/shifts/{NIGHT_SHIFT}").json()

    assert body["evaluated_from"] == "2026-10-10T01:00:00+07:00"
    assert body["intervals"][0]["start_at"] == "2026-10-10T01:00:00+07:00"


def test_the_gap_routes_write_nothing(client: TestClient, seeded: Session) -> None:
    """No INSERT, UPDATE or DELETE and no row lock, even for a short shift with a case."""
    case_rows.leave(seeded, 105)
    case_rows.make_case(seeded)
    seeded.flush()
    gaps_before = seeded.scalars(select(StaffingGap.id)).all()
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    bind = seeded.connection()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        assert _get(client, "/gap/shifts", ward_id=1, date=DAY.isoformat()).status_code == 200
        assert _get(client, f"/gap/shifts/{NIGHT_SHIFT}").status_code == 200
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert statements, "the capture saw no statement"
    writes = [
        sql
        for sql in statements
        if sql.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        or "FOR UPDATE" in sql.upper()
        or "FOR NO KEY UPDATE" in sql.upper()
    ]
    assert writes == []
    assert seeded.scalars(select(StaffingGap.id)).all() == gaps_before


def _row(db: Session, staff_id: int, shift_id: int) -> RosterAssignment:
    return db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


def _transfer(db: Session, staff_id: int, source_shift: int, to_shift: int) -> RosterAssignment:
    """A mid-shift move: the person's row on `to_shift` continues their row on the source."""
    source = _row(db, staff_id, source_shift)
    moved = RosterAssignment(
        staff_id=staff_id,
        shift_id=to_shift,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REPLACEMENT,
        transferred_from_assignment_id=source.id,
    )
    db.add(moved)
    db.flush()
    return moved


def _checked_in(client: TestClient, shift_id: int, staff_id: int, user: int = SUPERVISOR) -> bool:
    roster = _get(client, f"/gap/shifts/{shift_id}", user).json()["roster"]
    (entry,) = [row for row in roster if row["staff_id"] == staff_id]
    return entry["checked_in"]


@pytest.mark.parametrize("minutes_after_start", [0, 90])
def test_a_check_in_at_the_source_carries_through_a_transfer(
    client: TestClient, seeded: Session, minutes_after_start: int
) -> None:
    """Review finding 1: the person checked in at the source shift, on time or late.

    The destination row has no Attendance of its own, but a move creates no second
    check-in (workflow 6.24), so the roster must show the person as checked in.
    """
    start = seeded.get(Shift, NIGHT_SHIFT).start_at
    seeded.add(
        Attendance(
            staff_id=101,
            shift_id=NIGHT_SHIFT,
            check_in_at=start + timedelta(minutes=minutes_after_start),
            synced_at=DEMO_NOW,
        )
    )
    _transfer(seeded, 101, NIGHT_SHIFT, MEDICINE_NIGHT)

    assert _checked_in(client, MEDICINE_NIGHT, 101) is True


def test_a_chain_of_two_moves_still_finds_the_first_check_in(
    client: TestClient, seeded: Session
) -> None:
    seeded.add(
        Attendance(staff_id=101, shift_id=NIGHT_SHIFT, check_in_at=DEMO_NOW, synced_at=DEMO_NOW)
    )
    first = _transfer(seeded, 101, NIGHT_SHIFT, MEDICINE_NIGHT)
    seeded.add(
        Shift(
            id=9100,
            ward_id=1,
            patient_count=2,
            start_at=DEMO_NOW,
            end_at=DEMO_NOW + timedelta(hours=8),
            shift_type=ShiftType.NIGHT,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    seeded.flush()
    seeded.add(
        RosterAssignment(
            staff_id=101,
            shift_id=9100,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            transferred_from_assignment_id=first.id,
        )
    )
    seeded.flush()
    seeded.add(
        StaffingRequirement(shift_id=9100, required_staff=1, minimum_staff=1, created_at=DEMO_NOW)
    )
    seeded.flush()

    assert _checked_in(client, 9100, 101) is True


def test_a_moved_person_who_never_checked_in_is_not_checked_in(
    client: TestClient, seeded: Session
) -> None:
    _transfer(seeded, 102, NIGHT_SHIFT, MEDICINE_NIGHT)

    assert _checked_in(client, MEDICINE_NIGHT, 102) is False
    assert _checked_in(client, NIGHT_SHIFT, 102) is False


def test_a_check_in_does_not_leak_to_another_person_or_an_unlinked_row(
    client: TestClient, seeded: Session
) -> None:
    """Only the chain counts: 101 checked in at the source, 301 is a different person."""
    seeded.add(
        Attendance(staff_id=101, shift_id=NIGHT_SHIFT, check_in_at=DEMO_NOW, synced_at=DEMO_NOW)
    )
    seeded.flush()

    assert _checked_in(client, MEDICINE_NIGHT, 301) is False
    assert _checked_in(client, NIGHT_SHIFT, 101) is True


def test_an_inactive_ward_is_hidden_from_a_supervisor_on_every_route(
    client: TestClient, seeded: Session
) -> None:
    """Review finding 2: the dashboard lists the active wards, and the gap routes agree."""
    seeded.get(Ward, 2).is_active = False
    seeded.flush()

    dashboard = client.get("/dashboard", headers={"X-Demo-User": str(SUPERVISOR)}).json()

    assert dashboard["wards"] == [1, 3]
    assert (
        _get(client, "/gap/shifts", SUPERVISOR, ward_id=2, date=DAY.isoformat()).status_code == 403
    )
    assert _get(client, f"/gap/shifts/{MEDICINE_NIGHT}", SUPERVISOR).status_code == 403
    assert _get(client, f"/gap/shifts/{NIGHT_SHIFT}", SUPERVISOR).status_code == 200


@pytest.mark.parametrize("day", ["9999-12-31", "3000-01-01", "1999-12-31", "0001-01-01"])
def test_dates_outside_the_supported_range_are_422(client: TestClient, day: str) -> None:
    assert _get(client, "/gap/shifts", ward_id=1, date=day).status_code == 422


@pytest.mark.parametrize("day", ["2000-01-01", "2999-12-31"])
def test_the_edges_of_the_supported_range_work(client: TestClient, day: str) -> None:
    response = _get(client, "/gap/shifts", ward_id=1, date=day)

    assert response.status_code == 200 and response.json() == []


def _shift_without_requirement(db: Session) -> int:
    """An active ICU shift later the same day that nobody gave a staffing requirement."""
    db.add(
        Shift(
            id=9001,
            ward_id=1,
            patient_count=2,
            start_at=DEMO_NOW + timedelta(hours=1),
            end_at=DEMO_NOW + timedelta(hours=9),
            shift_type=ShiftType.DAY,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    db.flush()
    return 9001


def test_a_shift_without_a_requirement_is_skipped_by_the_day_list(
    client: TestClient, seeded: Session
) -> None:
    """Review finding: one badly set up shift must not turn the whole list into a 500."""
    bad = _shift_without_requirement(seeded)

    response = _get(client, "/gap/shifts", ward_id=1, date=DAY.isoformat())

    assert response.status_code == 200
    assert [row["shift_id"] for row in response.json()] == [NIGHT_SHIFT]
    assert bad not in [row["shift_id"] for row in response.json()]


def test_the_detail_of_a_shift_without_a_requirement_is_409(
    client: TestClient, seeded: Session
) -> None:
    bad = _shift_without_requirement(seeded)

    assert _get(client, f"/gap/shifts/{bad}").status_code == 409
