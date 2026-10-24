"""Review points of PR AU2 (#128) that the first version of the tests did not cover
(docs/workflow.md 6.33.4):

  * the Dashboard counts of a nurse follow what concerns them in any ward, like the case itself
  * a case that is not theirs is 404, not 403, and asking the LLM is for managers
  * the pending approvals of a head nurse are filtered in the query and show only their own side
  * POST /demo/events needs a session of a manager in session mode, and every audit row of a
    simulated event is by the SYSTEM actor, also after a merge window that stayed open
  * a route under /demo/line-sim is guarded by the router, one role decides the leave of a period
"""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.api import rate_limit
from app.api.dependencies import get_db, get_reader
from app.api.routes import line_sim
from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, CandidateItem, Shift, StaffingCase, StaffUnavailability
from app.domain.enums import ActorName, AuditAction, CaseStatus
from app.main import app
from app.services import access_service, actor_service, auth_service, job_service
from app.services import unavailability_service as unavailability
from tests.integration.case_rows import approval, make_plan, offer
from tests.integration.test_approval_two_wards import build

PASSWORD = "review points test password"
ORIGIN = settings.cors_origins[0]
NIGHT = 1
DAY = 2
WAITING = CaseStatus.WAITING_APPROVAL.value
ACCOUNTS = (105, 201, 202, 301, 900, 902, 950)

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture(autouse=True)
def session_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "auth_mode", "session")
    rate_limit.limiter.clear()
    yield
    rate_limit.limiter.clear()


class Scene:
    def __init__(self, db: Session, request_id: int, source_head: int, supervisor: int) -> None:
        self.db = db
        self.request_id = request_id
        self.source_head = source_head
        self.supervisor = supervisor
        self.case_id = db.scalars(select(StaffingCase.id)).one()


@pytest.fixture
def scene(production_seeded: Session) -> Iterator[Scene]:
    """The two-ward move of test_approval_two_wards, with the accounts of the people in it."""
    db = production_seeded
    request_id, source_headers, supervisor_headers = build(db)
    built = Scene(
        db, request_id, int(source_headers["X-Demo-User"]), int(supervisor_headers["X-Demo-User"])
    )
    for staff_id in (*ACCOUNTS, built.source_head, built.supervisor):
        auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)
    db.commit()

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
        yield built
    finally:
        app.dependency_overrides.pop(get_db, None)


def client_of(staff_id: int | None) -> TestClient:
    client = TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN})
    if staff_id is not None:
        answer = client.post("/auth/login", json={"staff_id": staff_id, "password": PASSWORD})
        assert answer.status_code == 200, answer.text
    return client


# --------------------------------------------------------------------------- #
# A nurse's Dashboard follows the case, in any ward
# --------------------------------------------------------------------------- #
def test_a_nurse_offered_a_shift_of_another_ward_sees_it_everywhere_or_nowhere(
    scene: Scene,
) -> None:
    """Medicine nurse 301 has an open offer on an ICU case: the case, the list and the
    Dashboard counts all show it, and nobody else of Medicine does."""
    db = scene.db
    case = db.get(StaffingCase, scene.case_id)
    assert case is not None
    items = make_plan(db, case, (301,))
    offer(db, case, items[301])
    db.commit()

    me = client_of(301)
    assert me.get(f"/cases/{scene.case_id}").status_code == 200
    listed = me.get(f"/cases?status={WAITING}").json()
    assert [row["id"] for row in listed] == [scene.case_id]
    dashboard = me.get("/dashboard").json()
    counts = {row["status"]: row["count"] for row in dashboard["cases_by_status"]}
    assert counts[WAITING] == 1
    assert dashboard["open_offers"]["count"] == 1

    # The head nurse of Medicine has no part in it: nothing, in the case, the list or the counts
    other = client_of(902)
    assert other.get(f"/cases/{scene.case_id}").status_code == 404
    assert other.get(f"/cases?status={WAITING}").json() == []
    other_dashboard = other.get("/dashboard").json()
    other_counts = {row["status"]: row["count"] for row in other_dashboard["cases_by_status"]}
    assert other_counts[WAITING] == 0
    assert other_dashboard["open_offers"]["count"] == 0


