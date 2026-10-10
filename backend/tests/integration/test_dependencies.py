"""get_db and get_demo_user (docs/workflow.md, D9) on a throwaway app with the seeded DB."""

from collections.abc import Iterator
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.api.dependencies import DEMO_USER_HEADER, MAX_STAFF_ID, DbSession, DemoUser, get_db
from app.db.models import Actor, Role, Staff
from app.db.session import engine
from app.domain.enums import ActorType, StaffStatus
from app.services import actor_service


def _client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(db: DbSession, user: DemoUser) -> dict[str, object]:
        return {
            "staff_id": user.staff.id,
            "first_name": user.staff.first_name,
            "actor_id": user.actor_id,
            "same_session": object_session(user.staff) is db,
        }

    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    yield from _client(seeded)


@pytest.fixture
def production_client(production_seeded: Session) -> Iterator[TestClient]:
    """Same app, but the session has SessionLocal's options (autoflush off)."""
    yield from _client(production_seeded)


def _add_staff(
    db: Session, staff_id: int, *, status: StaffStatus | str = StaffStatus.ACTIVE
) -> Staff:
    template = db.get(Staff, 105)
    assert template is not None
    staff = Staff(
        id=staff_id,
        first_name="Extra",
        last_name="Staff",
        email=f"{staff_id}@demo.local",
        password_hash="!",
        role_id=template.role_id,
        home_ward_id=template.home_ward_id,
        status=status,
    )
    db.add(staff)
    return staff


def _add_actor(db: Session, staff_id: int) -> None:
    db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))


def test_missing_header_is_401(client: TestClient) -> None:
    response = client.get("/whoami")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing X-Demo-User header"}
    assert response.headers["WWW-Authenticate"] == DEMO_USER_HEADER


@pytest.mark.parametrize("staff_id", [105, 201, 900])
def test_known_staff_is_returned(client: TestClient, staff_id: int) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: str(staff_id)})

    assert response.status_code == 200
    assert response.json()["staff_id"] == staff_id


@pytest.mark.parametrize("staff_id", [105, 201, 900])
def test_actor_id_is_the_user_actor_of_that_staff(
    client: TestClient, seeded: Session, staff_id: int
) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: str(staff_id)})

    actor_id = response.json()["actor_id"]
    assert actor_id == actor_service.user_id(seeded, staff_id)
    actor = seeded.get(Actor, actor_id)
    assert actor is not None
    assert actor.actor_type is ActorType.USER
    assert actor.staff_id == staff_id


def test_known_staff_takes_one_query(client: TestClient, seeded: Session) -> None:
    """Staff and actor ID come from one joined SELECT, not two lookups."""
    with mock.patch.object(seeded, "execute", wraps=seeded.execute) as execute:
        response = client.get("/whoami", headers={DEMO_USER_HEADER: "105"})

    assert response.status_code == 200
    assert execute.call_count == 1


def test_header_name_is_case_insensitive(client: TestClient) -> None:
    response = client.get("/whoami", headers={"x-demo-user": "105"})

    assert response.status_code == 200


def test_user_comes_from_the_request_session(client: TestClient) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: "105"})

    assert response.json()["same_session"] is True


@pytest.mark.parametrize(
    "value",
    ["", "abc", "0", "-105", "+105", "1.5", "0105", "105,201", "1e3", "9" * 19, "9" * 20],
)
def test_malformed_staff_id_is_401(client: TestClient, value: str) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: value})

    assert response.status_code == 401
    assert response.json() == {"detail": "X-Demo-User must be a staff ID"}


@pytest.mark.parametrize("staff_id", [1_000_000_000_000_000_000, MAX_STAFF_ID])
def test_nineteen_digit_staff_id_within_bigint_is_accepted(
    client: TestClient, seeded: Session, staff_id: int
) -> None:
    _add_staff(seeded, staff_id)
    seeded.flush()
    _add_actor(seeded, staff_id)
    seeded.flush()

    response = client.get("/whoami", headers={DEMO_USER_HEADER: str(staff_id)})

    assert response.status_code == 200
    assert response.json()["staff_id"] == staff_id


def test_staff_id_above_bigint_is_401_without_querying(client: TestClient, seeded: Session) -> None:
    assert MAX_STAFF_ID == 9_223_372_036_854_775_807

    with (
        mock.patch.object(seeded, "get", side_effect=AssertionError("queried")),
        mock.patch.object(seeded, "scalar", side_effect=AssertionError("queried")),
        mock.patch.object(seeded, "execute", side_effect=AssertionError("queried")),
    ):
        response = client.get("/whoami", headers={DEMO_USER_HEADER: str(MAX_STAFF_ID + 1)})

    assert response.status_code == 401
    assert response.json() == {"detail": "X-Demo-User must be a staff ID"}


def test_unknown_staff_is_401(client: TestClient) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: "999"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Staff 999 is unknown, inactive or has no actor"}


def test_inactive_staff_is_401(client: TestClient, seeded: Session) -> None:
    staff = seeded.get(Staff, 104)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    seeded.flush()

    response = client.get("/whoami", headers={DEMO_USER_HEADER: "104"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Staff 104 is unknown, inactive or has no actor"}


def test_staff_without_an_actor_is_401(client: TestClient, seeded: Session) -> None:
    """Otherwise an audited route fails later in user_id() and the case goes FAILED."""
    _add_staff(seeded, 106)
    seeded.flush()

    response = client.get("/whoami", headers={DEMO_USER_HEADER: "106"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Staff 106 is unknown, inactive or has no actor"}


def test_status_written_as_a_plain_string_in_this_session_is_accepted(
    client: TestClient, seeded: Session
) -> None:
    """StrEnumText accepts "ACTIVE"; the in-memory row keeps the string until reloaded."""
    staff = _add_staff(seeded, 106, status="ACTIVE")
    seeded.flush()
    _add_actor(seeded, 106)
    seeded.flush()
    assert type(staff.status) is str

    response = client.get("/whoami", headers={DEMO_USER_HEADER: "106"})

    assert response.status_code == 200


def test_get_db_yields_a_session_and_never_commits() -> None:
    generator = get_db()
    db = next(generator)
    db.add(Role(name="GET_DB_PROBE"))
    db.flush()

    generator.close()

    with Session(engine) as check:
        count = check.scalar(
            select(func.count()).select_from(Role).where(Role.name == "GET_DB_PROBE")
        )
    assert count == 0


def test_get_db_session_has_the_production_settings() -> None:
    generator = get_db()
    db = next(generator)
    try:
        assert db.autoflush is False
        assert db.expire_on_commit is False
    finally:
        generator.close()


@pytest.mark.parametrize(("staff_id", "status_code"), [(105, 200), (900, 200), (999, 401)])
def test_demo_user_with_production_session_settings(
    production_client: TestClient, production_seeded: Session, staff_id: int, status_code: int
) -> None:
    assert production_seeded.autoflush is False

    response = production_client.get("/whoami", headers={DEMO_USER_HEADER: str(staff_id)})

    assert response.status_code == status_code


def test_new_staff_is_accepted_only_after_flush_with_production_settings(
    production_client: TestClient, production_seeded: Session
) -> None:
    """get_demo_user reads with a SELECT, so unflushed rows are invisible when autoflush is off."""
    _add_staff(production_seeded, 106)
    production_seeded.flush()
    _add_actor(production_seeded, 106)

    before = production_client.get("/whoami", headers={DEMO_USER_HEADER: "106"})
    production_seeded.flush()
    after = production_client.get("/whoami", headers={DEMO_USER_HEADER: "106"})

    assert before.status_code == 401
    assert after.status_code == 200
