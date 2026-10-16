"""Wave selection, target credits and atomic delivery against PostgreSQL."""

from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateItemTarget,
    CandidateOutreach,
    Shift,
    Staff,
)
from app.domain.enums import (
    AuditAction,
    CaseStatus,
    OutreachStatus,
    SelectionType,
    StaffStatus,
    TargetType,
)
from app.domain.staffing.wave_targets import fill_targets
from app.domain.workflow.case_status import GapFiller
from app.services import optimization_service, outreach_service, wave_service
from app.workflow import orchestrator
from app.workflow.handlers import contact_candidate
from tests.integration.case_rows import make_case, make_plan, offer, short_case


def _setup(db: Session):
    case, items = short_case(db, status=CaseStatus.OUTREACH)
    credits = fill_targets(
        headcount_gap=1,
        role_gaps={1: 1},
        skill_gaps={},
        candidates=[GapFiller(201, 1, frozenset({1, 2})), GapFiller(202, 1, frozenset({2}))],
    )
    for staff_id, targets in credits.items():
        optimization_service.record_item_targets(db, items[staff_id], targets)
    return case, items


def _recipients(db: Session, case_id: int) -> list[int]:
    return list(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(CandidateOutreach.case_id == case_id)
            .order_by(CandidateOutreach.id)
        )
    )


def test_first_wave_uses_solver_group_and_one_timestamp(production_seeded: Session) -> None:
    db = production_seeded
    case, items = _setup(db)
    with patch.object(db, "commit", side_effect=AssertionError("Handler must not commit")):
        result = contact_candidate.handle(db, case)
    assert result.next_status == CaseStatus.WAITING_RESPONSE
    assert _recipients(db, case.id) == [201, 202]
    rows = list(db.scalars(select(CandidateOutreach).where(CandidateOutreach.case_id == case.id)))
    assert len({row.sent_at for row in rows}) == 1
    audits = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action != AuditAction.CASE_OPENED)
            .where(AuditLog.action == AuditAction.OFFER_SENT)
            .order_by(AuditLog.id)
        )
    )
    assert len(audits) == 2
    assert audits[0].payload["wave"] == audits[1].payload["wave"] == 1
    assert audits[0].payload["skipped"] == []
    assert "skipped" not in audits[1].payload
    assert items[203].id not in {row.candidate_item_id for row in rows}


def test_first_wave_replaces_only_vacant_target_not_whole_group(seeded: Session) -> None:
    case, items = _setup(seeded)
    member = seeded.get(Staff, 201)
    assert member is not None
    member.status = StaffStatus.INACTIVE
    seeded.flush()
    contact_candidate.handle(seeded, case)
    assert _recipients(seeded, case.id) == [202, 203]
    assert (
        seeded.scalar(
            select(CandidateItemTarget.id).where(
                CandidateItemTarget.candidate_item_id == items[203].id
            )
        )
        is not None
    )
    audit = seeded.scalar(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.OFFER_SENT)
        .order_by(AuditLog.id)
    )
    assert audit is not None
    assert audit.payload["skipped"] == [{"staff_id": 201, "reason": "STAFF_NOT_ACTIVE"}]


def test_later_wave_does_not_contact_any_answered_staff_again(seeded: Session) -> None:
    case, items = _setup(seeded)
    offer(seeded, case, items[201], OutreachStatus.REJECTED)
    offer(seeded, case, items[202], OutreachStatus.TIMEOUT)
    contact_candidate.handle(seeded, case)
    assert _recipients(seeded, case.id) == [201, 202, 203]
    audit = seeded.scalar(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.OFFER_SENT)
    )
    assert audit is not None and audit.payload["wave"] == 2


