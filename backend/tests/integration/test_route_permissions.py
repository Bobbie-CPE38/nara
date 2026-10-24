"""Route permissions in session mode (docs/workflow.md 6.33.4, round 6 PR AU2).

Who is who in the seeded wards: ICU (ward 1) has nurses 101-105 and 201-203 and head nurse
900; Medicine has nurse 301, head nurse 902 and supervisor 950. The case is the night
shift of ICU: 105 left (the event), 201 got an offer. 101 is an ICU nurse with no part in
it, 301 a nurse of another ward. 101-105 work the night shift; 201-203 do not.

Round 6 PR EV8 (6.38.2): an offer alone no longer shows a nurse the case, a nurse has no
Dashboard or gap check, and their roster is their own rows and the shifts they are on.

Every test here signs in for real: X-Demo-User is never a way in.
"""

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import rate_limit
from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CaseSummary,
    RankExplanation,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import CaseStatus
from app.main import app
from app.services import auth_service
from tests.integration.case_rows import NIGHT_SHIFT, approval, leave, replacement, short_case
from tests.integration.case_rows import offer as make_offer

PASSWORD = "permission test password"
ORIGIN = settings.cors_origins[0]
PEOPLE = (101, 105, 201, 202, 203, 301, 900, 902, 950)

pytestmark = pytest.mark.usefixtures("stub_handlers")

Client = Callable[[int], TestClient]


@pytest.fixture(autouse=True)
def session_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "auth_mode", "session")
    rate_limit.limiter.clear()
    yield
    rate_limit.limiter.clear()


@pytest.fixture
def world(production_seeded: Session) -> dict[str, int]:
    """Accounts for PEOPLE, and the ICU night-shift case: an open offer to 201, and 202's
    accepted offer waiting for the head nurse's approval."""
    db = production_seeded
    for staff_id in PEOPLE:
        auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)
    case, items = short_case(db)
    outreach = make_offer(db, case, items[201])
    # approval() gives 202 an ACCEPTED offer first: only then is the request actionable
    request = approval(db, case, items[202])
    event_id = db.scalar(select(StaffingEvent.id).where(StaffingEvent.case_id == case.id))
    assert event_id is not None
    db.commit()
    return {
        "case": case.id,
        "event": event_id,
        "outreach": outreach.id,
        "approval": request.id,
    }


def _request_db(production_seeded: Session) -> Callable[[], Iterator[Session]]:
    def request_db() -> Iterator[Session]:
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    return request_db


@pytest.fixture
def anonymous(production_seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _request_db(production_seeded)
    try:
        with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def as_(anonymous: TestClient, world: dict[str, int]) -> Iterator[Client]:
    """`as_(900)` is a client signed in as staff 900 (one login per person per test)."""
    clients: dict[int, TestClient] = {}

    def client_of(staff_id: int) -> TestClient:
        if staff_id not in clients:
            client = TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN})
            response = client.post("/auth/login", json={"staff_id": staff_id, "password": PASSWORD})
            assert response.status_code == 200, response.text
            clients[staff_id] = client
        return clients[staff_id]

    yield client_of
    for client in clients.values():
        client.close()


