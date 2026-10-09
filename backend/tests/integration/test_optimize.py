"""The stub solver against the seeded PostgreSQL: the candidate plan and its audit row."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidatePlan,
    SoftConstraintPolicy,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    ActorName,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
    SolverStatus,
)
from app.workflow import orchestrator
from app.workflow.handlers import optimize
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
LEAVING_STAFF_ID = 105


def _make_case(db: Session, status: CaseStatus = CaseStatus.OPTIMIZING) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=SHIFT_ID,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=SHIFT_ID,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


def _plans(db: Session, case: StaffingCase) -> list[CandidatePlan]:
    return list(
        db.scalars(
            select(CandidatePlan).where(CandidatePlan.case_id == case.id).order_by(CandidatePlan.id)
        )
    )


def _items(db: Session, plan: CandidatePlan) -> list[CandidateItem]:
    query = select(CandidateItem).where(CandidateItem.plan_id == plan.id)
    return list(db.scalars(query.order_by(CandidateItem.rank)))


def _audit(db: Session, case: StaffingCase) -> list[AuditLog]:
    # Ordered by id: the frozen demo clock gives every row the same created_at
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


def test_requests_outreach_without_touching_the_case(seeded: Session) -> None:
    case = _make_case(seeded)

    result = optimize.handle(seeded, case)

    assert result.next_status is CaseStatus.OUTREACH
    assert result.wait is False
    assert case.status is CaseStatus.OPTIMIZING


def test_writes_one_feasible_stub_plan(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    assert plan.solver_status is SolverStatus.FEASIBLE
    assert plan.solver_version == "stub"
    assert plan.execution_time_ms == 0
    assert plan.objective_score is None
    assert plan.hard_constraint_policy_id == 1
    assert plan.soft_constraint_policy_id == 1
    assert plan.input_snapshot == {}
    assert plan.generated_at == DEMO_NOW


def test_plan_ranks_the_golden_case_candidates_for_the_case_shift(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    items = _items(seeded, plan)
    assert [(item.staff_id, item.rank) for item in items] == [(201, 1), (202, 2), (203, 3)]
    assert {item.source for item in items} == {CandidateSource.SAME_WARD}
    assert {item.proposed_shift_id for item in items} == {case.shift_id}


def test_outreach_finds_rank_one_of_the_latest_plan(seeded: Session) -> None:
    """Seams 1 and 2 as Outreach reads them: highest plan id, then exactly one rank 1."""
    case = _make_case(seeded)

    optimize.handle(seeded, case)
    optimize.handle(seeded, case)

    latest = seeded.scalars(
        select(CandidatePlan)
        .where(CandidatePlan.case_id == case.id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    ).one()
    assert latest.id == _plans(seeded, case)[-1].id
    first_choice = seeded.scalars(
        select(CandidateItem).where(CandidateItem.plan_id == latest.id, CandidateItem.rank == 1)
    ).one()
    assert first_choice.staff_id == 201


def test_logs_solver_executed(seeded: Session) -> None:
    case = _make_case(seeded)
    solver_actor = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.CONSTRAINT_FAIR_SCHEDULING_AGENT.value)
    )

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    [row] = _audit(seeded, case)
    assert row.action is AuditAction.SOLVER_EXECUTED
    assert row.actor_id == solver_actor
    assert row.entity_type is EntityType.CANDIDATE_PLANS
    assert row.entity_id == plan.id
    assert row.payload == {"plan_id": plan.id, "solver_status": "FEASIBLE", "candidate_count": 3}


def test_missing_soft_policy_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    policy = seeded.get(SoftConstraintPolicy, 1)
    assert policy is not None
    seeded.delete(policy)
    seeded.flush()

    with pytest.raises(LookupError, match="Soft constraint policy"):
        optimize.handle(seeded, case)


def test_advance_with_production_session_settings(production_seeded: Session) -> None:
    """Autoflush off: the plan id must be flushed before the items and the audit row."""
    db = production_seeded
    case = _make_case(db)

    orchestrator.advance(db, case.id)

    db.expire_all()
    # Outreach is still a stub: WAITING_RESPONSE holds once it is real too
    assert case.status is CaseStatus.WAITING_RESPONSE
    [plan] = _plans(db, case)
    assert len(_items(db, plan)) == 3
    solver_row, status_row = _audit(db, case)[:2]
    assert solver_row.action is AuditAction.SOLVER_EXECUTED
    assert status_row.action is AuditAction.CASE_STATUS_CHANGED
    assert status_row.payload == {"from": "OPTIMIZING", "to": "OUTREACH"}