def test_current_limit_replaces_solver_candidate(seeded: Session) -> None:
    case, _ = _setup(seeded)
    for _ in range(3):
        other = make_case(seeded)
        item = make_plan(seeded, other, (201,))[201]
        offer(seeded, other, item)
    selected = wave_service.select_wave(seeded, case_id=case.id, shift=seeded.get(Shift, 1))
    assert [item.staff_id for item in selected.items] == [202, 203]
    assert {"staff_id": 201, "reason": "OFFER_LIMIT_REACHED"} in selected.skipped


def test_no_plan_is_an_error_not_a_fallback(seeded: Session) -> None:
    case = make_case(seeded, CaseStatus.OUTREACH)
    with pytest.raises(LookupError, match="No candidate plan"):
        contact_candidate.handle(seeded, case)


def test_latest_plan_is_used_even_if_it_has_no_items(seeded: Session) -> None:
    case, _ = _setup(seeded)
    make_plan(seeded, case, ())
    result = contact_candidate.handle(seeded, case)
    assert result.next_status == CaseStatus.MANUAL_HANDOFF
    assert _recipients(seeded, case.id) == []


@pytest.mark.parametrize("failure", ["delivery", "audit"])
def test_round_failure_rolls_back_entire_wave_and_targets(
    production_seeded: Session, failure: str
) -> None:
    db = production_seeded
    case, _ = _setup(db)
    inactive = db.get(Staff, 201)
    assert inactive is not None
    inactive.status = StaffStatus.INACTIVE
    db.flush()
    before = db.scalar(select(func.count()).select_from(CandidateItemTarget))
    target = (
        "app.integrations.line.mock.send_offer"
        if failure == "delivery"
        else "app.services.audit_service.log"
    )
    from app.services import audit_service

    real_log = audit_service.log

    def log(*args, **kwargs):
        if kwargs["action"] == AuditAction.OFFER_SENT:
            raise RuntimeError("audit failed")
        return real_log(*args, **kwargs)

    with patch(
        target, side_effect=RuntimeError("delivery failed") if failure == "delivery" else log
    ):
        orchestrator.advance(db, case.id)
    assert case.status == CaseStatus.FAILED
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0
    assert db.scalar(select(func.count()).select_from(CandidateItemTarget)) == before


def test_cancel_keeps_response_timestamp(seeded: Session) -> None:
    case, items = _setup(seeded)
    row = offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    from tests.integration.conftest import DEMO_NOW

    row.response_at = DEMO_NOW
    outreach_service.cancel_offer(seeded, row)
    seeded.flush()
    assert row.status == OutreachStatus.CANCELLED
    assert row.response_at == DEMO_NOW


def test_send_service_leaves_audit_and_commit_to_handler(production_seeded: Session) -> None:
    db = production_seeded
    case, items = _setup(db)
    with patch.object(db, "commit", side_effect=AssertionError("Service must not commit")):
        rows = outreach_service.send_offer(db, case, [items[201], items[202]])
    assert len(rows) == 2
    assert rows[0].sent_at == rows[1].sent_at
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action != AuditAction.CASE_OPENED)
        )
        == 0
    )


def test_a_missing_plan_does_not_use_another_cases_plan(seeded: Session) -> None:
    _setup(seeded)
    other = make_case(seeded, CaseStatus.OUTREACH)
    with pytest.raises(LookupError, match="No candidate plan"):
        contact_candidate.handle(seeded, other)


def test_send_service_rejects_items_of_another_case(seeded: Session) -> None:
    case, _ = _setup(seeded)
    other = make_case(seeded, CaseStatus.OUTREACH)
    foreign = make_plan(seeded, other, (201,))[201]
    with pytest.raises(ValueError, match="different case"):
        outreach_service.send_offer(seeded, case, [foreign])
    assert seeded.scalar(select(func.count()).select_from(CandidateOutreach)) == 0


