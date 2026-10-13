"""The round 1 Solver against the seeded PostgreSQL: the candidate plan, its target rows,
its snapshots and its audit rows."""

import contextlib
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidateItemTarget,
    CandidateOutreach,
    CandidatePlan,
    OutreachPolicy,
    Shift,
    SoftConstraintPolicy,
    Staff,
    StaffingCase,
    StaffingRequirementSkill,
    StaffUnavailability,
    StaffWorkingTimeSnapshot,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorName,
    AuditAction,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    OutreachStatus,
    SelectionType,
    SolverStatus,
    StaffStatus,
    TargetType,
)
from app.seed import load
from app.workflow import orchestrator
from app.workflow.handlers import optimize
from tests.integration.case_rows import cancel_roster, leave, make_case, record_gap
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
DAY_SHIFT_ID = 2
LEAVING_STAFF_ID = 105
RN, ICU = 1, 1


def _case_with_gap(db: Session, *, shift_id: int = SHIFT_ID) -> StaffingCase:
    """A case at OPTIMIZING with the current gap of its shift recorded."""
    case = make_case(db, CaseStatus.OPTIMIZING, shift_id=shift_id)
    record_gap(db, case)
    return case


def _make_case(db: Session, *leaving: int, shift_id: int = SHIFT_ID) -> StaffingCase:
    """A case whose gap is what the given staff left behind (105 by default)."""
    for staff_id in leaving or (LEAVING_STAFF_ID,):
        leave(db, staff_id, shift_id)
    return _case_with_gap(db, shift_id=shift_id)


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


def _candidates(db: Session, case: StaffingCase) -> list[tuple[int, int]]:
    [plan] = _plans(db, case)
    return [(item.staff_id, item.rank) for item in _items(db, plan)]


def _targets(
    db: Session, case: StaffingCase
) -> dict[int, list[tuple[TargetType, int | None, str]]]:
    """staff ID -> (type, role or skill ID, selection type) of each target row, by row id."""
    [plan] = _plans(db, case)
    rows = db.execute(
        select(
            CandidateItem.staff_id,
            CandidateItemTarget.target_type,
            CandidateItemTarget.role_id,
            CandidateItemTarget.skill_id,
            CandidateItemTarget.selection_type,
        )
        .join(CandidateItem, CandidateItem.id == CandidateItemTarget.candidate_item_id)
        .where(CandidateItem.plan_id == plan.id)
        .order_by(CandidateItemTarget.id)
    )
    result: dict[int, list[tuple[TargetType, int | None, str]]] = {}
    for staff_id, target_type, role_id, skill_id, selection in rows:
        result.setdefault(staff_id, []).append((target_type, role_id or skill_id, selection.value))
    return result


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


P, R = SelectionType.PRIMARY.value, SelectionType.RESERVE.value


# --------------------------------------------------------------------------- #
# The plan of the Golden Case
# --------------------------------------------------------------------------- #
def test_requests_outreach_without_touching_the_case(seeded: Session) -> None:
    case = _make_case(seeded)

    result = optimize.handle(seeded, case)

    assert result.next_status is CaseStatus.OUTREACH
    assert result.wait is False
    assert case.status is CaseStatus.OPTIMIZING


