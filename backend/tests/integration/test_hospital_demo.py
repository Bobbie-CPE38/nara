"""The hospital demo of the Demo control (round 6 PR EV6, docs/workflow.md 6.36.3).

Five more wards and a Float Pool for a week, loaded by a reset that asks for them and kept
by the next resets. These tests commit, like test_demo_reset.
"""

from collections import Counter
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Attendance,
    DemoDataset,
    RosterAssignment,
    Shift,
    Staff,
    StaffingEvent,
    Ward,
)
from app.db.session import SessionLocal
from app.domain.enums import EventType, RosterStatus
from app.main import app
from app.seed import hospital_demo
from app.seed.reset import reset_demo
from app.services import job_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

client = TestClient(app)

WARDS = len(hospital_demo.WARD_NAMES)
DAYS = hospital_demo.DAYS_BEFORE + hospital_demo.DAYS_AFTER + 1


def _hospital_shifts(db: Session) -> list[Shift]:
    return list(
        db.scalars(select(Shift).where(Shift.ward_id > hospital_demo.WARD_BASE).order_by(Shift.id))
    )


def test_a_reset_with_the_hospital_loads_a_week_of_five_wards() -> None:
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200

    with SessionLocal() as db:
        wards = db.scalars(select(Ward).where(Ward.id > hospital_demo.WARD_BASE)).all()
        assert sorted(ward.name for ward in wards) == sorted(
            [*hospital_demo.WARD_NAMES, "Hospital Float Pool"]
        )
        people = db.scalar(
            select(func.count()).select_from(Staff).where(Staff.id > hospital_demo.STAFF_BASE)
        )
        assert people == WARDS * 16 + hospital_demo.FLOAT_POOL_SIZE
        shifts = _hospital_shifts(db)
        assert len(shifts) == WARDS * DAYS * 3
        now = clock.now()
        for shift in shifts:
            rows = db.scalars(
                select(RosterAssignment).where(RosterAssignment.shift_id == shift.id)
            ).all()
            # Exactly the required staff on every shift, none twice
            assert len({row.staff_id for row in rows}) == len(rows) == 4
            expected = RosterStatus.COMPLETED if shift.end_at <= now else RosterStatus.ASSIGNED
            assert {row.status for row in rows} == {expected}
        # The evening shift of D is running at 21:00: its people are checked in
        running = [shift for shift in shifts if shift.start_at <= now < shift.end_at]
        assert len(running) == WARDS
        checked_in = db.scalar(
            select(func.count())
            .select_from(Attendance)
            .where(Attendance.shift_id.in_([shift.id for shift in running]))
        )
        assert checked_in == WARDS * 4


def test_the_next_resets_keep_the_choice_until_one_changes_it() -> None:
    reset_demo(hospital=True)
    reset_demo()

    with SessionLocal() as db:
        assert db.scalars(select(DemoDataset.profile)).all() == [hospital_demo.PROFILE]
        assert len(_hospital_shifts(db)) == WARDS * DAYS * 3

    # Left out: paused, because its people are kept like everyone (6.33.7)
    assert client.post("/demo/reset", json={"hospital": False}).status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(DemoDataset.profile)).all() == [hospital_demo.PAUSED_PROFILE]
        assert _hospital_shifts(db) == []
        assert not any(
            db.scalars(select(Ward.is_active).where(Ward.id > hospital_demo.WARD_BASE)).all()
        )
        assert db.get(Staff, hospital_demo.STAFF_BASE + 1) is not None
    # No body: still paused; asked for again: back with its week
    assert client.post("/demo/reset").status_code == 200
    with SessionLocal() as db:
        assert _hospital_shifts(db) == []
    assert client.post("/demo/reset", json={"hospital": True}).status_code == 200
    with SessionLocal() as db:
        assert len(_hospital_shifts(db)) == WARDS * DAYS * 3


def test_leaving_out_a_hospital_never_loaded_adds_nothing() -> None:
    assert client.post("/demo/reset", json={"hospital": False}).status_code == 200

    with SessionLocal() as db:
        assert db.scalars(select(DemoDataset.profile)).all() == []
        assert db.scalars(select(Ward.id).where(Ward.id > hospital_demo.WARD_BASE)).all() == []


def test_the_hospital_people_come_to_work_and_are_never_a_no_show() -> None:
    """Without the arrivals, the start of the night shift made 20 NO_SHOW cases at once."""
    reset_demo(hospital=True)
    with SessionLocal() as db:
        night = next(
            shift
            for shift in _hospital_shifts(db)
            if shift.start_at == clock.now().replace(hour=23)
        )
        absent = db.scalars(
            select(RosterAssignment.staff_id)
            .where(RosterAssignment.shift_id == night.id)
            .order_by(RosterAssignment.staff_id)
        ).first()
        night_id = night.id
    assert absent is not None
    # One of them reports leave from the Demo control before the shift
    reported = client.post(
        "/demo/events",
        json={
            "event_type": EventType.STAFF_UNAVAILABLE.value,
            "shift_id": night_id,
            "reporter_staff_id": absent,
        },
    )
    assert reported.status_code == 201, reported.text

    # Past the start and the grace period of NO_SHOW
    clock.advance(timedelta(hours=2, minutes=30))
    with SessionLocal() as db:
        job_service.run_due_work(db)

    with SessionLocal() as db:
        arrived = db.scalars(
            select(Attendance.staff_id).where(Attendance.shift_id == night_id)
        ).all()
        no_shows = db.scalars(
            select(StaffingEvent)
            .join(Shift, Shift.id == StaffingEvent.shift_id)
            .where(Shift.ward_id > hospital_demo.WARD_BASE)
        ).all()
    assert len(arrived) == 3 and absent not in arrived
    # The only event of the hospital is the leave that was reported
    assert Counter(event.staff_id for event in no_shows) == Counter({absent: 1})


def test_a_test_run_pauses_the_hospital_wards() -> None:
    reset_demo(hospital=True)

    started = client.post("/demo/test-runs", json={"tester_code": "T01", "scenario": "golden"})

    assert started.status_code == 201, started.text
    with SessionLocal() as db:
        active = db.scalars(
            select(Ward.id).where(Ward.id > hospital_demo.WARD_BASE, Ward.is_active.is_(True))
        ).all()
    assert active == []
    assert client.post(f"/demo/test-runs/{started.json()['test_run_id']}/abort").status_code == 200
