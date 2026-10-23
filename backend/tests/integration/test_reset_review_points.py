"""Review of #145 on what a demo reset keeps (round 6 PR EV6, docs/workflow.md 6.36.2).

Logins and LINE bindings survive a reset, so nothing the old database handed out may reach
the new one: an old offer button, or a session the account no longer allows. These tests
commit, like test_demo_reset.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core import clock
from app.db.models import (
    Attendance,
    AuthSession,
    CandidateItem,
    CandidateOutreach,
    Contact,
    RosterAssignment,
    Shift,
    StaffingEvent,
    Ward,
)
from app.db.session import SessionLocal
from app.domain.enums import AssignmentType, CandidateResponse, RosterStatus
from app.main import app
from app.seed import hospital_demo
from app.seed.reset import reset_demo
from app.services import auth_service, job_service, outreach_service

pytestmark = pytest.mark.usefixtures("restore_empty_database")

client = TestClient(app)
LEAVE = {"event_type": "STAFF_UNAVAILABLE", "shift_id": 1}
PASSWORD = "kept across resets"


def _offer_of(staff_id: int) -> int:
    with SessionLocal() as db:
        offer_id = db.scalar(
            select(CandidateOutreach.id)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .where(CandidateItem.staff_id == staff_id)
            .order_by(CandidateOutreach.id.desc())
        )
    assert offer_id is not None
    return offer_id


def test_an_old_offer_button_never_names_an_offer_after_the_reset() -> None:
    """The reviewer's case: keep 201's button, reset, offer 201 again, press the old button."""
    reset_demo()
    assert client.post("/events", headers={"X-Demo-User": "105"}, json=LEAVE).status_code == 201
    old_button = _offer_of(201)

    reset_demo()
    assert client.post("/events", headers={"X-Demo-User": "105"}, json=LEAVE).status_code == 201
    new_offer = _offer_of(201)

    assert new_offer > old_button
    with SessionLocal() as db:
        assert db.get(CandidateOutreach, old_button) is None
        actor = db.scalar(text("SELECT id FROM actors WHERE staff_id = 201"))
        # What the webhook does with the old button: refused, nothing written
        with pytest.raises(outreach_service.OpenOfferConflictError):
            outreach_service.record_response(
                db,
                staff_id=201,
                actor_id=actor,
                outreach_id=old_button,
                response=CandidateResponse.ACCEPT,
            )
        db.rollback()
        new = db.get(CandidateOutreach, new_offer)
        assert new is not None and new.status.value == "SENT"


def test_only_sessions_the_account_still_allows_survive() -> None:
    reset_demo()
    with SessionLocal() as db:
        for staff_id in (105, 201, 202, 203):
            auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)
        tokens = {
            staff_id: auth_service.login(db, staff_id, PASSWORD)
            for staff_id in (105, 201, 202, 203)
        }
        assert all(tokens.values())
        auth_service.set_disabled(db, 201, True)  # closed account
        db.execute(
            text(
                "UPDATE auth_account SET must_change_password = true WHERE staff_subject ="
                " (SELECT auth_subject FROM staff WHERE id = 202)"
            )
        )
        db.execute(
            text(
                "UPDATE auth_session SET revoked_at = now() WHERE account_subject ="
                " (SELECT auth_subject FROM staff WHERE id = 203)"
            )
        )
        db.add(Contact(staff_id=202, line_uid="U" + "d" * 32, is_active=True))
        db.commit()

    reset_demo()

    with SessionLocal() as db:
        kept = db.scalars(select(AuthSession.account_subject)).all()
        assert len(kept) == 1
        live = auth_service.resolve(db, tokens[105][0])  # type: ignore[index]
        assert live is not None and live.staff.id == 105
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Contact)) == 1


def _hospital_night() -> int:
    with SessionLocal() as db:
        shift_id = db.scalar(
            select(Shift.id).where(
                Shift.ward_id == hospital_demo.WARD_BASE + 1,
                Shift.start_at == clock.now().replace(hour=23),
            )
        )
    assert shift_id is not None
    return shift_id


def test_a_replacement_from_outside_the_profile_must_check_in_by_themselves() -> None:
    """The reviewer's case: 201 put on a hospital shift was checked in by the job."""
    reset_demo(hospital=True)
    night = _hospital_night()
    with SessionLocal() as db:
        db.add(
            RosterAssignment(
                staff_id=201,
                shift_id=night,
                status=RosterStatus.ASSIGNED,
                assignment_type=AssignmentType.REPLACEMENT,
                candidate_source=None,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        db.commit()

    clock.advance(timedelta(hours=2, minutes=30))
    with SessionLocal() as db:
        job_service.run_due_work(db)

    with SessionLocal() as db:
        arrived = set(db.scalars(select(Attendance.staff_id).where(Attendance.shift_id == night)))
        missed = db.scalars(
            select(StaffingEvent.staff_id).where(StaffingEvent.shift_id == night)
        ).all()
    assert 201 not in arrived and len(arrived) == 4
    assert missed == [201]


def test_a_test_run_leaves_no_no_show_in_the_paused_hospital() -> None:
    reset_demo(hospital=True)
    started = client.post("/demo/test-runs", json={"tester_code": "T01", "scenario": "golden"})
    assert started.status_code == 201, started.text

    clock.advance(timedelta(hours=4))
    with SessionLocal() as db:
        job_service.run_due_work(db)
        events = db.scalars(
            select(StaffingEvent.id)
            .join(Shift, Shift.id == StaffingEvent.shift_id)
            .join(Ward, Ward.id == Shift.ward_id)
            .where(Ward.id > hospital_demo.WARD_BASE)
        ).all()
    assert events == []
    assert client.post(f"/demo/test-runs/{started.json()['test_run_id']}/abort").status_code == 200