def test_writes_one_feasible_plan(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    assert plan.solver_status is SolverStatus.FEASIBLE
    assert plan.solver_version == "weighted-v1"
    assert plan.execution_time_ms >= 0
    assert plan.objective_score == 2023
    assert plan.hard_constraint_policy_id == 1
    assert plan.soft_constraint_policy_id == 1
    assert plan.generated_at == DEMO_NOW
    snapshot = plan.input_snapshot
    assert snapshot["captured_at"] == DEMO_NOW.isoformat()
    assert snapshot["week_start"] == "2026-10-05T00:00:00+07:00"
    assert snapshot["targets"] == {
        "headcount": {"gap": 1, "target": 2},
        "roles": [{"role_id": 1, "gap": 1, "target": 2}],
        "skills": [],
    }
    assert [row["staff_id"] for row in snapshot["candidates"]] == [201, 202, 203]
    assert [row["first_wave"] for row in snapshot["candidates"]] == [True, True, False]
    assert [row["penalty"] for row in snapshot["candidates"]] == [1005, 1018, 1018]
    assert snapshot["skipped"] == [
        {"staff_id": 101, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 102, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 103, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 104, "reason": "ALREADY_ON_SHIFT"},
        {"staff_id": 105, "reason": "UNAVAILABLE"},
        {"staff_id": 900, "reason": "ROLE_MISMATCH"},
    ]


def test_plan_ranks_the_golden_case_candidates_for_the_case_shift(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    items = _items(seeded, plan)
    assert [(item.staff_id, item.rank) for item in items] == [(201, 1), (202, 2), (203, 3)]
    assert {item.source for item in items} == {CandidateSource.SAME_WARD}
    assert {item.proposed_shift_id for item in items} == {case.shift_id}


def test_the_first_wave_gets_target_rows(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    assert _targets(seeded, case) == {
        201: [(TargetType.ROLE, RN, P), (TargetType.HEADCOUNT, None, P)],
        202: [(TargetType.ROLE, RN, R), (TargetType.HEADCOUNT, None, R)],
    }


def test_every_item_links_the_snapshot_it_was_ranked_with(seeded: Session) -> None:
    case = _make_case(seeded)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    for item in _items(seeded, plan):
        assert item.working_time_snapshot_id is not None
        snapshot = seeded.get(StaffWorkingTimeSnapshot, item.working_time_snapshot_id)
        assert snapshot is not None
        assert snapshot.staff_id == item.staff_id
        assert snapshot.captured_at == DEMO_NOW
        assert snapshot.hours_this_week == (8 if item.staff_id in (202, 203) else 0)


def test_skill_gap_picks_the_staff_with_the_skill(seeded: Session) -> None:
    case = _make_case(seeded, 101)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (203, 2), (202, 3)]
    assert _targets(seeded, case) == {
        201: [
            (TargetType.SKILL, ICU, P),
            (TargetType.ROLE, RN, P),
            (TargetType.HEADCOUNT, None, P),
        ],
        203: [
            (TargetType.SKILL, ICU, R),
            (TargetType.ROLE, RN, R),
            (TargetType.HEADCOUNT, None, R),
        ],
    }


def test_the_pool_is_the_ward_of_the_shift(seeded: Session) -> None:
    case = _make_case(seeded, 202, 203, shift_id=DAY_SHIFT_ID)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [
        (201, 1),
        (101, 2),
        (102, 3),
        (103, 4),
        (104, 5),
        (105, 6),
    ]


def test_a_candidate_who_fills_nothing_is_left_out(seeded: Session) -> None:
    """Only ICU is short: 202 passes the Hard Rules but has no ICU."""
    requirement = seeded.get(StaffingRequirementSkill, (1, ICU))
    assert requirement is not None
    requirement.required_count = 3
    seeded.flush()
    case = _case_with_gap(seeded)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (203, 2)]
    assert _targets(seeded, case) == {
        201: [(TargetType.SKILL, ICU, P)],
        203: [(TargetType.SKILL, ICU, R)],
    }
    [plan] = _plans(seeded, case)
    assert {"staff_id": 202, "reason": "SKILL_MISMATCH"} in plan.input_snapshot["skipped"]


def test_the_first_failed_rule_is_the_reason(seeded: Session) -> None:
    case = _make_case(seeded)
    _deactivate(seeded, 101)

    optimize.handle(seeded, case)

    [plan] = _plans(seeded, case)
    assert {"staff_id": 101, "reason": "STAFF_NOT_ACTIVE"} in plan.input_snapshot["skipped"]


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


def test_a_case_without_a_gap_fails(seeded: Session) -> None:
    case = make_case(seeded, CaseStatus.OPTIMIZING)

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.status is CaseStatus.FAILED
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["error_type"] == "GapNotFoundError"
    assert _plans(seeded, case) == []


# --------------------------------------------------------------------------- #
# Candidates who cannot take the case's shift are dropped, ranks stay 1..n
# --------------------------------------------------------------------------- #
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


def test_staff_taken_off_the_shift_are_not_offered_it_again(seeded: Session) -> None:
    """ASSIGNMENT_CANCELLED cancels the roster row and records no leave."""
    cancel_roster(seeded, 104)
    case = _case_with_gap(seeded)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (202, 2), (203, 3)]
    [plan] = _plans(seeded, case)
    assert {"staff_id": 104, "reason": "UNAVAILABLE"} in plan.input_snapshot["skipped"]


