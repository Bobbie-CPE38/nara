"""Offer expiry and recovery of missed foreign-case notifications (round 1 PR O).

Each case owns a separate transaction. All changes use backend clock time and
Offer → Case → whole-plan Staff locks. Only this job changes SENT to TIMEOUT;
response/read paths reject overdue offers without writing them.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidateOutreach, StaffingCase
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
    OutreachStatus,
)
from app.services import actor_service, audit_service, case_facts_service, outreach_service
from app.workflow import orchestrator

logger = logging.getLogger(__name__)

# Per-process, bounded diagnostic suppression; retries still run every tick.
_failure_counts: dict[tuple[str, int, type[Exception]], int] = {}


def _clear_failures(operation: str, case_id: int) -> None:
    for key in list(_failure_counts):
        if key[:2] == (operation, case_id):
            del _failure_counts[key]


def _log_failure(operation: str, case_id: int, error: Exception) -> None:
    key = (operation, case_id, type(error))
    if key not in _failure_counts and len(_failure_counts) >= 1024:
        del _failure_counts[next(iter(_failure_counts))]
    count = _failure_counts.get(key, 0) + 1
    _failure_counts[key] = count
    if count == 1 or count % 120 == 0:
        logger.exception(
            "%s for case %s failed (%s consecutive failures); retry next tick",
            operation,
            case_id,
            count,
        )


def _needs_recovery(db: Session, case: StaffingCase) -> bool:
    if case.status not in WAITING_CASE_STATUSES:
        return False
    facts = case_facts_service.load_case_facts(db, case)
    if case.status == CaseStatus.WAITING_APPROVAL:
        return not facts.has_pending_approval or facts.gap_closed_by_assigned
    has_sent = (
        db.scalar(
            select(CandidateOutreach.id)
            .where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.status == OutreachStatus.SENT,
            )
            .limit(1)
        )
        is not None
    )
    return not facts.has_open_offer and (
        not has_sent
        or (facts.has_paused_offer and facts.has_uncontacted_candidate)
        or facts.gap_closed_with_pending
    )


@dataclass
class ExpiredOffers:
    outreach_ids: list[int] = field(default_factory=list)
    failed_case_ids: set[int] = field(default_factory=set)


def expire_due_offers(db: Session) -> ExpiredOffers:
    """Expire due SENT rows and recompute, preserving timeouts on D11 failure.

    The caller must have no uncommitted writes. Scan without retaining a read
    transaction, then recheck each case after locking. A failed case round rolls
    back and is retried next tick; it does not prevent other cases being processed.
    """
    cutoff = clock.now()
    case_ids = list(
        db.scalars(
            select(CandidateOutreach.case_id)
            .where(
                CandidateOutreach.status == OutreachStatus.SENT,
                CandidateOutreach.expires_at <= cutoff,
            )
            .distinct()
            .order_by(CandidateOutreach.case_id)
        )
    )
    db.rollback()
    result = ExpiredOffers()
    for case_id in case_ids:
        try:
            case = outreach_service.lock_case_for_outreach(db, case_id)
            now = clock.now()  # A response may have committed while this job waited.
            rows = list(
                db.execute(
                    select(CandidateOutreach, CandidateItem.staff_id)
                    .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
                    .where(
                        CandidateOutreach.case_id == case_id,
                        CandidateOutreach.status == OutreachStatus.SENT,
                        CandidateOutreach.expires_at <= now,
                    )
                    .order_by(CandidateOutreach.id)
                )
            )
            if not rows:
                db.rollback()
                continue
            actor_id = actor_service.component_id(db, ActorName.OUTREACH_AGENT)
            ids = []
            for outreach, staff_id in rows:
                outreach.status = OutreachStatus.TIMEOUT
                audit_service.log(
                    db,
                    case_id=case_id,
                    actor_id=actor_id,
                    action=AuditAction.OFFER_TIMEOUT,
                    entity_type=EntityType.CANDIDATE_OUTREACH,
                    entity_id=outreach.id,
                    payload={"outreach_id": outreach.id, "staff_id": staff_id},
                )
                ids.append(outreach.id)
            if case.status in WAITING_CASE_STATUSES or case.status in AUTOMATION_STOPPED_STATUSES:
                orchestrator.recompute(db, case.id, prepare=outreach_service.promote_reserves)
            else:
                # Persist expiry even for legacy/inconsistent active phases. The
                # job cannot drive those phases through recompute's wait API.
                logger.error(
                    "Expired offers for non-waiting case %s (%s); manual repair required",
                    case.id,
                    case.status.value,
                )
                db.commit()
            _clear_failures("Offer expiry", case_id)
            result.outreach_ids.extend(ids)
        except Exception as error:
            db.rollback()
            _log_failure("Offer expiry", case_id, error)
            result.failed_case_ids.add(case_id)
    return result


def recover_waiting_cases(db: Session, *, excluded_case_ids: set[int]) -> list[int]:
    """Recompute only stranded response waits under the agreed case locks.

    Recover no-SENT cases, or paused-only cases with an uncontacted candidate.
    Legitimate paused-only waits stay untouched until a result or their deadline.
    Also recover coverage already closed by pending/assigned candidates, whose
    missed notification left the case at WAITING_RESPONSE. Stale WAITING_APPROVAL
    cases with no actionable pending request are recovered too; a real pending
    approval is handled separately by approval_timeout_service.
    """
    case_ids = list(
        db.scalars(
            select(StaffingCase.id)
            .where(
                StaffingCase.status.in_([CaseStatus.WAITING_RESPONSE, CaseStatus.WAITING_APPROVAL]),
                StaffingCase.id.not_in(excluded_case_ids),
            )
            .order_by(StaffingCase.id)
        )
    )
    db.rollback()
    recovered = []
    for case_id in case_ids:
        try:
            # Read without row locks first. This is a hint, not an authoritative
            # snapshot: only apparently stranded cases acquire the shared locks.
            with db.no_autoflush:
                case = db.get(StaffingCase, case_id, populate_existing=True)
                needs_retry = case is not None and _needs_recovery(db, case)
            db.rollback()
            if not needs_retry:
                _clear_failures("Recovery", case_id)
                continue
            case = outreach_service.lock_case_for_outreach(db, case_id)
            if not _needs_recovery(db, case):
                db.rollback()
                _clear_failures("Recovery", case_id)
                continue
            orchestrator.recompute(db, case_id, prepare=outreach_service.promote_reserves)
            _clear_failures("Recovery", case_id)
            recovered.append(case_id)
        except Exception as error:
            db.rollback()
            _log_failure("Recovery", case_id, error)
    return recovered
