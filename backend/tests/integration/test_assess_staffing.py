"""The ASSESSING step on the seeded Golden Case: the stored gap and its audit row
(docs/workflow.md, sections 5.1, 7 and 8)."""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    Actor,
    AuditLog,
    HardConstraintPolicy,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapRole,
    StaffingGapSkill,
)
from app.domain.enums import (
    GOLDEN_PATH_AUDIT_ACTIONS,
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
    RosterStatus,
)
from app.main import app
from app.services import requirement_service
from app.workflow import orchestrator
from app.workflow.handlers import assess_staffing
from app.workflow.handlers.assess_staffing import NoGapError
from tests.integration.conftest import DEMO_NOW, STUB_STEPS, returns

RN, ICU = 1, 1
NIGHT_SHIFT = 1
LEAVING_STAFF_ID = 105
ICU_STAFF_ID = 101


def _cancel(db: Session, staff_id: int) -> None:
    row = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()
    row.status = RosterStatus.CANCELLED


def _make_case(db: Session, status: CaseStatus = CaseStatus.ASSESSING) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=NIGHT_SHIFT,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


@pytest.fixture
def case(production_seeded: Session) -> StaffingCase:
    """A case on the night shift after 105 left it, the way event intake leaves it.

    The roster change is not flushed: the session has autoflush off, like
    SessionLocal, so the handler must see it anyway.
    """
    row = _make_case(production_seeded)
    _cancel(production_seeded, LEAVING_STAFF_ID)
    return row


def _gaps(db: Session, case: StaffingCase) -> list[StaffingGap]:
    return list(
        db.scalars(
            select(StaffingGap).where(StaffingGap.case_id == case.id).order_by(StaffingGap.id)
        )
    )