# --------------------------------------------------------------------------- #
# The offer cap, and the interim open-offer rule (until PR 2b)
# --------------------------------------------------------------------------- #
def _open_offer(
    db: Session, staff_id: int, *, offer_status: OutreachStatus, case_status: CaseStatus
) -> None:
    """Another case on shift 1 whose offer to `staff_id` has `offer_status`."""
    other = make_case(db, case_status)
    plan = CandidatePlan(
        case_id=other.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="test",
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


def _offers(db: Session, staff_id: int, count: int, **kwargs: object) -> None:
    for _ in range(count):
        _open_offer(db, staff_id, **kwargs)  # type: ignore[arg-type]


def test_a_candidate_at_the_offer_cap_is_left_out(seeded: Session) -> None:
    case = _make_case(seeded)
    _offers(
        seeded, 201, 3, offer_status=OutreachStatus.SENT, case_status=CaseStatus.WAITING_RESPONSE
    )

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(202, 1), (203, 2)]
    [plan] = _plans(seeded, case)
    assert {"staff_id": 201, "reason": "OFFER_LIMIT_REACHED"} in plan.input_snapshot["skipped"]


def test_offers_of_stopped_cases_do_not_count(seeded: Session) -> None:
    case = _make_case(seeded)
    _offers(seeded, 201, 3, offer_status=OutreachStatus.ACCEPTED, case_status=CaseStatus.RESOLVED)

    optimize.handle(seeded, case)

    assert _candidates(seeded, case) == [(201, 1), (202, 2), (203, 3)]


