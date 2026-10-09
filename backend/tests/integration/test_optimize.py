"""The stub solver against the seeded PostgreSQL: the candidate plan and its audit row."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Shift,
    SoftConstraintPolicy,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import (
    ActorName,
    AuditAction,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
    StaffStatus,
)
from app.services.optimization_service import NoCandidatesError
from app.workflow import orchestrator
from app.workflow.handlers import optimize
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
DAY_SHIFT_ID = 2
LEAVING_STAFF_ID = 105


def _make_case(
    db: Session, status: CaseStatus = CaseStatus.OPTIMIZING, *, shift_id: int = SHIFT_ID
) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift_id,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=shift_id,
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
    # The real Outreach step runs next and waits for the answer
    assert case.status is CaseStatus.WAITING_RESPONSE
    [plan] = _plans(db, case)
    assert len(_items(db, plan)) == 3
    solver_row, status_row = _audit(db, case)[:2]
    assert solver_row.action is AuditAction.SOLVER_EXECUTED
    assert status_row.action is AuditAction.CASE_STATUS_CHANGED
    assert status_row.payload == {"from": "OPTIMIZING", "to": "OUTREACH"}


# --------------------------------------------------------------------------- #
# Candidates who cannot take the case's shift are dropped, ranks stay 1..n
# --------------------------------------------------------------------------- #
def _candidates(db: Session, case: StaffingCase) -> list[tuple[int, int]]:
    [plan] = _plans(db, case)
    return [(item.staff_id, item.rank) for item in _items(db, plan)]


def _deactivate(db: Session, *staff_ids: int) -> None:
    for staff_id in staff_ids:
        staff = db.get(Staff, staff_id)
        assert staff is not None
        staff.status = StaffStatus.INACTIVE
    db.flush()


def _unavailable(
    db: Session, staff_id: int, shift_id: int, *, start: timedelta, end: timedelta | None
) -> None:
    """Unavailability from shift start + `start` to shift start + `end` (None = open-ended)."""
    shift = db.get(Shift, shift_id)
    assert shift is not None
    db.add(
        StaffUnavailability(
            staff_id=staff_id,
            start_at=shift.start_at + start,
            end_at=None if end is None else shift.start_at + end,
            reason=AvailabilityReason.PLANNED_LEAVE,
        )
    )
    db.flush()


def test_staff_already_on_the_shift_are_dropped(seeded: Session) -> None:
    """202 and 203 are ASSIGNED on shift 2 in the Golden Case seed."""
    case = _make_case(seeded, shift_id=DAY_SHIFT_ID)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1)]


def test_inactive_staff_are_dropped_and_the_rest_move_up(seeded: Session) -> None:
    case = _make_case(seeded)
    _deactivate(seeded, 201)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(202, 1), (203, 2)]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (timedelta(hours=-1), timedelta(hours=2)),
        (timedelta(hours=-1), None),
        (timedelta(hours=7, minutes=59), timedelta(days=1)),
    ],
    ids=["covers_the_start", "open_ended", "starts_before_the_end"],
)
def test_staff_unavailable_during_the_shift_are_dropped(
    seeded: Session, start: timedelta, end: timedelta | None
) -> None:
    case = _make_case(seeded)
    _unavailable(seeded, 202, SHIFT_ID, start=start, end=end)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (203, 2)]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (timedelta(hours=-5), timedelta(0)),
        (timedelta(hours=8), None),
    ],
    ids=["ends_at_the_start", "starts_at_the_end"],
)
def test_unavailability_that_only_touches_the_shift_keeps_the_candidate(
    seeded: Session, start: timedelta, end: timedelta | None
) -> None:
    """Shift 1 runs 8 hours; touching an edge is not an overlap."""
    case = _make_case(seeded)
    _unavailable(seeded, 202, SHIFT_ID, start=start, end=end)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (202, 2), (203, 3)]


def test_no_candidate_left_raises_before_writing_a_plan(seeded: Session) -> None:
    case = _make_case(seeded)
    _deactivate(seeded, 201, 202, 203)

    with pytest.raises(NoCandidatesError):
        optimize.handle(seeded, case)

    assert _plans(seeded, case) == []


def test_no_candidate_left_fails_the_case(seeded: Session) -> None:
    """Section 5 has no transition for it yet, so D11 records the failure."""
    case = _make_case(seeded)
    _deactivate(seeded, 201, 202, 203)

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.status is CaseStatus.FAILED
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["failed_at"] == "OPTIMIZING"
    assert failure.payload["error_type"] == "NoCandidatesError"
    assert _plans(seeded, case) == []


# --------------------------------------------------------------------------- #
# Rule 4: candidates who already hold an open offer are dropped
# --------------------------------------------------------------------------- #
def _offered_staff(db: Session, case: StaffingCase) -> list[int]:
    query = (
        select(CandidateItem.staff_id)
        .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
        .where(CandidateOutreach.case_id == case.id)
    )
    return list(db.scalars(query))


def _open_offer(
    db: Session, staff_id: int, *, offer_status: OutreachStatus, case_status: CaseStatus
) -> None:
    """Another case on shift 1 whose offer to `staff_id` has `offer_status`."""
    other = _make_case(db, case_status)
    plan = CandidatePlan(
        case_id=other.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="stub",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=staff_id,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=SHIFT_ID,
    )
    db.add(item)
    db.flush()
    db.add(
        CandidateOutreach(
            case_id=other.id,
            candidate_item_id=item.id,
            channel=Channel.LINE,
            sent_at=DEMO_NOW,
            status=offer_status,
        )
    )
    db.flush()


def test_second_case_on_the_shift_offers_the_next_candidate(seeded: Session) -> None:
    """Seam 3 needs exactly one SENT offer per responder, so 201 is not offered twice."""
    first = _make_case(seeded)
    second = _make_case(seeded)

    orchestrator.advance(seeded, first.id)
    orchestrator.advance(seeded, second.id)

    seeded.expire_all()
    assert first.status is CaseStatus.WAITING_RESPONSE
    assert second.status is CaseStatus.WAITING_RESPONSE
    assert _candidates(seeded, second) == [(202, 1), (203, 2)]
    assert _offered_staff(seeded, first) == [201]
    assert _offered_staff(seeded, second) == [202]


@pytest.mark.parametrize(
    ("offer_status", "case_status", "dropped"),
    [
        (OutreachStatus.SENT, CaseStatus.WAITING_RESPONSE, True),
        (OutreachStatus.SENT, CaseStatus.FAILED, True),
        (OutreachStatus.ACCEPTED, CaseStatus.WAITING_APPROVAL, True),
        (OutreachStatus.ACCEPTED, CaseStatus.FAILED, False),
        (OutreachStatus.ACCEPTED, CaseStatus.RESOLVED, False),
        (OutreachStatus.REJECTED, CaseStatus.WAITING_RESPONSE, False),
    ],
    ids=[
        "sent",
        "sent_in_a_stopped_case",
        "accepted_in_a_running_case",
        "accepted_in_a_failed_case",
        "accepted_in_a_resolved_case",
        "rejected",
    ],
)
def test_which_offers_count_as_open(
    seeded: Session, offer_status: OutreachStatus, case_status: CaseStatus, dropped: bool
) -> None:
    case = _make_case(seeded)
    _open_offer(seeded, 201, offer_status=offer_status, case_status=case_status)

    optimize.handle(seeded, case)

    if dropped:
        assert _candidates(seeded, case) == [(202, 1), (203, 2)]
    else:
        assert _candidates(seeded, case) == [(201, 1), (202, 2), (203, 3)]


def test_everyone_holding_an_open_offer_fails_the_case(seeded: Session) -> None:
    case = _make_case(seeded)
    for staff_id in (201, 202, 203):
        _open_offer(
            seeded,
            staff_id,
            offer_status=OutreachStatus.SENT,
            case_status=CaseStatus.WAITING_RESPONSE,
        )

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.status is CaseStatus.FAILED
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["failed_at"] == "OPTIMIZING"
    assert failure.payload["error_type"] == "NoCandidatesError"
    assert _plans(seeded, case) == []