def _count(db: Session, model: type) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------- #
# Inventory: every method/path has an owner and an anonymous answer
# --------------------------------------------------------------------------- #
# public: answers without a session. auth: the login API of AU1. internal: the job
# secret, not a session. webhook: the LINE signature. demo: the Demo control, behind its
# own Basic Auth on AWS (6.33.5), no session. session: a signed-in user (401 otherwise)
INVENTORY: dict[tuple[str, str], str] = {
    ("GET", "/admin/staff"): "session",
    ("POST", "/admin/staff/{staff_id}/line-unlink"): "session",
    ("POST", "/admin/staff/{staff_id}/line-code"): "session",
    ("GET", "/health"): "public",
    ("GET", "/clock"): "public",
    ("GET", "/auth/config"): "auth",
    ("POST", "/auth/login"): "auth",
    ("POST", "/auth/register"): "auth",
    ("GET", "/auth/me"): "session",
    # Asked by Caddy before the Basic Auth of the Demo pages (round 6 PR EV8, 6.38.1)
    ("GET", "/auth/demo-gate"): "auth",
    ("POST", "/auth/logout"): "auth",
    ("POST", "/auth/change-password"): "session",
    ("POST", "/approvals/{approval_id}/decision"): "session",
    ("GET", "/approvals"): "session",
    ("GET", "/approvals/auto"): "session",
    ("GET", "/cases"): "session",
    ("GET", "/cases/search"): "session",
    ("GET", "/cases/{case_id}"): "session",
    ("POST", "/cases/{case_id}/explanation"): "session",
    ("POST", "/cases/{case_id}/summary"): "session",
    ("GET", "/cases/{case_id}/audit"): "session",
    ("GET", "/cases/{case_id}/handoff/candidates"): "session",
    ("POST", "/cases/{case_id}/handoff/assignments"): "session",
    ("POST", "/cases/{case_id}/handoff/close"): "session",
    ("GET", "/dashboard"): "session",
    ("POST", "/demo/reset"): "demo",
    ("POST", "/demo/clock/advance"): "demo",
    ("POST", "/demo/clock/freeze"): "demo",
    ("POST", "/demo/clock/unfreeze"): "demo",
    ("POST", "/demo/clock/resume"): "demo",
    # Names of people: a head nurse or a supervisor in session mode, like /demo/events
    ("GET", "/demo/wards"): "session",
    ("GET", "/demo/offers"): "session",
    ("POST", "/demo/offers/{outreach_id}/response"): "session",
    ("GET", "/demo/shifts"): "session",
    ("POST", "/demo/clock/set"): "demo",
    ("POST", "/demo/attendance/check-in"): "demo",
    ("POST", "/demo/events"): "demo",
    ("POST", "/demo/test-runs"): "demo",
    ("POST", "/demo/test-runs/{test_run_id}/finish"): "demo",
    ("POST", "/demo/test-runs/{test_run_id}/abort"): "demo",
    ("GET", "/demo/test-runs"): "demo",
    ("GET", "/demo/test-runs.csv"): "demo",
    ("POST", "/events"): "session",
    ("GET", "/events/{event_id}"): "session",
    ("GET", "/gap/shifts"): "session",
    ("GET", "/gap/shifts/{shift_id}"): "session",
    ("POST", "/internal/merge-windows/close-due"): "internal",
    ("POST", "/internal/line-accounts/{staff_id}/issue-code"): "internal",
    ("POST", "/internal/line-accounts/{staff_id}/unlink"): "internal",
    ("GET", "/demo/line-sim/offers"): "session",
    ("POST", "/demo/line-sim/respond"): "session",
    ("POST", "/line/webhook"): "webhook",
    ("GET", "/me/handovers"): "session",
    ("GET", "/me/offers"): "session",
    ("POST", "/me/offers/{outreach_id}/response"): "session",
    ("POST", "/me/attendance/check-in"): "session",
    ("POST", "/me/unavailability"): "session",
    ("GET", "/roster"): "session",
    ("PATCH", "/unavailability/{unavailability_id}"): "session",
}


def _app_routes() -> set[tuple[str, str]]:
    """Every method/path of the app. FastAPI keeps an included router as one wrapper whose
    `original_router` holds the routes; main.py includes them without an extra prefix."""
    found = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        inner = getattr(route, "original_router", None)
        if inner is not None:
            pending.extend(inner.routes)
        elif isinstance(route, APIRoute):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                found.add((method, route.path))
    return found


def test_every_route_is_in_the_inventory() -> None:
    """A new route fails here until it is given an owner and a test (6.33.4)."""
    assert _app_routes() == set(INVENTORY)


