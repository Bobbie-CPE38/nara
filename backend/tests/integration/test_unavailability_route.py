"""PATCH /unavailability/{id}: change when a leave period ends (round 3 PR R, workflow.md 9.5).

The seeded night shift (1) runs 2026-10-09 23:00 to 2026-10-10 07:00 with 101 to
105 on it; the day shift (2) runs 2026-10-11 07:00 to 15:00 with 202 and 203.
900 is the head nurse of ward 1. Overlaps are reported, never acted on.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    Actor,
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffUnavailability,
    Ward,
)
from app.domain.enums import (
    ActorType,
    AssignmentType,
    AuditAction,
    AvailabilityReason,
    CaseStatus,
    EntityType,
    OutreachStatus,
    RosterStatus,
    StaffStatus,
)
from app.main import app
from tests.integration.case_rows import DAY_SHIFT, NIGHT_SHIFT, leave, make_case, make_plan, offer
from tests.integration.conftest import DEMO_NOW

HEAD_NURSE = {"X-Demo-User": "900"}


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: production_seeded
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def night_leave(db: Session, staff_id: int = 105) -> StaffUnavailability:
    """What a reported leave writes: the roster row cancelled, the period = the shift."""
    leave(db, staff_id)
    db.commit()
    return db.scalars(
        select(StaffUnavailability).where(StaffUnavailability.staff_id == staff_id)
    ).one()


def shift_bounds(db: Session, shift_id: int) -> tuple[datetime, datetime]:
    """In +07:00, as the API and the audit payload send them."""
    shift = db.get(Shift, shift_id)
    assert shift is not None
    return shift.start_at.astimezone(clock.APP_TIMEZONE), shift.end_at.astimezone(
        clock.APP_TIMEZONE
    )


def patch(client: TestClient, period_id: int, end_at: object, **kwargs: object):
    headers = kwargs.pop("headers", HEAD_NURSE)
    body = {"end_at": end_at.isoformat() if isinstance(end_at, datetime) else end_at, **kwargs}
    return client.patch(f"/unavailability/{period_id}", headers=headers, json=body)  # type: ignore[arg-type]


def audits(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.UNAVAILABILITY_UPDATED)
            .order_by(AuditLog.id)
        )
    )


def other_ward_head_nurse(db: Session) -> dict[str, str]:
    ward_id = (db.scalar(select(func.max(Ward.id))) or 0) + 1
    staff_id = (db.scalar(select(func.max(Staff.id))) or 0) + 1
    db.add(Ward(id=ward_id, name="Other", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    db.add(
        Staff(
            id=staff_id,
            first_name="Other",
            last_name="Ward",
            email=f"{staff_id}@demo.local",
            password_hash="!",
            role_id=2,
            home_ward_id=ward_id,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
    db.commit()
    return {"X-Demo-User": str(staff_id)}


# --------------------------------------------------------------------------- #
# The change and its audit row
# --------------------------------------------------------------------------- #
def test_returning_early_shortens_the_period_and_writes_one_audit_row(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    period = night_leave(db)
    start, end = shift_bounds(db, NIGHT_SHIFT)
    new_end = start + timedelta(hours=2)

    response = patch(client, period.id, new_end)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "unavailability_id": period.id,
        "staff_id": 105,
        "start_at": start.isoformat(),
        "end_at": new_end.isoformat(),
        "previous_end_at": end.isoformat(),
        "overlapping_assignment_ids": [],
        "overlapping_offers": [],
    }
    db.expire_all()
    assert db.get(StaffUnavailability, period.id).end_at == new_end  # type: ignore[union-attr]
    [row] = audits(db)
    assert (row.case_id, row.event_id, row.entity_type, row.entity_id) == (
        None,
        None,
        EntityType.STAFF_UNAVAILABILITY,
        period.id,
    )
    assert row.actor_id == db.scalar(select(Actor.id).where(Actor.name == "900"))
    assert row.payload == {
        "unavailability_id": period.id,
        "staff_id": 105,
        "previous_end_at": end.isoformat(),
        "end_at": new_end.isoformat(),
    }


def test_an_open_end_can_be_given_a_return_date(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    start, _ = shift_bounds(db, NIGHT_SHIFT)
    period = StaffUnavailability(
        staff_id=201, start_at=start, end_at=None, reason=AvailabilityReason.PLANNED_LEAVE
    )
    db.add(period)
    db.commit()

    response = patch(client, period.id, start + timedelta(hours=3))

    assert response.status_code == 200, response.text
    assert response.json()["previous_end_at"] is None
    assert audits(db)[0].payload["previous_end_at"] is None


def test_extending_reports_the_assigned_shifts_and_offers_it_now_covers_and_changes_none(
    client: TestClient, production_seeded: Session
) -> None:
    """104 leaves the night shift, but holds the day shift and an offer on another case.

    Extending the leave to the end of the day shift reports both, and leaves the
    roster row ASSIGNED and the offer SENT. GET /roster then flags the row.
    """
    db = production_seeded
    period = night_leave(db, 104)
    _, day_end = shift_bounds(db, DAY_SHIFT)
    day_row = RosterAssignment(
        staff_id=104,
        shift_id=DAY_SHIFT,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REGULAR,
        candidate_source=None,
    )
    db.add(day_row)
    case = make_case(db, shift_id=DAY_SHIFT)
    sent = offer(db, case, make_plan(db, case, (104,))[104])
    stopped = make_case(db, CaseStatus.MANUAL_HANDOFF, shift_id=DAY_SHIFT)
    offer(db, stopped, make_plan(db, stopped, (104,))[104])
    db.commit()

    response = patch(client, period.id, day_end)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overlapping_assignment_ids"] == [day_row.id]
    # The offer of the stopped case is not reported
    assert body["overlapping_offers"] == [
        {"outreach_id": sent.id, "case_id": case.id, "status": "SENT"}
    ]
    db.expire_all()
    assert db.get(RosterAssignment, day_row.id).status is RosterStatus.ASSIGNED  # type: ignore[union-attr]
    assert db.get(type(sent), sent.id).status is OutreachStatus.SENT  # type: ignore[union-attr]
    roster = client.get("/roster?staff_id=104", headers=HEAD_NURSE).json()["assignments"]
    assert {row["shift"]["id"]: row["is_unavailable"] for row in roster} == {
        NIGHT_SHIFT: False,  # CANCELLED by the leave, so not flagged
        DAY_SHIFT: True,
    }


# --------------------------------------------------------------------------- #
# Refusals: 401 → 404 → 403 → 422, nothing written
# --------------------------------------------------------------------------- #
def test_refusals_and_their_order(client: TestClient, production_seeded: Session) -> None:
    db = production_seeded
    period = night_leave(db)
    start, end = shift_bounds(db, NIGHT_SHIFT)

    assert patch(client, period.id, end, headers={}).status_code == 401
    assert patch(client, 9_000_000, end, headers={"X-Demo-User": "101"}).status_code == 404
    assert patch(client, period.id, start, headers={"X-Demo-User": "101"}).status_code == 403
    assert patch(client, period.id, start).status_code == 422
    assert patch(client, period.id, start - timedelta(hours=1)).status_code == 422
    db.expire_all()
    assert db.get(StaffUnavailability, period.id).end_at == end  # type: ignore[union-attr]
    assert audits(db) == []


def test_a_head_nurse_of_another_ward_is_403(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    period = night_leave(db)
    _, end = shift_bounds(db, NIGHT_SHIFT)

    response = patch(client, period.id, end + timedelta(hours=1), headers=other_ward_head_nurse(db))

    assert response.status_code == 403
    assert audits(db) == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"end_at": None},
        {"end_at": "2026-10-10T09:00:00"},  # no time zone
        {"end_at": "2026-10-10T09:00:00+07:00", "staff_id": 101},
    ],
)
def test_the_body_needs_one_aware_end_at_and_nothing_else(
    client: TestClient, production_seeded: Session, body: dict[str, object]
) -> None:
    db = production_seeded
    period = night_leave(db)

    response = client.patch(f"/unavailability/{period.id}", headers=HEAD_NURSE, json=body)

    assert response.status_code == 422
    assert audits(db) == []


@pytest.mark.parametrize("period_id", ["0", "-1", "abc", str(2**63)])
def test_the_id_must_be_a_bigint(client: TestClient, period_id: str) -> None:
    response = client.patch(
        f"/unavailability/{period_id}",
        headers=HEAD_NURSE,
        json={"end_at": "2026-10-10T09:00:00+07:00"},
    )

    assert response.status_code == 422
