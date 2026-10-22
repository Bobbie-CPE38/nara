"""Run the real Golden HTTP flow before/after import; no external LINE/LLM calls."""

import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    Attendance,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Shift,
    StructuredHandover,
)
from app.main import app
from app.seed.large_demo import STAFF_BASE, generate
from app.services import optimization_service
from tests.integration.test_orchestrator_graph_parity import GOLDEN, Driver


@pytest.mark.parametrize("large", [False, True], ids=["baseline", "after-import"])
def test_golden_candidates_and_complete_flow(production_seeded: Session, large: bool) -> None:
    db = production_seeded
    if large:
        generate(db, clock.now())
        db.commit()
    shift = db.get(Shift, 1)
    assert shift is not None
    pool = optimization_service._pool(db, shift)

    def request_db() -> Iterator[Session]:
        with Session(
            bind=db.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as request_session:
            yield request_session

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app) as client:
            run = Driver(client, db)
            assert run.report_leave()["case_status"] == "WAITING_RESPONSE"
            db.expire_all()
            plan = db.scalars(
                select(CandidatePlan).where(CandidatePlan.case_id == run.case_id)
            ).one()
            items = db.scalars(
                select(CandidateItem)
                .where(CandidateItem.plan_id == plan.id)
                .order_by(CandidateItem.rank)
            ).all()
            offers = db.execute(
                select(CandidateItem.staff_id, CandidateOutreach.status)
                .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
                .where(CandidateOutreach.case_id == run.case_id)
            ).all()
            print(
                json.dumps(
                    {
                        "large": large,
                        "pool_count": len(pool),
                        "mock_in_pool": sum(staff_id > STAFF_BASE for staff_id in pool),
                        "ranked_count": len(items),
                        "mock_ranked_count": sum(item.staff_id > STAFF_BASE for item in items),
                        "top10": [
                            (item.staff_id, item.rank, item.source.value) for item in items[:10]
                        ],
                        "outreach": [(row.staff_id, row.status.value) for row in offers],
                        "solver_status": plan.solver_status.value,
                        "objective": str(plan.objective_score),
                    }
                )
            )
            assert [(item.staff_id, item.rank) for item in items[:3]] == [
                (201, 1),
                (202, 2),
                (203, 3),
            ]
            assert len(pool) == (514 if large else 14)
            assert sum(staff_id > STAFF_BASE for staff_id in pool) == (500 if large else 0)
            assert len(items) == (123 if large else 3)
            assert sum(item.staff_id > STAFF_BASE for item in items) == (120 if large else 0)
            assert all(
                item.source.value == "CROSS_WARD" for item in items if item.staff_id > STAFF_BASE
            )
            assert plan.solver_status.value == "OPTIMAL"
            assert plan.objective_score == 2023
            assert {row.staff_id for row in offers} == {201, 202}
            assert run.answer(201, "ACCEPT") == "WAITING_APPROVAL"
            assert run.decide(201, approved=True) == "RESOLVED"
            assert run.transitions() == GOLDEN
            handover = db.scalars(
                select(StructuredHandover).where(StructuredHandover.case_id == run.case_id)
            ).one()
            assert handover.incoming_staff_id == 201
            clock.set_time(shift.start_at + timedelta(minutes=7))
            checked = client.post(
                "/me/attendance/check-in", headers={"X-Demo-User": "201"}, json={"shift_id": 1}
            )
            assert checked.status_code == 200, checked.text
            assert checked.json()["on_time"] is True
            assert (
                db.scalars(
                    select(Attendance).where(Attendance.staff_id == 201, Attendance.shift_id == 1)
                ).one()
                is not None
            )
    finally:
        app.dependency_overrides.clear()
