"""Wave offers, individual responses and reserves (workflow.md 6.6–6.11).

No case-status writes. The orchestrator commits the answer and its workflow;
foreign-case notifications run after that commit in separate transactions.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    SafetyValidation,
    Shift,
    StaffingCase,
    Ward,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AuditAction,
    CandidateResponse,
    Channel,
    EntityType,
    OutreachStatus,
)
from app.integrations.line import mock as line_mock
from app.schemas.outreach import OfferView
from app.services import audit_service, case_facts_service, hard_rule_service
from app.services.wave_service import plan_items

logger = logging.getLogger(__name__)


class OpenOfferConflictError(ValueError):
    """The selected offer is not answerable by this staff member."""


def list_offers(db: Session, *, staff_id: int) -> list[OfferView]:
    """Read history with per-offer actions and ward/shift context; no writes."""
    with db.no_autoflush:
        rows = (
            db.execute(
                select(
                    CandidateOutreach.id,
                    CandidateOutreach.case_id,
                    CandidateOutreach.candidate_item_id,
                    CandidateItem.staff_id,
                    CandidateItem.proposed_shift_id,
                    CandidateOutreach.status,
                    StaffingCase.status.label("case_status"),
                    CandidateOutreach.channel,
                    CandidateOutreach.sent_at,
                    CandidateOutreach.response_at,
                    Shift.ward_id,
                    Ward.name.label("ward_name"),
                    Shift.start_at.label("shift_start_at"),
                    Shift.end_at.label("shift_end_at"),
                )
                .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
                .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
                .join(Shift, Shift.id == CandidateItem.proposed_shift_id)
                .join(Ward, Ward.id == Shift.ward_id)
                .where(CandidateItem.staff_id == staff_id)
                .order_by(CandidateOutreach.id)
            )
            .mappings()
            .all()
        )
        if not rows:
            return []
        item_ids = {row["candidate_item_id"] for row in rows}
        requested = set(
            db.scalars(
                select(ApprovalRequest.candidate_item_id).where(
                    ApprovalRequest.candidate_item_id.in_(item_ids)
                )
            )
        )
        validated = set(
            db.scalars(
                select(SafetyValidation.candidate_item_id).where(
                    SafetyValidation.candidate_item_id.in_(item_ids)
                )
            )
        )
        # One set of unresolved acceptances for the staff, independent of the
        # number of displayed offers. Keep the shared pausing semantics.
        waiting_cases = case_facts_service.staff_waiting_case_ids(db, staff_id)
        cancelled = {row["id"] for row in rows if row["status"] == OutreachStatus.CANCELLED}
        reasons = _cancellation_reasons(db, cancelled)
        result = []
        for row in rows:
            live = row["status"] is OutreachStatus.SENT and (
                row["case_status"] not in AUTOMATION_STOPPED_STATUSES
            )
            paused = live and bool(waiting_cases - {row["case_id"]})
            blocked = (
                "AWAITING_OTHER_CASE"
                if paused
                else ("CASE_STOPPED" if row["case_status"] in AUTOMATION_STOPPED_STATUSES else None)
            )
            reason = reasons.get(row["id"]) if row["status"] == OutreachStatus.CANCELLED else None
            reserve = (
                row["status"] == OutreachStatus.ACCEPTED
                and row["case_status"] not in AUTOMATION_STOPPED_STATUSES
                and row["candidate_item_id"] not in requested
                and row["candidate_item_id"] not in validated
            )
            result.append(
                OfferView.model_validate(
                    dict(row)
                    | {
                        "can_accept": live and not paused,
                        "can_reject": live,
                        "blocked_reason": blocked,
                        "cancellation_reason": reason,
                        "is_reserve": reserve,
                    }
                )
            )
        return result


def _cancellation_reasons(db: Session, outreach_ids: set[int]) -> dict[int, str]:
    """Batch only audits whose payload references the displayed cancelled offers.

    Foreign ASSIGNMENT_CREATED rows are relevant only when their cancellation
    list contains one of these IDs; never load all assignments in the system.
    Latest matching audit wins, as in the original per-offer lookup.
    """
    if not outreach_ids:
        return {}
    references = [
        predicate
        for outreach_id in sorted(outreach_ids)
        for predicate in (
            AuditLog.payload.contains({"cancelled_outreach_ids": [outreach_id]}),
            AuditLog.payload.contains({"outreach_id": outreach_id}),
        )
    ]
    rows = db.scalars(select(AuditLog).where(or_(*references)).order_by(AuditLog.id.desc()))
    reasons: dict[int, str] = {}
    for row in rows:
        payload = row.payload
        for outreach_id in outreach_ids - reasons.keys():
            if outreach_id in payload.get("cancelled_outreach_ids", []):
                reasons[outreach_id] = {
                    AuditAction.CASE_RESOLVED: "CASE_RESOLVED",
                    AuditAction.MANUAL_HANDOFF: "MANUAL_HANDOFF",
                    AuditAction.ASSIGNMENT_CREATED: "CONFLICTING_ASSIGNMENT",
                }.get(row.action, "CANCELLED")
            elif payload.get("outreach_id") == outreach_id:
                if row.action == AuditAction.SAFETY_FAILED:
                    reasons[outreach_id] = (
                        ", ".join(payload.get("failed_rules", [])) or "SAFETY_FAILED"
                    )
                elif row.action == AuditAction.APPROVAL_REJECTED:
                    reasons[outreach_id] = payload.get("reason") or "APPROVAL_REJECTED"
    return {outreach_id: reasons.get(outreach_id, "CANCELLED") for outreach_id in outreach_ids}


def send_offer(
    db: Session, case: StaffingCase, items: Sequence[CandidateItem]
) -> list[CandidateOutreach]:
    """Write one SENT row per selected Item with one clock read; audit is the handler's."""
    if len({item.staff_id for item in items}) != len(items):
        raise ValueError("A Wave cannot contact the same staff member twice")
    if any(item.proposed_shift_id != case.shift_id for item in items):
        raise ValueError("A Wave item proposes a different shift")
    plan_ids = set(
        db.scalars(
            select(CandidatePlan.id).where(
                CandidatePlan.id.in_([item.plan_id for item in items]),
                CandidatePlan.case_id == case.id,
            )
        )
    )
    if any(item.plan_id not in plan_ids for item in items):
        raise ValueError("A Wave item belongs to a different case")
    now = clock.now()
    offers = [
        CandidateOutreach(
            case_id=case.id,
            candidate_item_id=item.id,
            channel=Channel.LINE,
            status=OutreachStatus.SENT,
            sent_at=now,
        )
        for item in items
    ]
    db.add_all(offers)
    db.flush()
    # The mock sends before commit. A real LINE adapter must use a transactional
    # outbox so rolled-back waves cannot deliver offers that do not exist.
    for item, outreach in zip(items, offers, strict=True):
        line_mock.send_offer(staff_id=item.staff_id, outreach_id=outreach.id)
    return offers


