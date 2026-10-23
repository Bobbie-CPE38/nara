"""How long and how often a case may send waves (round 6 PR EV6, docs/workflow.md 6.36.8).

A case sends at most OUTREACH_POLICY.maximum_waves_per_case waves, and no new wave once
case_outreach_deadline_seconds have passed since it opened (StaffingCase.created_at). Either
limit only stops the next wave: offers already sent keep their own deadline, and the case
waits for them like any other wave. When nothing is left to wait for, contact_candidate hands
the case off with the limit as the reason (ManualHandoffReason).

Read-only: no flush, lock or commit.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import AuditLog, CandidateOutreach, StaffingCase
from app.domain.enums import AuditAction, ManualHandoffReason
from app.services import policy_service


def waves_sent(db: Session, case_id: int) -> int:
    """The number of the case's latest wave, from its OFFER_SENT audit rows.

    Every wave writes its number on all of its OFFER_SENT rows. History from before the
    number was written counts as wave 1. A frozen clock gives every wave the same sent_at,
    so the time of the offers cannot tell the waves apart.
    """
    payloads = db.scalars(
        select(AuditLog.payload).where(
            AuditLog.case_id == case_id, AuditLog.action == AuditAction.OFFER_SENT
        )
    ).all()
    if payloads:
        return max(int(payload.get("wave", 1)) for payload in payloads)
    sent = db.scalar(
        select(CandidateOutreach.id).where(CandidateOutreach.case_id == case_id).limit(1)
    )
    return 0 if sent is None else 1


def stop_reason(db: Session, case_id: int) -> ManualHandoffReason | None:
    """Why the case may send no new wave, or None while it may."""
    case = db.get(StaffingCase, case_id)
    if case is None:
        raise LookupError(f"No case {case_id}")
    policy = policy_service.get_outreach_policy(db)
    if clock.now() >= case.created_at + timedelta(seconds=policy.case_outreach_deadline_seconds):
        return ManualHandoffReason.OUTREACH_DEADLINE_REACHED
    if waves_sent(db, case_id) >= policy.maximum_waves_per_case:
        return ManualHandoffReason.WAVE_LIMIT_REACHED
    return None
