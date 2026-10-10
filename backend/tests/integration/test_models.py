"""Person 1's models against a real PostgreSQL: defaults, enum round trip and constraints."""

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.base import Base
from app.db.models import Actor, Role, Shift, Staff, StaffingEvent, Ward
from app.domain.enums import (
    ActorName,
    ActorType,
    EventStatus,
    EventType,
    ShiftType,
    StaffStatus,
)
from tests.integration.conftest import DEMO_NOW

pytestmark = pytest.mark.usefixtures("frozen_clock")


@pytest.fixture
def session(db: Session) -> Session:
    # DDL is transactional in PostgreSQL, so the `db` fixture rolls these tables back.
    # Once the first migration exists the tables are already there and this is a no-op
    Base.metadata.create_all(db.connection())
    return db


@pytest.fixture
def staff(session: Session) -> Staff:
    role = Role(name="RN")
    ward = Ward(name="ICU", is_active=True)
    session.add_all([role, ward])
    session.flush()
    member = Staff(
        first_name="Demo",
        last_name="Nurse",
        email="105@demo.local",
        password_hash="!",
        role_id=role.id,
        home_ward_id=ward.id,
        status=StaffStatus.ACTIVE,
    )
    session.add(member)
    session.flush()
    return member


@pytest.fixture
def shift(session: Session, staff: Staff) -> Shift:
    row = Shift(
        ward_id=staff.home_ward_id,
        patient_count=10,
        start_at=DEMO_NOW + timedelta(hours=3),
        end_at=DEMO_NOW + timedelta(hours=11),
        shift_type=ShiftType.NIGHT,
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def test_timestamps_default_to_the_clock(session: Session, staff: Staff) -> None:
    session.expire_all()

    assert staff.created_at == DEMO_NOW
    assert staff.updated_at == DEMO_NOW


def test_updated_at_follows_the_clock_on_update(session: Session, staff: Staff) -> None:
    later = clock.advance(timedelta(minutes=5))

    staff.status = StaffStatus.INACTIVE
    session.flush()
    session.expire_all()

    assert staff.created_at == DEMO_NOW
    assert staff.updated_at == later


def test_enum_column_reads_back_as_the_enum_member(session: Session, staff: Staff) -> None:
    session.expire_all()

    assert staff.status is StaffStatus.ACTIVE


def test_enum_column_rejects_an_unknown_value(session: Session, staff: Staff) -> None:
    staff.status = "ON_LEAVE"  # type: ignore[assignment]

    with pytest.raises(StatementError, match="ON_LEAVE"), session.begin_nested():
        session.flush()


def test_event_payload_defaults_to_empty_object(
    session: Session, staff: Staff, shift: Shift
) -> None:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift.id,
        occurred_at=clock.now(),
        staff_id=staff.id,
        status=EventStatus.RECEIVED,
    )
    session.add(event)
    session.flush()
    session.expire_all()

    assert event.payload == {}


def test_staff_event_requires_staff_id(session: Session, shift: Shift) -> None:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift.id,
        occurred_at=clock.now(),
        staff_id=None,
        status=EventStatus.RECEIVED,
    )

    with (
        pytest.raises(IntegrityError, match="ck_staffing_events_staff_id_matches_event_group"),
        session.begin_nested(),
    ):
        session.add(event)
        session.flush()


def test_demand_event_must_not_have_staff_id(session: Session, staff: Staff, shift: Shift) -> None:
    event = StaffingEvent(
        event_type=EventType.PATIENT_SURGE,
        shift_id=shift.id,
        occurred_at=clock.now(),
        staff_id=staff.id,
        status=EventStatus.RECEIVED,
    )

    with (
        pytest.raises(IntegrityError, match="ck_staffing_events_staff_id_matches_event_group"),
        session.begin_nested(),
    ):
        session.add(event)
        session.flush()


def test_user_actor_requires_staff_id(session: Session) -> None:
    actor = Actor(name="105", actor_type=ActorType.USER, staff_id=None)

    with pytest.raises(IntegrityError, match="ck_actors_user_has_staff"), session.begin_nested():
        session.add(actor)
        session.flush()


def test_component_actor_must_not_have_staff_id(session: Session, staff: Staff) -> None:
    actor = Actor(name=ActorName.OUTREACH_AGENT, actor_type=ActorType.COMPONENT, staff_id=staff.id)

    with pytest.raises(IntegrityError, match="ck_actors_user_has_staff"), session.begin_nested():
        session.add(actor)
        session.flush()


def test_one_actor_per_staff_member(session: Session, staff: Staff) -> None:
    session.add(Actor(name=str(staff.id), actor_type=ActorType.USER, staff_id=staff.id))
    session.flush()

    with pytest.raises(IntegrityError, match="uq_actors_staff_id"), session.begin_nested():
        session.add(Actor(name="duplicate", actor_type=ActorType.USER, staff_id=staff.id))
        session.flush()


def test_component_actor_name_is_unique(session: Session) -> None:
    session.add(Actor(name=ActorName.OUTREACH_AGENT, actor_type=ActorType.COMPONENT))
    session.flush()

    with pytest.raises(IntegrityError, match="uq_actors_name_non_user"), session.begin_nested():
        session.add(Actor(name=ActorName.OUTREACH_AGENT, actor_type=ActorType.COMPONENT))
        session.flush()