def cancel_offer(db: Session, outreach: CandidateOutreach) -> None:
    """Shared cancellation write for Safety, Approval and case completion (Q8).

    The caller holds offer locks, owns its audit and transaction, and chooses
    which rows to cancel. Keep response_at: cancellation is not a new response.
    """
    if outreach.status in {OutreachStatus.SENT, OutreachStatus.ACCEPTED}:
        outreach.status = OutreachStatus.CANCELLED


def lock_case_for_outreach(db: Session, case_id: int) -> StaffingCase:
    """Offer rows → case → whole-plan Staff, in the agreed global order.

    Must be called before making response/foreign-case recompute writes. Lock
    every offer in one query, including the selected row on replay, then refresh
    cached state after waiting. NO KEY UPDATE permits FK audit inserts.
    """
    db.flush()
    list(
        db.scalars(
            select(CandidateOutreach)
            .where(CandidateOutreach.case_id == case_id)
            .order_by(CandidateOutreach.id)
            .with_for_update(key_share=True, of=CandidateOutreach)
            .execution_options(populate_existing=True)
        )
    )
    case = db.scalar(
        select(StaffingCase)
        .where(StaffingCase.id == case_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if case is None:
        raise LookupError(f"No case {case_id}")
    if case.status not in AUTOMATION_STOPPED_STATUSES:
        items = plan_items(db, case_id)
        hard_rule_service.lock_staff(db, [item.staff_id for item in items])
    return case


def promote_reserves(db: Session, case: StaffingCase) -> None:
    """Process accepted reserves oldest first until assigned+pending cover the gap.

    PR 3 replaces the temporary individual Skeleton Safety adapter below. PR 4
    calls this helper after a rejection. Caller already holds all case/Staff locks.
    """
    from app.workflow.handlers import validate_safety

    processed = exists().where(
        SafetyValidation.candidate_item_id == CandidateOutreach.candidate_item_id
    )
    requested = exists().where(
        ApprovalRequest.candidate_item_id == CandidateOutreach.candidate_item_id
    )
    while not case_facts_service.load_case_facts(db, case).gap_closed_with_pending:
        db.flush()
        outreach = db.scalar(
            select(CandidateOutreach)
            .where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.status == OutreachStatus.ACCEPTED,
                ~processed,
                ~requested,
            )
            .order_by(CandidateOutreach.response_at, CandidateOutreach.id)
            .limit(1)
        )
        if outreach is None:
            break
        validate_safety.handle(db, case, outreach_id=outreach.id)
        db.flush()
        # A stub or broken Safety implementation must not keep selecting the
        # same reserve forever inside the HTTP request.
        if (
            outreach.status == OutreachStatus.ACCEPTED
            and not db.scalar(
                select(
                    exists().where(SafetyValidation.candidate_item_id == outreach.candidate_item_id)
                )
            )
            and not db.scalar(
                select(
                    exists().where(ApprovalRequest.candidate_item_id == outreach.candidate_item_id)
                )
            )
        ):
            raise RuntimeError("Safety did not record an outcome for the accepted offer")


def recompute_affected_cases(db: Session, *, staff_id: int, own_case_id: int) -> None:
    """Post-commit notifications; each foreign case starts with its own locks."""
    from app.workflow import orchestrator

    case_ids = list(
        db.scalars(
            select(CandidateOutreach.case_id)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateItem.staff_id == staff_id,
                CandidateOutreach.case_id != own_case_id,
                CandidateOutreach.status == OutreachStatus.SENT,
                StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            )
            .distinct()
            .order_by(CandidateOutreach.case_id)
        )
    )
    # End the read transaction before each independent foreign-case round.
    db.rollback()
    for case_id in case_ids:
        try:
            lock_case_for_outreach(db, case_id)
            orchestrator.recompute(db, case_id)
        except Exception:
            db.rollback()
            logger.exception("Foreign case %s needs recompute retry", case_id)
            # PR O recovery tracking: docs/round1/round1-contract-draft.md, section 10.
            # https://github.com/Bobbie-CPE38/nara/blob/feat/round1-case-flow/docs/round1/round1-contract-draft.md#10-ลำดับ-pr
            # Until the sweep lands, this log
            # signals a foreign case needing a manual recompute retry.


