"""Seam 4: exactly one accepted offer for the safety step, with autoflush off."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    SafetyValidation,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    AuditAction,
    CandidateSource,
    CaseStatus,
    Channel,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.services import outreach_service
from app.workflow import orchestrator
from tests.integration.conftest import DEMO_NOW


def _case(db: Session) -> StaffingCase:
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
        status=CaseStatus.WAITING_RESPONSE,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


def _offer(db: Session, case: StaffingCase) -> CandidateOutreach:
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
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=201,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=1,
    )
    db.add(item)
    db.flush()
    offer = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        sent_at=DEMO_NOW,
        response_at=DEMO_NOW,
        status=OutreachStatus.ACCEPTED,
    )
    db.add(offer)
    db.flush()
    return offer


@pytest.fixture
def case(production_seeded: Session) -> StaffingCase:
    return _case(production_seeded)


def test_returns_the_accepted_offer_without_writes(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    offer = _offer(db, case)
    before = dict(vars(offer))
    with (
        patch.object(db, "flush", wraps=db.flush) as flush,
        patch.object(db, "commit", wraps=db.commit) as commit,
    ):
        result = outreach_service.get_accepted_outreach(db, case.id)
    assert result is offer
    assert vars(offer) == before
    assert case.status is CaseStatus.WAITING_RESPONSE
    flush.assert_called_once_with()
    commit.assert_not_called()
    assert not db.new
    assert not db.dirty
    assert db.scalar(select(AuditLog.id)) is None


def test_no_accepted_offer_raises(production_seeded: Session, case: StaffingCase) -> None:
    with pytest.raises(NoResultFound):
        outreach_service.get_accepted_outreach(production_seeded, case.id)


def test_unknown_case_has_no_accepted_offer(production_seeded: Session) -> None:
    with pytest.raises(NoResultFound):
        outreach_service.get_accepted_outreach(production_seeded, 999)


@pytest.mark.parametrize(
    "status", [status for status in OutreachStatus if status != OutreachStatus.ACCEPTED]
)
def test_other_statuses_do_not_count_as_accepted(
    production_seeded: Session, case: StaffingCase, status: OutreachStatus
) -> None:
    db = production_seeded
    offer = _offer(db, case)
    offer.status = status
    db.flush()
    with pytest.raises(NoResultFound):
        outreach_service.get_accepted_outreach(db, case.id)


def test_another_cases_accepted_offer_is_not_selected(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    _offer(db, _case(db))
    with pytest.raises(NoResultFound):
        outreach_service.get_accepted_outreach(db, case.id)
    own = _offer(db, case)
    assert outreach_service.get_accepted_outreach(db, case.id).id == own.id


def test_multiple_accepted_offers_raise_instead_of_choosing_first(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    _offer(db, case)
    _offer(db, case)
    with pytest.raises(MultipleResultsFound):
        outreach_service.get_accepted_outreach(db, case.id)


def test_other_offers_do_not_make_the_accepted_offer_ambiguous(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    accepted = _offer(db, case)
    for status in (OutreachStatus.SENT, OutreachStatus.REJECTED, OutreachStatus.CANCELLED):
        other = _offer(db, case)
        other.status = status
    db.flush()
    assert outreach_service.get_accepted_outreach(db, case.id).id == accepted.id


def test_pending_answer_is_flushed_with_production_settings(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    assert db.autoflush is False
    offer = _offer(db, case)
    offer.status = OutreachStatus.SENT
    db.flush()
    offer.status = OutreachStatus.ACCEPTED
    assert outreach_service.get_accepted_outreach(db, case.id).id == offer.id


def test_resume_uses_shared_lookup_in_real_safety_with_an_unflushed_answer(
    production_seeded: Session, case: StaffingCase
) -> None:
    db = production_seeded
    offer = _offer(db, case)
    offer.status = OutreachStatus.SENT
    db.flush()
    offer.status = OutreachStatus.ACCEPTED
    with patch.object(
        outreach_service, "get_accepted_outreach", wraps=outreach_service.get_accepted_outreach
    ) as lookup:
        orchestrator.resume(db, case.id, CaseStatus.SAFETY_VALIDATION)
    lookup.assert_called_once_with(db, case.id)
    assert case.status is CaseStatus.WAITING_APPROVAL
    assert db.scalars(select(SafetyValidation)).one().candidate_item_id == offer.candidate_item_id
    assert db.scalars(select(ApprovalRequest)).one().candidate_item_id == offer.candidate_item_id
    assert outreach_service.get_accepted_outreach(db, case.id).id == offer.id


@pytest.mark.parametrize("count", [0, 2])
def test_invalid_handoff_reaches_d11(
    production_seeded: Session, case: StaffingCase, count: int
) -> None:
    db = production_seeded
    for _ in range(count):
        _offer(db, case)
    orchestrator.resume(db, case.id, CaseStatus.SAFETY_VALIDATION)
    assert case.status is CaseStatus.FAILED
    assert db.scalar(select(SafetyValidation.id)) is None
    assert db.scalar(select(ApprovalRequest.id)) is None
    failure = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).one()
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["failed_at"] == "SAFETY_VALIDATION"
    assert failure.payload["error_type"] == (
        "NoResultFound" if count == 0 else "MultipleResultsFound"
    )
