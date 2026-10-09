"""get_db and get_demo_user (docs/workflow.md, D9) on a throwaway app with the seeded DB."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.api.dependencies import DEMO_USER_HEADER, DbSession, DemoUser, get_db
from app.core import clock
from app.db.models import Role, Staff
from app.db.session import engine
from app.domain.enums import StaffStatus
from app.seed import load

DEMO_NOW = datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE)


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_time(DEMO_NOW)
    yield
    clock.reset()


@pytest.fixture
def seeded(db: Session) -> Session:
    load(db)
    return db


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(db: DbSession, user: DemoUser) -> dict[str, object]:
        return {
            "staff_id": user.id,
            "first_name": user.first_name,
            "same_session": object_session(user) is db,
        }

    app.dependency_overrides[get_db] = lambda: seeded
    with TestClient(app) as test_client:
        yield test_client


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


def test_header_name_is_case_insensitive(client: TestClient) -> None:
    response = client.get("/whoami", headers={"x-demo-user": "105"})

    assert response.status_code == 200


def test_user_comes_from_the_request_session(client: TestClient) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: "105"})

    assert response.json()["same_session"] is True


@pytest.mark.parametrize(
    "value",
    ["", "abc", "0", "-105", "+105", "1.5", "0105", "105,201", "1e3", "9" * 19],
)
def test_malformed_staff_id_is_401(client: TestClient, value: str) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: value})

    assert response.status_code == 401
    assert response.json() == {"detail": "X-Demo-User must be a staff ID"}


def test_unknown_staff_is_401(client: TestClient) -> None:
    response = client.get("/whoami", headers={DEMO_USER_HEADER: "999"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unknown or inactive staff 999"}


def test_inactive_staff_is_401(client: TestClient, seeded: Session) -> None:
    staff = seeded.get(Staff, 104)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    seeded.flush()

    response = client.get("/whoami", headers={DEMO_USER_HEADER: "104"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unknown or inactive staff 104"}


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
