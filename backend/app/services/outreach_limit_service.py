"""How long and how often a case may send waves (round 6 PR EV6, docs/workflow.md 6.36.8).

A case sends at most OUTREACH_POLICY.maximum_waves_per_case waves, and no new wave once
case_outreach_deadline_seconds have passed since it opened (StaffingCase.created_at). Either
limit only stops the next wave: offers already sent keep their own deadline, and the case
waits for them like any other wave. When nothing is left to wait for, contact_candidate hands
the case off with the limit as the reason (ManualHandoffReason).

The first wave is never stopped (review of #145): a demo clock set or advanced past the
deadline before the case sent anything would otherwise hand it off with nobody asked. A clock
set back before the case opened only delays the deadline until the clock passes it again.

Read-only: no flush, lock or commit. Two reads at most, and the policy is in the session.
"""

from datetime import datetime, timedelta

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import AuditLog, CandidateOutreach, StaffingCase
from app.domain.enums import AuditAction, ManualHandoffReason
from app.services import policy_service


def _sent(db: Session, case_id: int) -> tuple[int, datetime | None]:
    """The number of the case's latest wave and when it opened, from one read.

    Every wave writes its number on all of its OFFER_SENT audit rows. History from before the
    number was written counts as wave 1. A frozen clock gives every wave the same sent_at,
    so the time of the offers cannot tell the waves apart.
    """
    waves, rows = db.execute(
        select(
            func.max(func.coalesce(AuditLog.payload["wave"].astext.cast(Integer), 1)),
            func.count(AuditLog.id),
        ).where(AuditLog.case_id == case_id, AuditLog.action == AuditAction.OFFER_SENT)
    ).one()
    case_opened = db.scalar(select(StaffingCase.created_at).where(StaffingCase.id == case_id))
    if rows:
        return int(waves), case_opened
    sent = db.scalar(
        select(CandidateOutreach.id).where(CandidateOutreach.case_id == case_id).limit(1)
    )
    return (0 if sent is None else 1), case_opened


def waves_sent(db: Session, case_id: int) -> int:
    """The number of the case's latest wave; 0 before the first one."""
    return _sent(db, case_id)[0]


def stop_reason(db: Session, case_id: int) -> ManualHandoffReason | None:
    """Why the case may send no new wave, or None while it may (always None before wave 1)."""
    waves, opened = _sent(db, case_id)
    if opened is None:
        raise LookupError(f"No case {case_id}")
    if waves == 0:
        return None
    policy = policy_service.get_outreach_policy(db)
    if clock.now() >= opened + timedelta(seconds=policy.case_outreach_deadline_seconds):
        return ManualHandoffReason.OUTREACH_DEADLINE_REACHED
    if waves >= policy.maximum_waves_per_case:
        return ManualHandoffReason.WAVE_LIMIT_REACHED
    return None
