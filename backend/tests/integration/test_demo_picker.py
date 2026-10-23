"""GET /demo/wards and GET /demo/shifts: what the Demo control picks from
(round 6 PR EV6, docs/workflow.md 6.36.5).

The seed: ICU night shift 1 (D 23:00) with 101-105, ICU day shift 2 (D+2 07:00) with 202
and 203, and the Medicine shifts 21 and 22 at the same times.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Shift
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
