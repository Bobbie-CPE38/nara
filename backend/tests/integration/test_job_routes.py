"""GET /events/{id}, POST /demo/clock/advance and POST /internal/merge-windows/close-due
(docs/workflow.md, sections 3.8 and 9.2)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import StaffingCase, StaffingEvent
from app.domain.enums import CaseStatus, EventStatus
from app.jobs import ticker
from app.main import app
from app.schemas.job import MAX_ADVANCE_SECONDS
from app.seed.scenarios import merge_gap
from app.services import job_service
from app.services.job_service import DueWork
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1
WINDOW = merge_gap.MERGE_WINDOW_SECONDS
LEAVE = {"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT}
AS_105 = {"X-Demo-User": "105"}
SECRET = "test-secret-of-the-job"
CLOSE_DUE = "/internal/merge-windows/close-due"

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    """The Golden Case with a ten minute window on the night shift."""
    merge_gap.seed(seeded)
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def job_secret(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "internal_job_secret", SECRET)
    return {"X-Internal-Secret": SECRET}


def _waiting_event(client: TestClient) -> int:
    body = client.post("/events", headers=AS_105, json=LEAVE).json()
    assert body == {
        "event_id": body["event_id"],
        "event_status": "RECEIVED",
        "case_id": None,
        "case_status": None,
    }
    return int(body["event_id"])


# --------------------------------------------------------------------------- #
# GET /events/{event_id}
# --------------------------------------------------------------------------- #
def test_reporter_can_follow_an_event_from_received_to_its_case(
    client: TestClient, seeded: Session
) -> None:
    event_id = _waiting_event(client)

    waiting = client.get(f"/events/{event_id}")
    client.post("/demo/clock/advance", json={"seconds": WINDOW})
    closed = client.get(f"/events/{event_id}")

    assert waiting.status_code == 200
    assert waiting.json() == {
        "event_id": event_id,
        "event_status": "RECEIVED",
        "case_id": None,
        "case_status": None,
    }
    case_id = seeded.scalars(select(StaffingCase.id)).one()
    assert closed.json() == {
        "event_id": event_id,
        "event_status": "PROCESSED",
        "case_id": case_id,
        "case_status": "WAITING_RESPONSE",
    }


def test_event_status_follows_the_case_as_it_moves_on(client: TestClient, seeded: Session) -> None:
    event_id = _waiting_event(client)
    client.post("/demo/clock/advance", json={"seconds": WINDOW})
    case = seeded.scalars(select(StaffingCase)).one()
    case.status = CaseStatus.RESOLVED
    seeded.flush()

    assert client.get(f"/events/{event_id}").json()["case_status"] == "RESOLVED"


@pytest.mark.parametrize(("event_id", "status_code"), [(999, 404), (0, 422), (2**63, 422)])
def test_unknown_or_invalid_event_id(client: TestClient, event_id: int, status_code: int) -> None:
    assert client.get(f"/events/{event_id}").status_code == status_code


def test_reading_an_event_needs_no_demo_user(client: TestClient) -> None:
    event_id = _waiting_event(client)

    assert client.get(f"/events/{event_id}").status_code == 200


# --------------------------------------------------------------------------- #
# POST /demo/clock/advance
# --------------------------------------------------------------------------- #
def test_advancing_the_clock_closes_the_windows_that_became_due(
    client: TestClient, seeded: Session
) -> None:
    event_id = _waiting_event(client)

    response = client.post("/demo/clock/advance", json={"seconds": WINDOW})

    assert response.status_code == 200
    case_id = seeded.scalars(select(StaffingCase.id)).one()
    assert response.json() == {
        "clock": "2026-10-09T21:10:00+07:00",
        "closed_windows": [
            {
                "shift_id": NIGHT_SHIFT,
                "event_ids": [event_id],
                "case_id": case_id,
                "case_status": "WAITING_RESPONSE",
            }
        ],
        "auto_approved_request_ids": [],
        "failed_auto_approval_ward_ids": [],
        "no_show_event_ids": [],
        "timed_out_approval_request_ids": [],
        "timed_out_outreach_ids": [],
        "recovered_case_ids": [],
    }
    assert clock.now() == DEMO_NOW + timedelta(seconds=WINDOW)


def test_advancing_too_little_moves_the_clock_and_closes_nothing(
    client: TestClient, seeded: Session
) -> None:
    event_id = _waiting_event(client)

    response = client.post("/demo/clock/advance", json={"seconds": WINDOW - 1})

    assert response.json() == {
        "clock": "2026-10-09T21:09:59+07:00",
        "closed_windows": [],
        "auto_approved_request_ids": [],
        "failed_auto_approval_ward_ids": [],
        "no_show_event_ids": [],
        "timed_out_approval_request_ids": [],
        "timed_out_outreach_ids": [],
        "recovered_case_ids": [],
    }
    event = seeded.get(StaffingEvent, event_id)
    assert event is not None
    assert event.status is EventStatus.RECEIVED


def test_advancing_the_clock_reports_timed_out_offers_and_rechecked_cases(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route only passes on what the job round did, in ID order."""
    monkeypatch.setattr(
        job_service,
        "run_due_work",
        lambda db: DueWork(
            closed_windows=[], timed_out_outreach_ids=[5, 2], recovered_case_ids=[9, 4]
        ),
    )

    response = client.post("/demo/clock/advance", json={"seconds": 300})

    assert response.json() == {
        "clock": "2026-10-09T21:05:00+07:00",
        "closed_windows": [],
        "auto_approved_request_ids": [],
        "failed_auto_approval_ward_ids": [],
        "no_show_event_ids": [],
        "timed_out_approval_request_ids": [],
        "timed_out_outreach_ids": [2, 5],
        "recovered_case_ids": [4, 9],
    }