def test_exhausted_case_waits_for_paused_offer_instead_of_handoff(seeded: Session) -> None:
    case, items = _setup(seeded)
    paused = offer(seeded, case, items[201])
    other = make_case(seeded, CaseStatus.WAITING_APPROVAL)
    other_item = make_plan(seeded, other, (201,))[201]
    accepted = offer(seeded, other, other_item, OutreachStatus.ACCEPTED)
    for staff_id in (202, 203):
        member = seeded.get(Staff, staff_id)
        assert member is not None
        member.status = StaffStatus.INACTIVE
    seeded.flush()
    result = contact_candidate.handle(seeded, case)
    assert result.next_status == CaseStatus.WAITING_RESPONSE
    assert paused.status == OutreachStatus.SENT
    assert (
        seeded.scalar(
            select(AuditLog.id)
            .where(AuditLog.action != AuditAction.CASE_OPENED)
            .where(AuditLog.action == AuditAction.MANUAL_HANDOFF)
        )
        is None
    )
    outreach_service.cancel_offer(seeded, accepted)
    seeded.flush()
    from app.services import case_facts_service

    assert case_facts_service.has_open_offer(seeded, case.id)


def test_skipped_solver_reserve_gets_new_primary_targets_in_later_wave(seeded: Session) -> None:
    case, items = short_case(seeded, status=CaseStatus.OUTREACH)
    credits = fill_targets(
        headcount_gap=1,
        role_gaps={1: 1},
        skill_gaps={},
        candidates=[GapFiller(202, 1, frozenset({2})), GapFiller(201, 1, frozenset({1, 2}))],
    )
    for staff_id, targets in credits.items():
        optimization_service.record_item_targets(seeded, items[staff_id], targets)
    limited_offers = []
    for _ in range(3):
        other = make_case(seeded)
        item = make_plan(seeded, other, (201,))[201]
        limited_offers.append(offer(seeded, other, item))
    assert set(
        seeded.scalars(
            select(CandidateItemTarget.selection_type).where(
                CandidateItemTarget.candidate_item_id == items[201].id
            )
        )
    ) == {SelectionType.RESERVE}
    contact_candidate.handle(seeded, case)
    assert _recipients(seeded, case.id) == [202, 203]
    for row in seeded.scalars(
        select(CandidateOutreach).where(CandidateOutreach.case_id == case.id)
    ):
        row.status = OutreachStatus.REJECTED
    for row in limited_offers:
        row.status = OutreachStatus.REJECTED
    seeded.flush()
    contact_candidate.handle(seeded, case)
    assert _recipients(seeded, case.id) == [202, 203, 201]
    targets = list(
        seeded.scalars(
            select(CandidateItemTarget).where(
                CandidateItemTarget.candidate_item_id == items[201].id
            )
        )
    )
    assert {(row.target_type, row.selection_type) for row in targets} == {
        (TargetType.ROLE, SelectionType.PRIMARY),
        (TargetType.HEADCOUNT, SelectionType.PRIMARY),
    }
    assert len(targets) == 2


@pytest.mark.parametrize("with_legacy_audit", [False, True])
def test_legacy_history_without_wave_number_advances_to_wave_two(
    seeded: Session, with_legacy_audit: bool
) -> None:
    case, items = _setup(seeded)
    row = offer(seeded, case, items[201], OutreachStatus.REJECTED)
    if with_legacy_audit:
        from app.domain.enums import EntityType
        from app.services import actor_service, audit_service

        audit_service.log(
            seeded,
            case_id=case.id,
            actor_id=actor_service.user_id(seeded, 201),
            action=AuditAction.OFFER_SENT,
            entity_type=EntityType.CANDIDATE_OUTREACH,
            entity_id=row.id,
            payload={"outreach_id": row.id, "staff_id": 201},
        )
    contact_candidate.handle(seeded, case)
    payloads = list(
        seeded.scalars(
            select(AuditLog.payload).where(
                AuditLog.case_id == case.id, AuditLog.action == AuditAction.OFFER_SENT
            )
        )
    )
    assert [p["wave"] for p in payloads if "wave" in p] == [2, 2]