def test_a_nurse_with_no_part_in_the_case_counts_nothing(scene: Scene) -> None:
    dashboard = client_of(105).get("/dashboard").json()
    # 105 reported the leave that opened the case, so it is theirs; 301 has no part in it
    counts = {row["status"]: row["count"] for row in dashboard["cases_by_status"]}
    assert counts[WAITING] == 1
    nothing = client_of(301).get("/dashboard").json()
    assert {row["status"]: row["count"] for row in nothing["cases_by_status"]}[WAITING] == 0


# --------------------------------------------------------------------------- #
# Asking the LLM is for managers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["explanation", "summary"])
def test_llm_requests_are_for_a_manager_who_may_read_the_case(scene: Scene, path: str) -> None:
    url = f"/cases/{scene.case_id}/{path}"
    # 105 may read the case (it is their leave) but may not queue model work
    refused = client_of(105).post(url)
    assert refused.status_code == 403
    assert refused.json() == {"detail": "AUTH_FORBIDDEN"}
    # A head nurse of a ward with no part in it: the case is not theirs
    other = client_of(902).post(url)
    assert other.status_code == 404
    assert other.json()["detail"]["code"] == "CASE_NOT_FOUND"
    # The head nurse of the case: not refused (the answer is the LLM's own: 200 or a 409)
    assert client_of(900).post(url).status_code not in (403, 404)


# --------------------------------------------------------------------------- #
# Pending approvals: in the query, own side only
# --------------------------------------------------------------------------- #
def _supervisor_may_decide(rows: list[dict]) -> None:  # type: ignore[type-arg]
    clock.set_time(max(datetime.fromisoformat(row["supervisor_from"]) for row in rows))


def _sides(rows: list[dict]) -> list[list[int]]:  # type: ignore[type-arg]
    return [sorted(side["ward_id"] for side in row["wards"]) for row in rows]


def test_a_head_nurse_gets_only_the_side_of_their_own_ward(scene: Scene) -> None:
    destination = client_of(900).get("/approvals?pending=true").json()
    source = client_of(scene.source_head).get("/approvals?pending=true").json()
    # A supervisor gets a request once they may decide it (round 6 PR EV7, 6.37.3)
    _supervisor_may_decide(destination)
    everyone = client_of(scene.supervisor).get("/approvals?pending=true").json()

    assert [row["id"] for row in destination] == [scene.request_id]
    assert [row["id"] for row in source] == [scene.request_id]
    assert _sides(destination) == [[1]]
    source_ward = _sides(source)[0]
    assert len(source_ward) == 1 and source_ward != [1]
    assert _sides(everyone) == [sorted([1, source_ward[0]])]
    assert client_of(902).get("/approvals?pending=true").json() == []
    assert client_of(105).get("/approvals?pending=true").status_code == 403


def test_another_request_of_the_same_case_is_not_in_a_source_head_nurses_queue(
    scene: Scene,
) -> None:
    """The source head nurse may read the case (a request moves someone out of their ward), but
    a second pending request of the same case that only involves the ICU is not theirs."""
    db = scene.db
    case = db.get(StaffingCase, scene.case_id)
    assert case is not None
    item_202 = db.scalars(select(CandidateItem).where(CandidateItem.staff_id == 202)).one()
    other = approval(db, case, item_202)
    db.commit()

    def ids(staff_id: int) -> list[int]:
        rows = client_of(staff_id).get("/approvals?pending=true").json()
        return [row["id"] for row in rows]

    # The source head nurse reads the case, and sees only the request that involves their ward
    source_nurse = client_of(scene.source_head)
    assert source_nurse.get(f"/cases/{scene.case_id}").status_code == 200
    assert ids(scene.source_head) == [scene.request_id]
    assert other.id not in ids(scene.source_head)
    assert all(row["wards"] for row in source_nurse.get("/approvals?pending=true").json())
    # The ICU head nurse has a side in both, and a supervisor sees both
    assert ids(900) == sorted([scene.request_id, other.id])
    _supervisor_may_decide(client_of(900).get("/approvals?pending=true").json())
    assert ids(scene.supervisor) == sorted([scene.request_id, other.id])
    # The head nurse of a ward with no side in either sees none
    assert ids(902) == []


