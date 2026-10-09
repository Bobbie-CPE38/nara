"""Offer creation for the Golden Path; the orchestrator owns the transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidateOutreach, CandidatePlan, StaffingCase
from app.domain.enums import ActorName, AuditAction, Channel, EntityType, OutreachStatus
from app.integrations.line import mock as line_mock
from app.services import actor_service, audit_service


def send_offer(db: Session, case: StaffingCase) -> CandidateOutreach:
    """Send exactly one rank-1 candidate from the latest plan, without committing.

    Missing plans, missing rank-1 items, and duplicate rank-1 items raise. The
    handler lets these errors reach the orchestrator's D11 failure handling.
    Flush first because plans may have been created earlier in this round and
    production sessions have autoflush disabled.
    """
    db.flush()
    plan = db.scalar(
        select(CandidatePlan)
        .where(CandidatePlan.case_id == case.id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan is None:
        raise LookupError(f"No candidate plan for case {case.id}")
    item = db.scalars(
        select(CandidateItem).where(CandidateItem.plan_id == plan.id, CandidateItem.rank == 1)
    ).one()
    actor_id = actor_service.component_id(db, ActorName.OUTREACH_AGENT)
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        status=OutreachStatus.PENDING,
    )
    db.add(outreach)
    db.flush()
    line_mock.send_offer(staff_id=item.staff_id, outreach_id=outreach.id)
    outreach.status = OutreachStatus.SENT
    outreach.sent_at = clock.now()
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.OFFER_SENT,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=outreach.id,
        payload={
            "outreach_id": outreach.id,
            "staff_id": item.staff_id,
            "channel": Channel.LINE.value,
        },
    )
    return outreach
