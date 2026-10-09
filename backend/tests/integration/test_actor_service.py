"""actor_service against the seeded PostgreSQL: IDs come from the Golden Case seed."""

from typing import Any
from unittest import mock

import pytest
from sqlalchemy.orm import Session

from app.db.models import Actor, Staff
from app.domain.enums import ActorName, ActorType
from app.seed.scenarios.golden_case import STAFF_DATA
from app.services import actor_service
from app.services.actor_service import ActorNotFoundError

STAFF_IDS = [staff_id for staff_id, *_ in STAFF_DATA]


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


@pytest.mark.parametrize(
    "staff_id", [True, "105", 105.0, None], ids=["bool", "str", "float", "none"]
)
def test_user_id_rejects_values_that_are_not_int(seeded: Session, staff_id: Any) -> None:
    with pytest.raises(TypeError, match="staff_id must be an int"):
        actor_service.user_id(seeded, staff_id)


def test_user_id_rejects_a_staff_object(seeded: Session) -> None:
    staff = seeded.get(Staff, 105)

    with pytest.raises(TypeError, match="staff_id must be an int"):
        actor_service.user_id(seeded, staff)  # type: ignore[arg-type]


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


def test_lookups_work_with_production_session_settings(production_seeded: Session) -> None:
    assert production_seeded.autoflush is False

    orchestrator = actor_service.component_id(production_seeded, ActorName.WORKFLOW_ORCHESTRATOR)
    user = actor_service.user_id(production_seeded, 105)

    assert orchestrator != user


def test_new_actor_is_found_only_after_flush_with_production_settings(
    production_seeded: Session,
) -> None:
    """The module never flushes: a caller that adds an actor must flush before the lookup."""
    db = production_seeded
    template = db.get(Staff, 105)
    assert template is not None
    db.add(
        Staff(
            id=106,
            first_name="New",
            last_name="Nurse",
            email="106@demo.local",
            password_hash="!",
            role_id=template.role_id,
            home_ward_id=template.home_ward_id,
            status=template.status,
        )
    )
    db.flush()
    db.add(Actor(name="106", actor_type=ActorType.USER, staff_id=106))

    with pytest.raises(ActorNotFoundError):
        actor_service.user_id(db, 106)

    db.flush()
    actor = db.get(Actor, actor_service.user_id(db, 106))
    assert actor is not None
    assert actor.staff_id == 106