def test_the_pending_list_is_filtered_by_the_query_not_after_loading(scene: Scene) -> None:
    """The request of another ward is never loaded for a head nurse who has no side in it."""
    statements: list[str] = []
    engine = scene.db.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client_of(902).get("/approvals?pending=true").json() == []
    finally:
        event.remove(engine, "before_cursor_execute", record)
    listing = [s for s in statements if "FROM approval_request" in s and "candidate_items" in s]
    assert listing, "the list query was not seen"
    # The ward condition is in the statement itself
    assert all("shift" in s.lower() and "EXISTS" in s.upper() for s in listing)


# --------------------------------------------------------------------------- #
# POST /demo/events: a manager's session, and SYSTEM all the way
# --------------------------------------------------------------------------- #
SURGE = {
    "event_type": "PATIENT_SURGE",
    "shift_id": DAY,
    "patient_count": 12,
    "reporter_staff_id": 900,
}


def test_an_anonymous_caller_cannot_post_a_demo_event(scene: Scene) -> None:
    """Whatever stands in front of the machine: no session, no event, not even as a head nurse."""
    before = scene.db.scalar(select(func.count()).select_from(AuditLog))
    anonymous = client_of(None)
    assert anonymous.post("/demo/events", json=SURGE).status_code == 401
    spoofed = anonymous.post("/demo/events", json=SURGE, headers={"X-Demo-User": "900"})
    assert spoofed.status_code == 401
    scene.db.expire_all()
    assert scene.db.scalar(select(func.count()).select_from(AuditLog)) == before


def test_a_nurse_cannot_post_a_demo_event_and_a_manager_can(scene: Scene) -> None:
    refused = client_of(105).post("/demo/events", json=SURGE)
    assert refused.status_code == 403
    assert refused.json() == {"detail": "AUTH_FORBIDDEN"}
    assert client_of(900).post("/demo/events", json=SURGE).status_code == 201
    assert client_of(scene.supervisor).post("/demo/events", json=SURGE).status_code == 201


def _audit_actor(db: Session, action: AuditAction, event_id: int) -> int:
    db.expire_all()
    return db.scalars(
        select(AuditLog.actor_id).where(AuditLog.event_id == event_id, AuditLog.action == action)
    ).one()


def test_every_audit_row_of_a_simulated_leave_is_by_system(scene: Scene) -> None:
    db = scene.db
    answer = client_of(900).post(
        "/demo/events",
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": DAY, "reporter_staff_id": 202},
    )
    assert answer.status_code == 201, answer.text
    event_id = answer.json()["event_id"]
    system = actor_service.component_id(db, ActorName.SYSTEM)
    assert _audit_actor(db, AuditAction.EVENT_RECEIVED, event_id) == system
    # 202 did nothing: the unavailability it creates is not theirs to answer for
    assert _audit_actor(db, AuditAction.UNAVAILABILITY_CREATED, event_id) == system


def test_a_simulated_head_nurse_event_is_by_system_when_it_is_applied(scene: Scene) -> None:
    db = scene.db
    answer = client_of(900).post("/demo/events", json=SURGE)
    assert answer.status_code == 201, answer.text
    system = actor_service.component_id(db, ActorName.SYSTEM)
    assert _audit_actor(db, AuditAction.PATIENT_COUNT_UPDATED, answer.json()["event_id"]) == system


def test_a_simulated_event_is_by_system_after_a_window_that_stayed_open(scene: Scene) -> None:
    db = scene.db
    shift = db.get(Shift, DAY)
    assert shift is not None
    shift.merge_window_seconds = 600
    db.commit()

    answer = client_of(900).post(
        "/demo/events",
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": DAY, "reporter_staff_id": 202},
    )
    assert answer.status_code == 201, answer.text
    event_id = answer.json()["event_id"]
    assert answer.json()["event_status"] == "RECEIVED"  # the window is still open

    clock.advance(timedelta(seconds=601))
    job_service.run_due_work(db)

    system = actor_service.component_id(db, ActorName.SYSTEM)
    assert _audit_actor(db, AuditAction.UNAVAILABILITY_CREATED, event_id) == system


def test_a_genuine_own_leave_stays_by_the_user_after_a_window_that_stayed_open(
    scene: Scene,
) -> None:
    db = scene.db
    shift = db.get(Shift, DAY)
    assert shift is not None
    shift.merge_window_seconds = 600
    db.commit()

    answer = client_of(202).post("/me/unavailability", json={"shift_id": DAY})
    assert answer.status_code == 201, answer.text
    event_id = answer.json()["event_id"]
    clock.advance(timedelta(seconds=601))
    job_service.run_due_work(db)

    assert _audit_actor(db, AuditAction.EVENT_RECEIVED, event_id) == actor_service.user_id(db, 202)
    assert _audit_actor(db, AuditAction.UNAVAILABILITY_CREATED, event_id) == actor_service.user_id(
        db, 202
    )
    assert db.scalar(select(func.count()).select_from(StaffUnavailability)) == 1