SESSION_ROUTES = sorted(key for key, kind in INVENTORY.items() if kind == "session")


@pytest.mark.parametrize(("method", "path"), SESSION_ROUTES)
@pytest.mark.parametrize("header", [None, "900"], ids=["no-cookie", "x-demo-user-only"])
def test_session_routes_answer_401_without_a_session(
    anonymous: TestClient, world: dict[str, int], method: str, path: str, header: str | None
) -> None:
    url = path.format(
        approval_id=world["approval"],
        case_id=world["case"],
        event_id=world["event"],
        shift_id=NIGHT_SHIFT,
        outreach_id=world["outreach"],
        unavailability_id=1,
        staff_id=201,
    )
    headers = {} if header is None else {"X-Demo-User": header}
    response = anonymous.request(method, url, headers=headers, json={})

    assert response.status_code == 401
    assert response.json() == {"detail": "AUTH_REQUIRED"}
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(("method", "path"), [("GET", "/health"), ("GET", "/clock")])
def test_public_routes_need_no_session(anonymous: TestClient, method: str, path: str) -> None:
    assert anonymous.request(method, path).status_code == 200


@pytest.mark.parametrize(
    "path",
    sorted(path for (_, path), kind in INVENTORY.items() if kind == "internal"),
)
def test_internal_routes_still_want_their_secret(anonymous: TestClient, path: str) -> None:
    url = path.format(staff_id=101)
    assert anonymous.post(url).status_code in {401, 503}


# --------------------------------------------------------------------------- #
# Cases: detail, audit, explanation, summary and the list
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("staff_id", "status_code"),
    [
        (105, 200),  # the event is theirs
        (201, 404),  # an offer alone is not enough since round 6 PR EV8
        (202, 404),  # nor an accepted offer still waiting for approval
        (101, 404),  # same ward, no part in the case
        (301, 404),  # another ward
        (900, 200),  # head nurse of the case's ward
        (902, 404),  # head nurse of another ward
        (950, 200),  # supervisor
    ],
)
@pytest.mark.parametrize("suffix", ["", "/audit"])
def test_case_reads_follow_the_matrix(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int, suffix: str
) -> None:
    response = as_(staff_id).get(f"/cases/{world['case']}{suffix}")

    assert response.status_code == status_code
    if status_code == 404:
        # A case that is not theirs reads like one that does not exist: no ID can be probed
        unknown = as_(staff_id).get(f"/cases/999999{suffix}")
        assert unknown.status_code == 404
        assert response.json()["detail"].replace(str(world["case"]), "N") == unknown.json()[
            "detail"
        ].replace("999999", "N")


def test_an_unknown_case_is_404_before_403(as_: Client, world: dict[str, int]) -> None:
    assert as_(101).get("/cases/999999").status_code == 404


@pytest.mark.parametrize(
    ("path", "model"), [("explanation", RankExplanation), ("summary", CaseSummary)]
)
def test_llm_requests_of_an_unreadable_case_are_refused_before_writing(
    as_: Client, world: dict[str, int], production_seeded: Session, path: str, model: type
) -> None:
    before = _count(production_seeded, model)

    response = as_(101).post(f"/cases/{world['case']}/{path}")

    assert response.status_code == 403
    assert _count(production_seeded, model) == before


@pytest.mark.parametrize(
    ("staff_id", "sees"),
    [(201, False), (105, True), (101, False), (301, False), (900, True), (902, False), (950, True)],
)
def test_case_list_is_filtered_in_the_query(
    as_: Client, world: dict[str, int], staff_id: int, sees: bool
) -> None:
    response = as_(staff_id).get("/cases", params={"status": CaseStatus.WAITING_RESPONSE.value})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ([world["case"]] if sees else [])


