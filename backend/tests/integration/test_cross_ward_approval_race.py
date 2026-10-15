"""Two cases of different wards use one candidate: no overlapping assignments (round 4 PR C1).

docs/workflow.md section 6.19 and the silent-failure table of "สถานะของรอบ 4".
Section 6.11 makes the first decision cancel the candidate's other offers, so the
second head nurse finds a cancelled offer. The race runs on two connections.
"""

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    CandidateOutreach,
    RosterAssignment,
    Shift,
    Staff,
    StaffingRequirement,
    StaffingRequirementRole,
    Ward,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    COMMITTED_ROSTER_STATUSES,
    CandidateSource,
    CaseStatus,
    OutreachStatus,
    ShiftType,
    StaffStatus,
)
from app.main import app
from app.seed import load
from tests.integration.case_rows import (
    NIGHT_SHIFT,
    RN,
    approval,
    cancel_roster,
    make_case,
    make_plan,
    offer,
    record_gap,
    safety,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_approval_decision import _add_other_ward_head_nurse

HEAD_A = {"X-Demo-User": "900"}


@dataclass(frozen=True)
class Scene:
    candidate_id: int
    shift_ids: tuple[int, int]
    approval_ids: tuple[int, int]
    headers: tuple[dict[str, str], dict[str, str]]


def _build(db: Session) -> Scene:
    """Case A on the night shift of ICU, case B on an overlapping shift of a new ward.

    Staff X belongs to a third ward, so both cases offer them as a cross-ward
    candidate. X has an accepted offer and a pending approval request in each.
    """
    night = db.get(Shift, NIGHT_SHIFT)
    assert night is not None
    ward_b, headers_b = _add_other_ward_head_nurse(db)
    shift_b = Shift(
        id=(db.scalar(select(func.max(Shift.id))) or 0) + 1,
        ward_id=ward_b,
        patient_count=5,
        start_at=night.start_at - timedelta(hours=2),
        end_at=night.end_at - timedelta(hours=2),
        shift_type=ShiftType.NIGHT,
        is_active=True,
        merge_window_seconds=0,
    )
    db.add(shift_b)
    db.flush()
    requirement = StaffingRequirement(
        shift_id=shift_b.id, required_staff=1, minimum_staff=1, created_at=DEMO_NOW
    )
    db.add(requirement)
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=requirement.id, role_id=RN, required_count=1
        )
    )
    db.flush()

    ward_c = ward_b + 1
    db.add(Ward(id=ward_c, name="Lender", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    candidate_id = (db.scalar(select(func.max(Staff.id))) or 0) + 1
    db.add(
        Staff(
            id=candidate_id,
            first_name="Shared",
            last_name="Nurse",
            email=f"{candidate_id}@demo.local",
            password_hash="!",
            role_id=RN,
            home_ward_id=ward_c,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()

    # 105 leaves the night shift: one RN short in ICU
    cancel_roster(db, 105)
    approvals = []
    for shift_id in (NIGHT_SHIFT, shift_b.id):
        case = make_case(db, CaseStatus.WAITING_APPROVAL, shift_id=shift_id)
        record_gap(db, case)
        item = make_plan(db, case, (candidate_id,))[candidate_id]
        item.source = CandidateSource.CROSS_WARD
        offer(db, case, item, OutreachStatus.ACCEPTED)
        safety(db, case, item, passed=True)
        approvals.append(approval(db, case, item).id)
    return Scene(
        candidate_id=candidate_id,
        shift_ids=(NIGHT_SHIFT, shift_b.id),
        approval_ids=(approvals[0], approvals[1]),
        headers=(HEAD_A, headers_b),
    )


@pytest.fixture
def scene(frozen_clock: datetime) -> Iterator[Scene]:
    with SessionLocal.begin() as db:
        load(db)
        built = _build(db)
    try:
        yield built
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def _committed_rows(scene: Scene) -> int:
    with SessionLocal() as db:
        return len(
            list(
                db.scalars(
                    select(RosterAssignment.id).where(
                        RosterAssignment.staff_id == scene.candidate_id,
                        RosterAssignment.shift_id.in_(scene.shift_ids),
                        RosterAssignment.status.in_(COMMITTED_ROSTER_STATUSES),
                    )
                )
            )
        )


def _offer_statuses(scene: Scene) -> list[OutreachStatus]:
    with SessionLocal() as db:
        return list(
            db.scalars(select(CandidateOutreach.status).order_by(CandidateOutreach.case_id))
        )


def test_concurrent_decisions_never_assign_overlapping_shifts(scene: Scene) -> None:
    barrier = threading.Barrier(2, timeout=10)
    results: list[int] = []
    errors: list[Exception] = []

    def approve(index: int) -> None:
        try:
            with TestClient(app) as client:
                barrier.wait()
                results.append(
                    client.post(
                        f"/approvals/{scene.approval_ids[index]}/decision",
                        headers=scene.headers[index],
                        json={"approved": True},
                    ).status_code
                )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=approve, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [200, 409]
    assert _committed_rows(scene) == 1


def test_the_second_decision_finds_its_offer_cancelled(scene: Scene) -> None:
    with TestClient(app) as client:
        first = client.post(
            f"/approvals/{scene.approval_ids[0]}/decision",
            headers=scene.headers[0],
            json={"approved": True},
        )
        second = client.post(
            f"/approvals/{scene.approval_ids[1]}/decision",
            headers=scene.headers[1],
            json={"approved": True},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert _committed_rows(scene) == 1
    assert _offer_statuses(scene) == [OutreachStatus.ACCEPTED, OutreachStatus.CANCELLED]