@pytest.mark.parametrize(
    ("offer_status", "case_status", "dropped"),
    [
        (OutreachStatus.SENT, CaseStatus.WAITING_RESPONSE, False),
        (OutreachStatus.SENT, CaseStatus.FAILED, False),
        (OutreachStatus.ACCEPTED, CaseStatus.WAITING_APPROVAL, False),
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

    [plan] = _plans(seeded, case)
    if dropped:
        assert _candidates(seeded, case) == [(202, 1), (203, 2)]
        assert {"staff_id": 201, "reason": "OFFER_LIMIT_REACHED"} in plan.input_snapshot["skipped"]
    else:
        assert _candidates(seeded, case) == [(201, 1), (202, 2), (203, 3)]


def test_second_case_can_offer_same_staff_below_limit(seeded: Session) -> None:
    """The cap is three; an unanswered offer does not exclude a candidate."""
    first = _make_case(seeded)
    second = _case_with_gap(seeded)

    orchestrator.advance(seeded, first.id)
    orchestrator.advance(seeded, second.id)

    seeded.expire_all()
    assert first.status is CaseStatus.WAITING_RESPONSE
    assert second.status is CaseStatus.WAITING_RESPONSE
    assert _candidates(seeded, first) == [(201, 1), (202, 2), (203, 3)]
    assert _candidates(seeded, second) == [(201, 1), (202, 2), (203, 3)]


# --------------------------------------------------------------------------- #
# Nobody can take the shift (T6)
# --------------------------------------------------------------------------- #
def test_nobody_left_stops_the_case_at_manual_handoff(seeded: Session) -> None:
    case = _make_case(seeded)
    _deactivate(seeded, 201, 202, 203)

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.status is CaseStatus.MANUAL_HANDOFF
    [plan] = _plans(seeded, case)
    assert plan.solver_status is SolverStatus.INFEASIBLE
    assert plan.objective_score is None
    assert _items(seeded, plan) == []
    rows = [
        row for row in _audit(seeded, case) if row.action is not AuditAction.CASE_STATUS_CHANGED
    ]
    assert [row.action for row in rows] == [AuditAction.SOLVER_EXECUTED, AuditAction.MANUAL_HANDOFF]
    assert rows[0].payload == {
        "plan_id": plan.id,
        "solver_status": "INFEASIBLE",
        "candidate_count": 0,
    }
    handoff = rows[1]
    solver_actor = seeded.scalar(
        select(Actor.id).where(Actor.name == ActorName.CONSTRAINT_FAIR_SCHEDULING_AGENT.value)
    )
    assert handoff.actor_id == solver_actor
    assert handoff.entity_type is EntityType.STAFFING_CASES
    assert handoff.entity_id == case.id
    assert handoff.payload == {
        "reason": "NO_FEASIBLE_PLAN",
        "stopped_at": "OPTIMIZING",
        "cancelled_outreach_ids": [],
        "skipped": [
            {"staff_id": 101, "reason": "ALREADY_ON_SHIFT"},
            {"staff_id": 102, "reason": "ALREADY_ON_SHIFT"},
            {"staff_id": 103, "reason": "ALREADY_ON_SHIFT"},
            {"staff_id": 104, "reason": "ALREADY_ON_SHIFT"},
            {"staff_id": 105, "reason": "UNAVAILABLE"},
            {"staff_id": 201, "reason": "STAFF_NOT_ACTIVE"},
            {"staff_id": 202, "reason": "STAFF_NOT_ACTIVE"},
            {"staff_id": 203, "reason": "STAFF_NOT_ACTIVE"},
            {"staff_id": 900, "reason": "ROLE_MISMATCH"},
        ],
    }
    assert seeded.scalar(select(CandidateOutreach.id)) is None
    orchestrator.advance(seeded, case.id)
    assert case.status is CaseStatus.MANUAL_HANDOFF
    assert len(_plans(seeded, case)) == 1


# --------------------------------------------------------------------------- #
# Two rounds planning at the same moment (separate committed transactions)
# --------------------------------------------------------------------------- #
@pytest.fixture
def committed_optimizing_cases(frozen_clock: datetime) -> Iterator[tuple[int, int]]:
    """Two committed cases at OPTIMIZING on the night shift, with the offer cap set to 1.

    The other tests share one rolled-back connection, which cannot show two
    transactions racing. This one commits, so it empties every table afterwards.
    """
    with SessionLocal.begin() as db:
        load(db)
        policy = db.get(OutreachPolicy, 1)
        assert policy is not None
        policy.maximum_concurrent_offers_per_staff = 1
        case_ids = (_make_case(db).id, _case_with_gap(db).id)
    try:
        yield case_ids
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_two_cases_planned_at_once_never_offer_the_same_candidate(
    committed_optimizing_cases: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the cap at 1, both rounds would offer 201 if they counted offers at once.

    Each round waits for the other right after the cap check. Without the STAFF
    row lock both get there and the race is certain. With it, the second round is
    still waiting for the lock, so the first gives up waiting and commits its
    offer, and the second then sees 201 at the cap.
    """
    from app.services import availability_service

    check = availability_service.staff_at_offer_limit
    both_checked = threading.Barrier(2, timeout=2)

    def check_then_wait(db: Session, staff_ids: list[int]) -> set[int]:
        at_limit = check(db, staff_ids)
        # A timeout means the other round is blocked on the lock: the fix at work
        with contextlib.suppress(threading.BrokenBarrierError):
            both_checked.wait()
        return at_limit

    monkeypatch.setattr(availability_service, "staff_at_offer_limit", check_then_wait)
    errors: list[BaseException] = []

    def plan(case_id: int) -> None:
        try:
            with SessionLocal() as db:
                orchestrator.advance(db, case_id)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=plan, args=(case_id,)) for case_id in committed_optimizing_cases
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    with SessionLocal() as db:
        sent = list(
            db.scalars(
                select(CandidateItem.staff_id)
                .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
                .where(CandidateOutreach.status == OutreachStatus.SENT)
            )
        )
        assert len(sent) == len(set(sent)) == 3, f"a candidate exceeded the cap: {sent}"
        for case_id in committed_optimizing_cases:
            case = db.get(StaffingCase, case_id)
            assert case is not None
            assert case.status is CaseStatus.WAITING_RESPONSE