@pytest.mark.parametrize(
    ("staff_id", "status_code"), [(101, 403), (900, 200), (902, 403), (950, 200)]
)
def test_handoff_candidates_need_a_manager_of_the_ward(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int
) -> None:
    response = as_(staff_id).get(f"/cases/{world['case']}/handoff/candidates")
    assert response.status_code == status_code


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("staff_id", "status_code"),
    [(105, 200), (201, 404), (101, 404), (301, 404), (900, 200), (902, 404), (950, 200)],
)
def test_event_reads_follow_the_case_and_the_ward(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int
) -> None:
    response = as_(staff_id).get(f"/events/{world['event']}")
    assert response.status_code == status_code
    if status_code == 404:
        unknown = as_(staff_id).get("/events/999999")
        assert response.json()["detail"].replace(str(world["event"]), "N") == unknown.json()[
            "detail"
        ].replace("999999", "N")


@pytest.mark.parametrize("staff_id", [105, 900, 950])
def test_post_events_is_closed_to_every_account(
    as_: Client, world: dict[str, int], production_seeded: Session, staff_id: int
) -> None:
    before = _count(production_seeded, StaffingEvent)

    response = as_(staff_id).post(
        "/events", json={"event_type": "PATIENT_SURGE", "shift_id": NIGHT_SHIFT, "patient_count": 9}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "AUTH_FORBIDDEN"}
    assert _count(production_seeded, StaffingEvent) == before


def test_post_events_answers_403_before_reading_a_bad_body(
    as_: Client, world: dict[str, int]
) -> None:
    assert as_(900).post("/events", json={"nonsense": True}).status_code == 403


# --------------------------------------------------------------------------- #
# Approvals
# --------------------------------------------------------------------------- #
# The Supervisor sees a request only once they may decide it (round 6 PR EV7, 6.37.3)
@pytest.mark.parametrize(("staff_id", "sees"), [(900, True), (902, False), (950, False)])
def test_pending_approvals_keep_the_wards_of_the_reader(
    as_: Client, world: dict[str, int], staff_id: int, sees: bool
) -> None:
    response = as_(staff_id).get("/approvals")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ([world["approval"]] if sees else [])


def test_the_supervisor_sees_a_request_once_the_head_nurses_had_their_time(
    as_: Client, world: dict[str, int]
) -> None:
    supervisor_from = as_(900).get("/approvals").json()[0]["supervisor_from"]
    clock.set_time(datetime.fromisoformat(supervisor_from))

    assert [row["id"] for row in as_(950).get("/approvals").json()] == [world["approval"]]


@pytest.mark.parametrize("staff_id", [101, 201])
def test_staff_cannot_read_approvals(as_: Client, world: dict[str, int], staff_id: int) -> None:
    assert as_(staff_id).get("/approvals").status_code == 403
    assert as_(staff_id).get("/approvals/auto").status_code == 403


def test_staff_cannot_decide(
    as_: Client, world: dict[str, int], production_seeded: Session
) -> None:
    before = _count(production_seeded, AuditLog)

    response = as_(201).post(f"/approvals/{world['approval']}/decision", json={"approved": True})

    assert response.status_code == 403
    assert _count(production_seeded, AuditLog) == before


# --------------------------------------------------------------------------- #
# Roster, gap and dashboard
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("staff_id", "status_code"),
    [
        (101, 200),  # a nurse on the shift reads all of it
        (201, 403),  # a nurse of the ward who is not on it (round 6 PR EV8)
        (900, 200),
        (301, 403),
        (902, 403),
        (950, 200),
    ],
)
def test_shift_roster_needs_the_ward(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int
) -> None:
    response = as_(staff_id).get("/roster", params={"shift_id": NIGHT_SHIFT})
    assert response.status_code == status_code