def _audits(db: Session, case: StaffingCase) -> list[AuditLog]:
    # Ordered by id: the frozen demo clock gives every row the same created_at
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------- #
# The handler
# --------------------------------------------------------------------------- #
def test_handler_requests_optimization_without_commit_or_status_change(
    production_seeded: Session, case: StaffingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_commit() -> None:
        raise AssertionError("a handler must not commit")

    monkeypatch.setattr(production_seeded, "commit", no_commit)

    result = assess_staffing.handle(production_seeded, case)

    assert result.next_status is CaseStatus.OPTIMIZING
    assert result.wait is False
    assert case.status is CaseStatus.ASSESSING


def test_handler_stores_the_gap_with_the_inputs_it_was_computed_from(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    requirement = requirement_service.get_current_requirement(db, NIGHT_SHIFT).requirement

    assess_staffing.handle(db, case)

    (gap,) = _gaps(db, case)
    assert gap.staffing_requirement_id == requirement.id
    # ceil(10 patients / 2 per nurse) = 5 needed, 4 left after 105
    assert gap.headcount_gap == 1
    assert gap.patient_count == 10
    assert gap.patients_per_nurse == Decimal(2)
    assert gap.computed_at == DEMO_NOW


def test_handler_stores_every_required_role_and_skill_also_without_a_shortage(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded

    assess_staffing.handle(db, case)

    (gap,) = _gaps(db, case)
    roles = db.scalars(select(StaffingGapRole).where(StaffingGapRole.gap_id == gap.id)).all()
    skills = db.scalars(select(StaffingGapSkill).where(StaffingGapSkill.gap_id == gap.id)).all()
    assert [(r.role_id, r.required_count, r.current_count, r.gap_count) for r in roles] == [
        (RN, 5, 4, 1)
    ]
    # 105 has no ICU skill, so both ICU nurses are still on the shift
    assert [(s.skill_id, s.required_count, s.current_count, s.gap_count) for s in skills] == [
        (ICU, 2, 2, 0)
    ]


def test_handler_writes_the_gap_assessed_audit_row(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded

    assess_staffing.handle(db, case)

    (gap,) = _gaps(db, case)
    (audit,) = _audits(db, case)
    actor = db.get(Actor, audit.actor_id)
    assert actor is not None
    assert actor.name == ActorName.STAFFING_GAP_ASSESSMENT_AGENT.value
    assert audit.action is AuditAction.GAP_ASSESSED
    assert audit.entity_type is EntityType.STAFFING_GAP
    assert audit.entity_id == gap.id
    assert audit.payload == {
        "gap_id": gap.id,
        "headcount_gap": 1,
        "role_gaps": [{"role_id": RN, "required_count": 5, "current_count": 4, "gap_count": 1}],
        "skill_gaps": [{"skill_id": ICU, "required_count": 2, "current_count": 2, "gap_count": 0}],
    }


def test_skill_shortage_is_stored_next_to_the_headcount_gap(production_seeded: Session) -> None:
    db = production_seeded
    case = _make_case(db)
    _cancel(db, ICU_STAFF_ID)

    assess_staffing.handle(db, case)

    (gap,) = _gaps(db, case)
    skill = db.scalars(select(StaffingGapSkill).where(StaffingGapSkill.gap_id == gap.id)).one()
    assert gap.headcount_gap == 1
    assert (skill.required_count, skill.current_count, skill.gap_count) == (2, 1, 1)


def test_snapshot_keeps_the_values_of_the_calculation_when_the_sources_change_later(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    assess_staffing.handle(db, case)

    shift = db.get(Shift, NIGHT_SHIFT)
    policy = db.get(HardConstraintPolicy, 1)
    assert shift is not None
    assert policy is not None
    shift.patient_count = 40
    policy.maximum_patients_per_nurse = Decimal(4)
    db.flush()
    db.expire_all()

    (gap,) = _gaps(db, case)
    assert (gap.patient_count, gap.patients_per_nurse) == (10, Decimal(2))


def test_covered_shift_raises_and_writes_nothing(production_seeded: Session) -> None:
    db = production_seeded
    case = _make_case(db)

    with pytest.raises(NoGapError, match=f"case {case.id}"):
        assess_staffing.handle(db, case)

    assert _gaps(db, case) == []
    assert _audits(db, case) == []


# --------------------------------------------------------------------------- #
# Inside an orchestrator round
# --------------------------------------------------------------------------- #
@pytest.fixture
def only_assessing_is_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every handler except assess_staffing, so the round stops on its own."""
    for status, (next_status, wait) in STUB_STEPS.items():
        if status is not CaseStatus.ASSESSING:
            monkeypatch.setitem(
                orchestrator.HANDLERS, status, returns(next_status=next_status, wait=wait)
            )


@pytest.mark.usefixtures("only_assessing_is_real")
def test_round_records_the_gap_between_the_two_status_changes(production_seeded: Session) -> None:
    db = production_seeded
    case = _make_case(db, CaseStatus.OPEN)
    _cancel(db, LEAVING_STAFF_ID)

    orchestrator.advance(db, case.id)

    assert case.status is CaseStatus.WAITING_RESPONSE
    assert len(_gaps(db, case)) == 1
    assert [
        (row.action, row.payload.get("to"))
        for row in _audits(db, case)
        if row.action in (AuditAction.GAP_ASSESSED, AuditAction.CASE_STATUS_CHANGED)
    ][:3] == [
        (AuditAction.CASE_STATUS_CHANGED, "ASSESSING"),
        (AuditAction.GAP_ASSESSED, None),
        (AuditAction.CASE_STATUS_CHANGED, "OPTIMIZING"),
    ]


@pytest.mark.usefixtures("only_assessing_is_real")
def test_covered_shift_fails_the_case_without_a_gap_row(production_seeded: Session) -> None:
    db = production_seeded
    case = _make_case(db, CaseStatus.OPEN)

    orchestrator.advance(db, case.id)

    assert case.status is CaseStatus.FAILED
    assert _gaps(db, case) == []
    failure = _audits(db, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["failed_at"] == "ASSESSING"
    assert failure.payload["error_type"] == "NoGapError"


@pytest.mark.usefixtures("only_assessing_is_real")
def test_failing_audit_rolls_back_the_gap_rows(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = production_seeded
    case = _make_case(db, CaseStatus.OPEN)
    _cancel(db, LEAVING_STAFF_ID)
    real_log = assess_staffing.audit_service.log

    def fail_gap_audit(*args: Any, **kwargs: Any) -> None:
        if kwargs["action"] is AuditAction.GAP_ASSESSED:
            raise RuntimeError("audit failed")
        real_log(*args, **kwargs)

    monkeypatch.setattr(assess_staffing.audit_service, "log", fail_gap_audit)

    orchestrator.advance(db, case.id)

    assert case.status is CaseStatus.FAILED
    assert _count(db, StaffingGap) == 0
    assert _count(db, StaffingGapRole) == 0
    assert _count(db, StaffingGapSkill) == 0


# --------------------------------------------------------------------------- #
# Through the API, every handler real
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_reported_leave_shows_the_gap_on_the_case_and_its_timeline(client: TestClient) -> None:
    opened = client.post(
        "/events",
        headers={"X-Demo-User": str(LEAVING_STAFF_ID)},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": NIGHT_SHIFT},
    ).json()
    case_id = opened["case_id"]
    assert opened["case_status"] == "WAITING_RESPONSE"

    detail = client.get(f"/cases/{case_id}").json()
    audit = client.get(f"/cases/{case_id}/audit").json()

    assert detail["gap"]["headcount_gap"] == 1
    assert [(r["id"], r["gap_count"]) for r in detail["gap"]["roles"]] == [(RN, 1)]
    assert [(s["id"], s["gap_count"]) for s in detail["gap"]["skills"]] == [(ICU, 0)]
    actions = [row["action"] for row in audit if row["action"] != "CASE_STATUS_CHANGED"]
    # The case waits for the candidate, so the timeline is the start of the golden path
    assert actions == [action.value for action in GOLDEN_PATH_AUDIT_ACTIONS[: len(actions)]]
    assert "GAP_ASSESSED" in actions
