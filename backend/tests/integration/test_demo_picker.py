"""GET /demo/wards and GET /demo/shifts: what the Demo control picks from
(round 6 PR EV6, docs/workflow.md 6.36.5).

The seed: ICU night shift 1 (D 23:00) with 101-105, ICU day shift 2 (D+2 07:00) with 202
and 203, and the Medicine shifts 21 and 22 at the same times.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import AuditLog, Shift
from app.domain.enums import AuditAction
from app.main import app
from tests.integration.conftest import DEMO_NOW


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_every_ward_is_listed(client: TestClient) -> None:
    wards = client.get("/demo/wards").json()

    assert [(ward["id"], ward["name"], ward["is_float_pool"]) for ward in wards] == [
        (1, "ICU", False),
        (2, "Medicine", False),
        (3, "Float Pool", True),
    ]


def test_the_shifts_of_a_day_come_with_every_person_on_them(client: TestClient) -> None:
    shifts = client.get(
        "/demo/shifts", params={"ward_id": 1, "date": DEMO_NOW.date().isoformat()}
    ).json()

    assert [shift["id"] for shift in shifts] == [1]
    night = shifts[0]
    assert night["shift_type"] == "NIGHT"
    assert night["start_at"].endswith("23:00:00+07:00")
    assert [person["staff_id"] for person in night["people"]] == [101, 102, 103, 104, 105]
    assert night["people"][0] == {
        "staff_id": 101,
        "first_name": "Pimchanok",
        "last_name": "Demo",
        "status": "ASSIGNED",
        "checked_in": False,
    }


def test_another_day_and_an_unknown_ward_have_their_own_shifts_or_none(
    client: TestClient,
) -> None:
    later = DEMO_NOW.date().toordinal() + 2
    day_after_next = DEMO_NOW.date().fromordinal(later).isoformat()

    day = client.get("/demo/shifts", params={"ward_id": 1, "date": day_after_next}).json()
    unknown = client.get("/demo/shifts", params={"ward_id": 999, "date": day_after_next})

    assert [(shift["id"], [p["staff_id"] for p in shift["people"]]) for shift in day] == [
        (2, [202, 203])
    ]
    assert unknown.status_code == 200 and unknown.json() == []


def test_an_inactive_shift_is_not_offered(client: TestClient, seeded: Session) -> None:
    """Review of #145: the picker listed shifts the gap check leaves out."""
    shift = seeded.get(Shift, 1)
    assert shift is not None
    shift.is_active = False
    seeded.flush()

    shifts = client.get(
        "/demo/shifts", params={"ward_id": 1, "date": DEMO_NOW.date().isoformat()}
    ).json()

    assert shifts == []


def test_the_wards_name_their_head_nurse(client: TestClient) -> None:
    """Round 6 PR EV7 (6.37.8): who reports a patient surge from the Demo control."""
    wards = {ward["id"]: ward["head_nurse_id"] for ward in client.get("/demo/wards").json()}

    assert wards == {1: 900, 2: 902, 3: None}


def test_an_open_offer_is_listed_and_answered_in_the_candidates_name(
    client: TestClient, seeded: Session
) -> None:
    leave = client.post(
        "/events",
        headers={"X-Demo-User": "105"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert leave.status_code == 201, leave.text

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(seeded.get_bind(), "before_cursor_execute", record)
    try:
        offers = client.get("/demo/offers").json()
    finally:
        event.remove(seeded.get_bind(), "before_cursor_execute", record)
    assert {offer["staff_id"] for offer in offers} == {201, 202}
    # Both candidates' offers come from one read, not one per candidate
    assert sum("offer_outcome_notification" in statement for statement in statements) == 1
    first = next(offer for offer in offers if offer["staff_id"] == 202)
    assert first["first_name"] == "Phanu" and first["can_reject"] is True

    answered = client.post(f"/demo/offers/{first['id']}/response", json={"response": "REJECT"})
    again = client.post(f"/demo/offers/{first['id']}/response", json={"response": "ACCEPT"})
    unknown = client.post("/demo/offers/999999/response", json={"response": "ACCEPT"})

    assert answered.status_code == 200 and answered.json()["outreach_status"] == "REJECTED"
    assert again.status_code == 409
    assert unknown.status_code == 404
    rejected = seeded.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.OFFER_REJECTED)
    ).one()
    assert rejected.payload["source"] == "SIMULATED"