@pytest.mark.parametrize(
    ("staff_id", "target", "status_code"),
    [
        (105, 105, 200),  # your own rows
        (101, 105, 403),  # a nurse reads nobody else's, even in their ward (round 6 PR EV8)
        (900, 105, 200),  # the head nurse reads their ward
        (301, 105, 403),  # someone of another ward
        (902, 105, 403),
        (950, 105, 200),
        (902, 999999, 404),
    ],
)
def test_staff_roster_needs_the_persons_ward(
    as_: Client, world: dict[str, int], staff_id: int, target: int, status_code: int
) -> None:
    response = as_(staff_id).get("/roster", params={"staff_id": target})
    assert response.status_code == status_code


@pytest.mark.parametrize(
    ("staff_id", "status_code"), [(101, 403), (301, 403), (900, 200), (902, 403), (950, 200)]
)
def test_gap_of_a_shift_needs_the_ward(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int
) -> None:
    assert as_(staff_id).get(f"/gap/shifts/{NIGHT_SHIFT}").status_code == status_code


@pytest.mark.parametrize(
    ("staff_id", "status_code"), [(101, 403), (201, 403), (900, 200), (950, 200)]
)
def test_the_dashboard_and_the_gap_list_are_for_managers(
    as_: Client, world: dict[str, int], staff_id: int, status_code: int
) -> None:
    """Round 6 PR EV8 (6.38.2): a nurse has the cases, the roster, their offers and leave."""
    assert as_(staff_id).get("/dashboard").status_code == status_code
    response = as_(staff_id).get("/gap/shifts", params={"ward_id": 1, "date": "2026-10-09"})
    assert response.status_code == status_code
    if status_code == 403:
        assert response.json() == {"detail": "AUTH_FORBIDDEN"}


def test_a_nurse_sees_the_case_that_put_them_on_the_shift(
    as_: Client, world: dict[str, int], production_seeded: Session
) -> None:
    """The approved candidate with their roster row reads the case, its list row and its event;
    an approval without the roster row (not on the shift) is not enough."""
    item = production_seeded.scalar(
        select(CandidateItem).where(CandidateItem.staff_id == 203).order_by(CandidateItem.id)
    )
    case = production_seeded.get(StaffingCase, world["case"])
    assert item is not None and case is not None
    approval(production_seeded, case, item, approved=True)
    production_seeded.commit()
    assert as_(203).get(f"/cases/{world['case']}").status_code == 404

    replacement(production_seeded, item)
    production_seeded.commit()

    assert as_(203).get(f"/cases/{world['case']}").status_code == 200
    listed = as_(203).get("/cases/search").json()["items"]
    assert [row["id"] for row in listed] == [world["case"]]
    assert as_(203).get(f"/events/{world['event']}").status_code == 200


# --------------------------------------------------------------------------- #
# The gate Caddy asks before the Basic Auth of the Demo pages (round 6 PR EV8, 6.38.1)
# --------------------------------------------------------------------------- #
def _gate(client: TestClient, uri: str) -> object:
    return client.get("/auth/demo-gate", headers={"X-Forwarded-Uri": uri}, follow_redirects=False)


def test_the_demo_gate_sends_a_visitor_to_the_login_without_the_basic_auth_box(
    anonymous: TestClient, world: dict[str, int]
) -> None:
    page = _gate(anonymous, "/demo/test-runs?x=1")
    assert (page.status_code, page.headers["location"]) == (302, "/login?next=/demo/test-runs")
    assert "www-authenticate" not in page.headers
    # An address Caddy would not let through never becomes the next page, and only the path
    # of the address is kept, so the login never sends anyone to another site
    odd = _gate(anonymous, "/demo/../admin/staff")
    assert odd.headers["location"] == "/login?next=/demo/control"
    other_site = _gate(anonymous, "//evil.example/demo")
    assert other_site.headers["location"] == "/login?next=/demo"
    call = _gate(anonymous, "/api/demo/reset")
    assert (call.status_code, call.json()) == (401, {"detail": "AUTH_REQUIRED"})
    assert "www-authenticate" not in call.headers
    assert call.headers["cache-control"] == "no-store"