def record_response(
    db: Session, *, staff_id: int, actor_id: int, outreach_id: int, response: CandidateResponse
) -> tuple[CandidateOutreach, StaffingCase]:
    """Answer the authenticated user's selected offer, even if other offers are open."""
    from app.workflow import orchestrator

    if not isinstance(response, CandidateResponse):
        raise TypeError("response must be a CandidateResponse")
    outreach = db.scalar(
        select(CandidateOutreach)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(CandidateOutreach.id == outreach_id, CandidateItem.staff_id == staff_id)
    )
    if outreach is None:
        raise OpenOfferConflictError("The selected offer is not available for this staff member")
    case = lock_case_for_outreach(db, outreach.case_id)
    if case.status in AUTOMATION_STOPPED_STATUSES:
        raise OpenOfferConflictError("This case has stopped; the offer cannot be answered")
    if outreach.status is not OutreachStatus.SENT:
        raise OpenOfferConflictError("The selected offer is no longer SENT; refresh offers")
    if response is CandidateResponse.ACCEPT and case_facts_service.staff_waiting_on_another_case(
        db, case.id, {staff_id}
    ):
        raise OpenOfferConflictError(
            "You are waiting for the outcome of an accepted offer on another case"
        )
    outreach.status = (
        OutreachStatus.ACCEPTED if response is CandidateResponse.ACCEPT else OutreachStatus.REJECTED
    )
    outreach.response_at = clock.now()
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.OFFER_ACCEPTED
        if response is CandidateResponse.ACCEPT
        else AuditAction.OFFER_REJECTED,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=outreach.id,
        payload={"outreach_id": outreach.id, "staff_id": staff_id},
    )
    orchestrator.recompute(db, case.id, prepare=promote_reserves)
    # Save IDs: rollback between independent notifications expires ORM objects.
    case_id = case.id
    recompute_affected_cases(db, staff_id=staff_id, own_case_id=case_id)
    return outreach, case


def get_accepted_outreach(db: Session, case_id: int) -> CandidateOutreach:
    """Return exactly one ACCEPTED outreach for the case (seam 4).

    Missing or multiple accepted offers raise NoResultFound / MultipleResultsFound
    for the safety handler to let D11 handle. Flush pending answers first because
    production sessions disable autoflush. Does not create rows, commit, audit,
    or acquire row locks. A flush error requires rollback before continuing.
    """
    db.flush()
    return db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.status == OutreachStatus.ACCEPTED,
        )
    ).one()