# --------------------------------------------------------------------------- #
# The simulator is guarded by its router; one role decides a leave period
# --------------------------------------------------------------------------- #
def test_every_route_of_the_line_simulator_asks_for_a_session_by_default(scene: Scene) -> None:
    assert any(dep.dependency is get_reader for dep in line_sim.router.dependencies)
    anonymous = client_of(None)
    assert anonymous.get("/demo/line-sim/offers?staff_id=201").status_code == 401
    body = {"outreach_id": 1, "response": "ACCEPT"}
    assert anonymous.post("/demo/line-sim/respond", json=body).status_code == 401


def test_answering_the_offer_of_someone_else_through_the_simulator_changes_nothing(
    scene: Scene,
) -> None:
    from app.db.models import CandidateOutreach

    db = scene.db
    outreach = db.scalars(select(CandidateOutreach)).first()
    assert outreach is not None
    before = outreach.status
    answer = client_of(105).post(
        "/demo/line-sim/respond", json={"outreach_id": outreach.id, "response": "REJECT"}
    )
    assert answer.status_code >= 400
    db.expire_all()
    assert db.get(CandidateOutreach, outreach.id).status == before  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("role", "home_ward", "allowed"),
    [
        ("head_nurse", 1, True),
        ("head_nurse", 2, False),
        ("supervisor", 2, True),
        ("staff", 1, False),
    ],
)
def test_the_leave_period_is_decided_by_the_role_it_is_given(
    scene: Scene, role: str, home_ward: int, allowed: bool
) -> None:
    db = scene.db
    shift = db.get(Shift, DAY)
    assert shift is not None
    period = StaffUnavailability(
        staff_id=105,
        start_at=shift.start_at,
        end_at=shift.end_at,
        reason=unavailability.AvailabilityReason.UNPLANNED_LEAVE,
    )
    db.add(period)
    db.commit()
    call: Callable[[], object] = lambda: unavailability.update_end_at(  # noqa: E731
        db,
        unavailability_id=period.id,
        end_at=shift.end_at + timedelta(hours=1),
        role=role,  # type: ignore[arg-type]
        home_ward_id=home_ward,
        actor_id=actor_service.user_id(db, 900),
    )
    if allowed:
        call()
    else:
        with pytest.raises(unavailability.UnavailabilityForbiddenError):
            call()


# --------------------------------------------------------------------------- #
# One query to read a case or an event
# --------------------------------------------------------------------------- #
def test_a_head_nurse_reads_only_the_rows_of_their_wards_in_anothers_roster(
    scene: Scene,
) -> None:
    """201 (an ICU nurse) holds one row on a shift of another ward. The ICU head nurse reads their
    roster without it, the supervisor and 201 with it, and the filter is in the statement."""
    db = scene.db
    statements: list[str] = []
    engine = db.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        seen = client_of(900).get("/roster?staff_id=201")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert seen.status_code == 200
    assert seen.json()["assignments"] == []
    rows = [s for s in statements if "FROM roster_assignment" in s and "staff_id" in s]
    assert rows and all("ward_id" in s for s in rows), "the ward filter is not in the query"

    for reader in (scene.supervisor, 201):
        full = client_of(reader).get("/roster?staff_id=201")
        assert full.status_code == 200
        assert len(full.json()["assignments"]) == 1
    # A head nurse of a ward that does not read 201's ward is refused before any row
    assert client_of(902).get("/roster?staff_id=201").status_code == 403


def test_may_the_viewer_read_this_is_one_statement(scene: Scene) -> None:
    db = scene.db
    viewer = access_service.Viewer(staff_id=902, home_ward_id=2, role="head_nurse")
    statements: list[str] = []
    engine = db.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert access_service.sees_case(db, viewer, scene.case_id) is False
        assert access_service.sees_case(db, viewer, 999999) is False
        assert access_service.sees_event(db, viewer, 999999) is False
    finally:
        event.remove(engine, "before_cursor_execute", record)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 3, statements