def test_the_demo_gate_sends_a_nurse_to_their_own_page(as_: Client, world: dict[str, int]) -> None:
    page = _gate(as_(101), "/demo/control")
    assert (page.status_code, page.headers["location"]) == (302, "/me/offers")
    call = _gate(as_(101), "/api/demo/events")
    assert (call.status_code, call.json()) == (403, {"detail": "AUTH_FORBIDDEN"})


@pytest.mark.parametrize("staff_id", [900, 902, 950])
def test_the_demo_gate_lets_a_manager_on_to_the_basic_auth(
    as_: Client, world: dict[str, int], staff_id: int
) -> None:
    assert _gate(as_(staff_id), "/demo/control").status_code == 204
    assert _gate(as_(staff_id), "/api/demo/reset").status_code == 204


def test_the_demo_gate_asks_for_the_new_password_first(
    anonymous: TestClient, world: dict[str, int], production_seeded: Session
) -> None:
    auth_service.create_account(production_seeded, 102, PASSWORD, must_change_password=True)
    production_seeded.commit()
    login = anonymous.post("/auth/login", json={"staff_id": 102, "password": PASSWORD})
    assert login.status_code == 200

    page = _gate(anonymous, "/demo/control")
    assert (page.status_code, page.headers["location"]) == (302, "/change-password")
    call = _gate(anonymous, "/api/demo/reset")
    assert call.json() == {"detail": "AUTH_PASSWORD_CHANGE_REQUIRED"}


def test_the_demo_gate_lets_everyone_through_in_demo_mode(
    anonymous: TestClient, world: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "demo")
    assert _gate(anonymous, "/demo/control").status_code == 204


# --------------------------------------------------------------------------- #
# Own things only: offers, the simulator, leave changes
# --------------------------------------------------------------------------- #
def test_simulator_reads_only_your_own_offers(as_: Client, world: dict[str, int]) -> None:
    assert as_(201).get("/demo/line-sim/offers", params={"staff_id": 201}).status_code == 200
    assert as_(201).get("/demo/line-sim/offers", params={"staff_id": 202}).status_code == 403


def test_someone_elses_offer_cannot_be_answered(
    as_: Client, world: dict[str, int], production_seeded: Session
) -> None:
    response = as_(202).post(
        f"/me/offers/{world['outreach']}/response", json={"response": "ACCEPT"}
    )

    assert response.status_code == 409
    production_seeded.expire_all()
    outreach = production_seeded.get(CandidateOutreach, world["outreach"])
    assert outreach is not None and outreach.status.value == "SENT"


@pytest.fixture
def leave_period(production_seeded: Session, world: dict[str, int]) -> int:
    leave(production_seeded, 104)
    production_seeded.commit()
    period_id = production_seeded.scalar(
        select(StaffUnavailability.id).where(StaffUnavailability.staff_id == 104)
    )
    assert period_id is not None
    return period_id


@pytest.mark.parametrize(
    ("staff_id", "status_code"), [(101, 403), (902, 403), (900, 200), (950, 200)]
)
def test_leave_end_changes_by_ward_managers_and_supervisors(
    as_: Client, leave_period: int, staff_id: int, status_code: int
) -> None:
    response = as_(staff_id).patch(
        f"/unavailability/{leave_period}", json={"end_at": "2099-01-01T00:00:00+07:00"}
    )
    assert response.status_code == status_code


def test_password_change_required_blocks_case_reads(
    anonymous: TestClient, world: dict[str, int], production_seeded: Session
) -> None:
    auth_service.create_account(production_seeded, 102, PASSWORD, must_change_password=True)
    production_seeded.commit()
    assert (
        anonymous.post("/auth/login", json={"staff_id": 102, "password": PASSWORD}).status_code
        == 200
    )

    response = anonymous.get(f"/cases/{world['case']}")

    assert response.status_code == 403
    assert response.json() == {"detail": "AUTH_PASSWORD_CHANGE_REQUIRED"}