def test_two_small_steps_close_the_window_like_one_large_step(client: TestClient) -> None:
    _waiting_event(client)

    first = client.post("/demo/clock/advance", json={"seconds": WINDOW // 2}).json()
    second = client.post("/demo/clock/advance", json={"seconds": WINDOW // 2}).json()

    assert first["closed_windows"] == []
    assert [window["shift_id"] for window in second["closed_windows"]] == [NIGHT_SHIFT]


@pytest.mark.parametrize(
    "body",
    [{}, {"seconds": 0}, {"seconds": -60}, {"seconds": 1.5}, {"seconds": MAX_ADVANCE_SECONDS + 1}],
    ids=["missing", "zero", "negative", "fraction", "above_one_week"],
)
def test_invalid_advance_leaves_the_clock_alone(client: TestClient, body: dict[str, float]) -> None:
    response = client.post("/demo/clock/advance", json=body)

    assert response.status_code == 422
    assert clock.now() == DEMO_NOW


def test_advancing_a_clock_that_is_not_frozen_is_a_conflict(client: TestClient) -> None:
    """Real time moves by itself. Only a reset freezes the clock."""
    clock.reset()

    response = client.post("/demo/clock/advance", json={"seconds": 60})

    assert response.status_code == 409
    assert not clock.is_frozen()


# --------------------------------------------------------------------------- #
# POST /internal/merge-windows/close-due
# --------------------------------------------------------------------------- #
def test_job_route_closes_due_windows_with_the_backend_clock(
    client: TestClient, seeded: Session, job_secret: dict[str, str]
) -> None:
    event_id = _waiting_event(client)

    too_early = client.post(CLOSE_DUE, headers=job_secret)
    clock.advance(timedelta(seconds=WINDOW))
    due = client.post(CLOSE_DUE, headers=job_secret)
    again = client.post(CLOSE_DUE, headers=job_secret)

    assert (too_early.status_code, too_early.json()) == (
        200,
        {
            "closed_windows": [],
            "auto_approved_request_ids": [],
            "failed_auto_approval_ward_ids": [],
            "no_show_event_ids": [],
        },
    )
    case_id = seeded.scalars(select(StaffingCase.id)).one()
    assert due.json() == {
        "closed_windows": [
            {
                "shift_id": NIGHT_SHIFT,
                "event_ids": [event_id],
                "case_id": case_id,
                "case_status": "WAITING_RESPONSE",
            }
        ],
        "auto_approved_request_ids": [],
        "failed_auto_approval_ward_ids": [],
        "no_show_event_ids": [],
    }
    # A closed window is not closed twice
    assert again.json() == {
        "closed_windows": [],
        "auto_approved_request_ids": [],
        "failed_auto_approval_ward_ids": [],
        "no_show_event_ids": [],
    }
    assert seeded.scalar(select(func.count()).select_from(StaffingCase)) == 1


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Internal-Secret": "wrong-secret-of-the-job"}, {"X-Internal-Secret": ""}],
    ids=["missing", "wrong", "empty"],
)
def test_job_route_refuses_a_caller_without_the_secret(
    client: TestClient,
    seeded: Session,
    job_secret: dict[str, str],
    headers: dict[str, str],
) -> None:
    event_id = _waiting_event(client)
    clock.advance(timedelta(seconds=WINDOW))

    response = client.post(CLOSE_DUE, headers=headers)

    assert response.status_code == 401
    assert SECRET not in response.text
    event = seeded.get(StaffingEvent, event_id)
    assert event is not None
    assert event.status is EventStatus.RECEIVED


def test_job_route_is_closed_when_no_secret_is_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset must not mean open: there is no value a caller could guess."""
    monkeypatch.setattr(settings, "internal_job_secret", None)

    for headers in ({}, {"X-Internal-Secret": ""}, {"X-Internal-Secret": "None"}):
        assert client.post(CLOSE_DUE, headers=headers).status_code == 503


def test_demo_user_header_does_not_open_the_job_route(
    client: TestClient, job_secret: dict[str, str]
) -> None:
    assert client.post(CLOSE_DUE, headers={"X-Demo-User": "900"}).status_code == 401


# --------------------------------------------------------------------------- #
# The job service
# --------------------------------------------------------------------------- #
def test_ticker_calls_the_route_the_backend_serves() -> None:
    assert ticker.CLOSE_DUE_PATH == CLOSE_DUE
    assert ticker.SECRET_HEADER == "X-Internal-Secret"
    assert app.url_path_for("close_due_merge_windows") == CLOSE_DUE


def test_ticker_reports_an_unreachable_backend_instead_of_raising() -> None:
    # Port 9 (discard) on localhost: nothing listens there in the test container
    assert "backend not reachable" in ticker.tick("http://127.0.0.1:9" + CLOSE_DUE, SECRET)


@pytest.mark.parametrize("route", ["/demo/clock/advance", CLOSE_DUE])
def test_due_work_routes_sort_auto_approval_result_ids(client, job_secret, monkeypatch, route):
    monkeypatch.setattr(
        job_service,
        "run_due_work",
        lambda db: DueWork(
            closed_windows=[],
            auto_approved_request_ids=[8, 3],
            failed_auto_approval_ward_ids=[9, 2],
        ),
    )
    response = client.post(
        route,
        headers=job_secret,
        **({"json": {"seconds": 1}} if route.startswith("/demo") else {}),
    )
    assert response.status_code == 200
    assert response.json()["auto_approved_request_ids"] == [3, 8]
    assert response.json()["failed_auto_approval_ward_ids"] == [2, 9]


# --------------------------------------------------------------------------- #
# POST /demo/clock/freeze and /demo/clock/unfreeze
# --------------------------------------------------------------------------- #
def test_the_clock_can_be_unfrozen_and_frozen_again(client: TestClient) -> None:
    assert clock.is_frozen()

    unfrozen = client.post("/demo/clock/unfreeze")
    assert unfrozen.status_code == 200
    assert unfrozen.json()["frozen"] is False
    assert client.get("/clock").json()["frozen"] is False

    frozen = client.post("/demo/clock/freeze")
    assert frozen.status_code == 200
    assert frozen.json()["frozen"] is True
    assert client.get("/clock").json()["now"] == frozen.json()["now"]

    # a second freeze keeps the time it froze at
    assert client.post("/demo/clock/freeze").json()["now"] == frozen.json()["now"]
