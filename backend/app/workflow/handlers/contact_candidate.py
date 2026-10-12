from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateOutreach, Shift, StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType, OutreachStatus
from app.services import (
    actor_service,
    audit_service,
    case_facts_service,
    outreach_service,
    wave_service,
)
from app.workflow.handlers.base import HandlerResult


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Send a Wave; exhaustion waits for useful commitments before handing off."""
    shift = db.get(Shift, case.shift_id)
    if shift is None:
        raise LookupError(f"No shift {case.shift_id}")
    selected = wave_service.select_wave(db, case_id=case.id, shift=shift)
    actor_id = actor_service.component_id(db, ActorName.OUTREACH_AGENT)
    if selected.items:
        offers = outreach_service.send_offer(db, case, selected.items)
        for index, (item, offer) in enumerate(zip(selected.items, offers, strict=True)):
            payload: dict[str, object] = {
                "outreach_id": offer.id,
                "staff_id": item.staff_id,
                "channel": offer.channel.value,
                "wave": selected.wave,
            }
            if index == 0:
                payload["skipped"] = list(selected.skipped)
            audit_service.log(
                db,
                case_id=case.id,
                actor_id=actor_id,
                action=AuditAction.OFFER_SENT,
                entity_type=EntityType.CANDIDATE_OUTREACH,
                entity_id=offer.id,
                payload=payload,
            )
        return HandlerResult(next_status=CaseStatus.WAITING_RESPONSE, wait=True)

    facts = case_facts_service.load_case_facts(db, case)
    if facts.has_pending_approval:
        return HandlerResult(next_status=CaseStatus.WAITING_APPROVAL, wait=True)
    if facts.has_paused_offer or facts.has_open_offer:
        return HandlerResult(next_status=CaseStatus.WAITING_RESPONSE, wait=True)
    cancelled_ids = []
    for offer in db.scalars(
        select(CandidateOutreach)
        .where(
            CandidateOutreach.case_id == case.id, CandidateOutreach.status == OutreachStatus.SENT
        )
        .order_by(CandidateOutreach.id)
    ):
        outreach_service.cancel_offer(db, offer)
        cancelled_ids.append(offer.id)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.MANUAL_HANDOFF,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={
            "reason": "NO_CANDIDATE_LEFT",
            "stopped_at": case.status.value,
            "cancelled_outreach_ids": cancelled_ids,
            "skipped": list(selected.skipped),
        },
    )
    return HandlerResult(next_status=CaseStatus.MANUAL_HANDOFF, wait=False)
