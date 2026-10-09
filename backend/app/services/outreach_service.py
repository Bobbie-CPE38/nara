"""Offer creation for the Golden Path; the orchestrator owns the transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidateOutreach, CandidatePlan, StaffingCase
from app.domain.enums import Channel, OutreachStatus
from app.integrations.line import mock as line_mock


def send_offer(db: Session, case: StaffingCase) -> tuple[CandidateOutreach, int]:
    """Send exactly one rank-1 candidate from the latest plan, without committing.

    Returns the outreach and recipient staff ID; writes no audit row. The
    contact handler owns OFFER_SENT. Missing plans, missing rank-1 items, and
    duplicate rank-1 items raise. The handler lets these errors reach the
    orchestrator's D11 failure handling.
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
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        status=OutreachStatus.SENT,
        sent_at=clock.now(),
    )
    db.add(outreach)
    db.flush()
    line_mock.send_offer(staff_id=item.staff_id, outreach_id=outreach.id)
    return outreach, item.staff_id
