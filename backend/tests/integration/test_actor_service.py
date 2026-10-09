"""actor_service against the seeded PostgreSQL: IDs come from the Golden Case seed."""

from collections.abc import Iterator
from datetime import datetime
from unittest import mock

import pytest
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Actor
from app.domain.enums import ActorName, ActorType
from app.seed import load
from app.seed.scenarios.golden_case import STAFF_DATA
from app.services import actor_service
from app.services.actor_service import ActorNotFoundError

DEMO_NOW = datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE)
STAFF_IDS = [staff_id for staff_id, *_ in STAFF_DATA]


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_time(DEMO_NOW)
    yield
    clock.reset()


@pytest.fixture
def seeded(db: Session) -> Session:
    load(db)
    return db


@pytest.mark.parametrize("name", list(ActorName))
def test_component_id_finds_every_seeded_non_user_actor(seeded: Session, name: ActorName) -> None:
    actor = seeded.get(Actor, actor_service.component_id(seeded, name))

    assert actor is not None
    assert actor.name == name.value
    assert actor.actor_type is not ActorType.USER
    assert actor.staff_id is None


@pytest.mark.parametrize("staff_id", STAFF_IDS)
def test_user_id_finds_the_actor_of_every_seeded_staff(seeded: Session, staff_id: int) -> None:
    actor = seeded.get(Actor, actor_service.user_id(seeded, staff_id))

    assert actor is not None
    assert actor.staff_id == staff_id
    assert actor.name == str(staff_id)
    assert actor.actor_type is ActorType.USER


def test_every_actor_has_a_different_id(seeded: Session) -> None:
    ids = [actor_service.component_id(seeded, name) for name in ActorName]
    ids += [actor_service.user_id(seeded, staff_id) for staff_id in STAFF_IDS]

    assert len(set(ids)) == len(ActorName) + len(STAFF_IDS)


@pytest.mark.parametrize("name", ["outreach_agent", "105"], ids=["component", "user"])
def test_component_id_rejects_plain_strings(seeded: Session, name: str) -> None:
    with pytest.raises(TypeError, match="ActorName"):
        actor_service.component_id(seeded, name)  # type: ignore[arg-type]


def test_component_id_fails_when_the_actor_is_not_seeded(db: Session) -> None:
    with pytest.raises(ActorNotFoundError, match="outreach_agent"):
        actor_service.component_id(db, ActorName.OUTREACH_AGENT)


def test_user_id_fails_for_unknown_staff(seeded: Session) -> None:
    with pytest.raises(ActorNotFoundError, match="999999"):
        actor_service.user_id(seeded, 999_999)


def test_lookups_are_read_only(seeded: Session) -> None:
    with mock.patch.object(seeded, "commit", side_effect=AssertionError("committed")):
        actor_service.component_id(seeded, ActorName.SYSTEM)
        actor_service.user_id(seeded, STAFF_IDS[0])

    assert not seeded.new
    assert not seeded.dirty
