"""Bounded nurse history, stable keyset ordering and header-only ownership."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import AuditLog, RosterAssignment, StructuredHandover
from app.domain.enums import RosterStatus
from app.main import app
from app.services import handover_service
from tests.integration.test_handover import created


def history_rows(db, count=25):
    case, current, snapshot = created(db)
    rows = []
    for _ in range(count):
        roster = RosterAssignment(
            staff_id=201,
            shift_id=current.shift_id,
            status=RosterStatus.COMPLETED,
            assignment_type=current.assignment_type,
        )
        db.add(roster)
        db.flush()
        row = StructuredHandover(
            case_id=case.id,
            shift_id=current.shift_id,
            incoming_staff_id=201,
            roster_assignment_id=roster.id,
            generated_at=snapshot.generated_at,
            content=snapshot.content,
        )
        db.add(row)
        db.flush()
        rows.append(row)
    return current, snapshot, rows


def test_history_is_bounded_and_timestamp_ties_never_skip_or_duplicate(production_seeded):
    db = production_seeded
    _, current, rows = history_rows(db)
    db.commit()
    audits = db.scalar(select(func.count()).select_from(AuditLog))
    cursor = None
    seen = []
    while True:
        page = handover_service.page_handovers(db, staff_id=201, limit=7, cursor=cursor)
        assert [h.handover_id for h in page.active] == [current.id]
        assert len(page.history) <= 7
        seen.extend(h.handover_id for h in page.history)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == [row.id for row in reversed(rows)]
    assert db.scalar(select(func.count()).select_from(AuditLog)) == audits
    assert not db.new and not db.dirty


def test_newer_history_insert_does_not_shift_the_next_page(production_seeded):
    db = production_seeded
    _, snapshot, rows = history_rows(db, count=5)
    snapshot.generated_at += timedelta(seconds=1)
    db.flush()
    page = handover_service.page_handovers(db, staff_id=201, limit=2)
    assert page.next_cursor
    # A current handover becomes newer history between requests.
    current = db.scalars(
        select(RosterAssignment).where(RosterAssignment.id == page.active[0].roster_assignment_id)
    ).one()
    current.status = RosterStatus.CANCELLED
    db.flush()
    next_page = handover_service.page_handovers(db, staff_id=201, limit=10, cursor=page.next_cursor)
    assert [h.handover_id for h in next_page.history] == [row.id for row in reversed(rows[:-2])]


def test_clock_and_roster_status_are_rechecked_on_every_page(production_seeded):
    db = production_seeded
    current, snapshot, _ = history_rows(db, count=2)
    first = handover_service.page_handovers(db, staff_id=201, limit=1)
    current.status = RosterStatus.CANCELLED
    db.flush()
    second = handover_service.page_handovers(db, staff_id=201, limit=1, cursor=first.next_cursor)
    assert second.active == []
    current.status = RosterStatus.ASSIGNED
    db.flush()
    clock.advance(timedelta(days=2))
    assert handover_service.page_handovers(db, staff_id=201).active == []


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=no", "cursor=bad!", "cursor="])
def test_invalid_parameters_return_422(production_seeded, query):
    app.dependency_overrides[get_db] = lambda: production_seeded
    try:
        with TestClient(app) as client:
            assert (
                client.get("/me/handovers?" + query, headers={"X-Demo-User": "201"}).status_code
                == 422
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cursor_cannot_select_another_nurses_history(production_seeded):
    db = production_seeded
    history_rows(db, count=2)
    db.commit()
    page = handover_service.page_handovers(db, staff_id=201, limit=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get("/me/handovers").status_code == 401
            response = client.get("/me/handovers?staff_id=201", headers={"X-Demo-User": "202"})
            assert response.json() == {"active": [], "history": [], "next_cursor": None}
            assert (
                client.get(
                    "/me/handovers",
                    params={"cursor": page.next_cursor},
                    headers={"X-Demo-User": "202"},
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_current_handovers_are_not_truncated_by_the_history_limit(production_seeded):
    db = production_seeded
    _, _, history = history_rows(db, count=4)
    for row in history:
        db.get(RosterAssignment, row.roster_assignment_id).status = RosterStatus.ASSIGNED
    db.flush()
    page = handover_service.page_handovers(db, staff_id=201, limit=1)
    assert len(page.active) == 5 and page.history == [] and page.next_cursor is None


@pytest.mark.parametrize(
    "changes",
    [
        {"v": True},
        {"v": 2},
        {"id": 0},
        {"id": True},
        {"at": "2026-10-09T21:00:00"},
        {"at": []},
        {"extra": 1},
    ],
)
def test_invalid_cursor_fields_are_rejected(production_seeded, changes):
    import base64
    import json

    payload = {"v": 1, "staff": 201, "at": "2026-10-09T21:00:00+07:00", "id": 1} | changes
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(ValueError, match="Invalid handover history cursor"):
        handover_service.page_handovers(production_seeded, staff_id=201, cursor=cursor)
