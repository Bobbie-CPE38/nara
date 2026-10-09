"""Seam 2: real PostgreSQL offer creation and orchestrator transaction ownership."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    ActorName,
    AuditAction,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.services import actor_service
from app.workflow import orchestrator
from app.workflow.handlers import contact_candidate
from tests.integration.conftest import DEMO_NOW


@pytest.fixture
def case(production_seeded: Session) -> StaffingCase:
    db = production_seeded
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=1,
        staff_id=105,
        occurred_at=DEMO_NOW,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=1,
        status=CaseStatus.OUTREACH,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


def _plan(db: Session, case: StaffingCase) -> CandidatePlan:
    plan = CandidatePlan(
        case_id=case.id,
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
    return plan


def _item(db: Session, plan: CandidatePlan, *, rank: int = 1, staff_id: int = 201) -> CandidateItem:
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=staff_id,
        rank=rank,
        source=CandidateSource.FLOAT_POOL,
        proposed_shift_id=1,
    )
    db.add(item)
    return item


def test_offer_contract_and_no_commit(production_seeded: Session, case: StaffingCase) -> None:
    db = production_seeded
    item = _item(db, _plan(db, case))  # Pending item must be seen with autoflush=False.
    with (
        patch.object(db, "commit", wraps=db.commit) as commit,
        patch("app.integrations.line.mock.send_offer") as send,
    ):
        result = contact_candidate.handle(db, case)
        commit.assert_not_called()
    offer = db.scalars(select(CandidateOutreach)).one()
    send.assert_called_once_with(staff_id=201, outreach_id=offer.id)
    assert result.next_status is CaseStatus.WAITING_RESPONSE
    assert result.wait is True
    assert case.status is CaseStatus.OUTREACH
    assert offer.case_id == case.id
    assert offer.candidate_item_id == item.id
    assert offer.channel is Channel.LINE
    assert offer.status is OutreachStatus.SENT
    assert offer.sent_at == DEMO_NOW
    assert offer.response_at is None
    audit = db.scalars(select(AuditLog)).one()
    assert audit.action is AuditAction.OFFER_SENT
    assert audit.actor_id == actor_service.component_id(db, ActorName.OUTREACH_AGENT)
    assert audit.case_id == case.id
    assert audit.entity_type is EntityType.CANDIDATE_OUTREACH
    assert audit.entity_id == offer.id
    assert audit.created_at == DEMO_NOW
    assert audit.payload == {"outreach_id": offer.id, "staff_id": 201, "channel": "LINE"}
    db.rollback()
    assert db.scalar(select(CandidateOutreach.id)) is None
    assert db.scalar(select(AuditLog.id)) is None


def test_latest_plan_by_id_and_rank_one(production_seeded: Session, case: StaffingCase) -> None:
    db = production_seeded
    older = _plan(db, case)
    older.generated_at = DEMO_NOW + timedelta(days=1)
    _item(db, older, staff_id=105)
    latest = _plan(db, case)
    _item(db, latest, rank=2, staff_id=105)
    selected = _item(db, latest)
    contact_candidate.handle(db, case)
    assert db.scalars(select(CandidateOutreach)).one().candidate_item_id == selected.id


@pytest.mark.parametrize("count", [0, 2])
def test_rank_one_must_be_exactly_one(
    production_seeded: Session, case: StaffingCase, count: int
) -> None:
    db = production_seeded
    plan = _plan(db, case)
    for _ in range(count):
        _item(db, plan)
    with patch("app.integrations.line.mock.send_offer") as send:
        with pytest.raises(NoResultFound if count == 0 else MultipleResultsFound):
            contact_candidate.handle(db, case)
        send.assert_not_called()
    assert db.scalar(select(CandidateOutreach.id)) is None
    assert db.scalar(select(AuditLog.id)) is None


def test_no_plan_does_not_send(production_seeded: Session, case: StaffingCase) -> None:
    with patch("app.integrations.line.mock.send_offer") as send:
        with pytest.raises(LookupError, match="No candidate plan"):
            contact_candidate.handle(production_seeded, case)
        send.assert_not_called()


def test_does_not_fall_back_to_older_plan(production_seeded: Session, case: StaffingCase) -> None:
    db = production_seeded
    _item(db, _plan(db, case))
    _plan(db, case)
    with pytest.raises(NoResultFound):
        contact_candidate.handle(db, case)


def test_plan_selection_is_scoped_to_case(production_seeded: Session, case: StaffingCase) -> None:
    db = production_seeded
    selected = _item(db, _plan(db, case))
    other = StaffingCase(
        event_id=case.event_id,
        shift_id=1,
        status=CaseStatus.OUTREACH,
        required_replacement_time=case.required_replacement_time,
    )
    db.add(other)
    db.flush()
    _item(db, _plan(db, other), staff_id=105)
    contact_candidate.handle(db, case)
    assert db.scalars(select(CandidateOutreach)).one().candidate_item_id == selected.id


def test_real_round_sends_once_and_waits(production_seeded: Session, case: StaffingCase) -> None:
    db = production_seeded
    _item(db, _plan(db, case))
    with patch.object(db, "commit", wraps=db.commit) as commit:
        orchestrator.advance(db, case.id)
        commit.assert_called_once()
    assert case.status is CaseStatus.WAITING_RESPONSE
    orchestrator.advance(db, case.id)
    assert len(list(db.scalars(select(CandidateOutreach)))) == 1
    actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == [AuditAction.OFFER_SENT, AuditAction.CASE_STATUS_CHANGED]


@pytest.mark.parametrize("failure", ["no_plan", "duplicate", "delivery", "audit"])
def test_round_failure_rolls_back_offer_and_records_failed(
    production_seeded: Session, case: StaffingCase, failure: str
) -> None:
    db = production_seeded
    if failure != "no_plan":
        plan = _plan(db, case)
        _item(db, plan)
        if failure == "duplicate":
            _item(db, plan)
    real_log = orchestrator.audit_service.log
    with (
        patch("app.integrations.line.mock.send_offer") as send,
        patch("app.services.outreach_service.audit_service.log", wraps=real_log) as audit,
    ):
        if failure == "delivery":
            send.side_effect = RuntimeError("mock delivery failed")
        if failure == "audit":

            def fail_offer_audit(*args: Any, **kwargs: Any) -> None:
                if kwargs.get("action") is AuditAction.OFFER_SENT:
                    raise RuntimeError("offer audit failed")
                real_log(*args, **kwargs)

            audit.side_effect = fail_offer_audit
        orchestrator.advance(db, case.id)
    assert case.status is CaseStatus.FAILED
    assert db.scalar(select(CandidateOutreach.id)) is None
    actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == [AuditAction.CASE_STATUS_CHANGED, AuditAction.WORKFLOW_FAILED]
