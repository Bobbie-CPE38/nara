"""Offer-row outbox: claim under workflow locks, release, send, lock and recheck.

Claims survive restarts. A 60-second lease exceeds the five-second HTTP timeout.
Retries use the same recipient, body and UUID, including after a crash. No HTTP
request holds database locks. Callers have no uncommitted work.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import CandidateItem, CandidateOutreach, Shift, Ward
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    AuditAction,
    EntityType,
    OutreachStatus,
)
from app.integrations.line import client
from app.services import actor_service, audit_service, line_contact_service, outreach_service

logger = logging.getLogger(__name__)


def prepare_delivery(db: Session, outreach: CandidateOutreach, item: CandidateItem) -> None:
    """Persist an immutable intent alongside the new offer, without network I/O."""
    uid = line_contact_service.line_uid_for_staff(db, item.staff_id)
    if uid is None:
        outreach.delivery_status = "NO_CONTACT"
        return
    shift = db.get(Shift, item.proposed_shift_id)
    if shift is None:
        raise LookupError("Offer shift is missing")
    ward = db.get(Ward, shift.ward_id)
    if ward is None:
        raise LookupError("Offer ward is missing")
    outreach.delivery_status = "PENDING"
    outreach.delivery_retry_key = str(uuid4())
    outreach.delivery_next_attempt_at = clock.now()
    if uid:
        message = (
            f"ข้อเสนอเข้าเวร: {ward.name}\n"
            f"{shift.start_at.astimezone(clock.APP_TIMEZONE):%d/%m/%Y %H:%M} – "
            f"{shift.end_at.astimezone(clock.APP_TIMEZONE):%d/%m/%Y %H:%M}\n"
            f"ตอบก่อน {outreach.expires_at.astimezone(clock.APP_TIMEZONE):%d/%m/%Y %H:%M}\n"
            "การตอบรับยังต้องรอหัวหน้าอนุมัติ"
            if outreach.expires_at is not None
            else "ข้อเสนอเข้าเวร"
        )
        outreach.delivery_payload = {
            "to": uid,
            "messages": [
                {
                    "type": "template",
                    "altText": "ข้อเสนอเข้าเวรจาก Nara",
                    "template": {
                        "type": "confirm",
                        "text": message[:240],
                        "actions": [
                            {
                                "type": "postback",
                                "label": label,
                                "data": f"outreach_id={outreach.id}&response={response}",
                            }
                            for label, response in (("รับข้อเสนอ", "ACCEPT"), ("ปฏิเสธ", "REJECT"))
                        ],
                    },
                }
            ],
        }


@dataclass(frozen=True)
class Claim:
    outreach_id: int
    case_id: int
    token: str
    payload: dict[str, Any]
    retry_key: str
    exhausted: bool


def _live(outreach: CandidateOutreach, stopped: bool) -> bool:
    return bool(
        outreach.status == OutreachStatus.SENT
        and not stopped
        and outreach.expires_at is not None
        and clock.now() < outreach.expires_at
    )


def _claim(db: Session, outreach_id: int) -> Claim | None:
    row = db.get(CandidateOutreach, outreach_id)
    if row is None:
        db.rollback()
        return None
    case_id = row.case_id
    case = outreach_service.lock_case_for_outreach(db, case_id)
    row = db.get(CandidateOutreach, outreach_id, populate_existing=True)
    if row is None or row.delivery_status != "PENDING":
        db.rollback()
        return None
    if not _live(row, case.status in AUTOMATION_STOPPED_STATUSES):
        row.delivery_status = "CANCELLED"
        row.delivery_claim = None
        row.delivery_lease_until = None
        db.commit()
        return None
    now = clock.now()
    if (row.delivery_lease_until is not None and row.delivery_lease_until > now) or (
        row.delivery_next_attempt_at is not None and row.delivery_next_attempt_at > now
    ):
        db.rollback()
        return None
    if not row.delivery_retry_key or row.delivery_payload is None:
        raise RuntimeError("Delivery intent has no retry key or payload")
    token = str(uuid4())
    exhausted = row.delivery_attempts >= 3
    if not exhausted:
        row.delivery_attempts += 1
    row.delivery_claim = token
    row.delivery_lease_until = now + timedelta(seconds=60)
    claim = Claim(row.id, case_id, token, row.delivery_payload, row.delivery_retry_key, exhausted)
    db.commit()
    return claim


def _finish(db: Session, claim: Claim, result: str) -> bool:
    """Persist the outcome; True asks this sweep to stop for credential errors."""
    from app.workflow import orchestrator

    case = outreach_service.lock_case_for_outreach(db, claim.case_id)
    row = db.get(CandidateOutreach, claim.outreach_id, populate_existing=True)
    if row is None or row.delivery_claim != claim.token or row.delivery_status != "PENDING":
        db.rollback()
        return False
    row.delivery_claim = None
    row.delivery_lease_until = None
    row.delivery_last_result = result
    if not _live(row, case.status in AUTOMATION_STOPPED_STATUSES):
        row.delivery_status = "CANCELLED"
        db.commit()
        return False
    if result.startswith("2") or result == "409":
        row.delivery_status = "ACCEPTED"
        db.commit()
        return False
    if result in {"429", "401", "403"}:
        row.delivery_attempts -= 1
        row.delivery_next_attempt_at = clock.now() + timedelta(seconds=30)
        db.commit()
        logger.error("LINE delivery deferred: HTTP %s", result)
        return result in {"401", "403"}
    permanent = result.startswith("4")
    if not permanent and row.delivery_attempts < 3:
        row.delivery_next_attempt_at = clock.now() + timedelta(seconds=30)
        db.commit()
        return False
    row.delivery_status = "FAILED"
    row.status = OutreachStatus.FAILED
    staff_id = db.scalar(
        select(CandidateItem.staff_id).where(CandidateItem.id == row.candidate_item_id)
    )
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.OUTREACH_AGENT),
        action=AuditAction.OFFER_DELIVERY_FAILED,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=row.id,
        payload={
            "outreach_id": row.id,
            "staff_id": staff_id,
            "attempts": row.delivery_attempts,
            "last_result": result,
        },
    )
    # Outcome is outside the D11 savepoint: workflow failure must not undo it.
    orchestrator.recompute(db, case.id, prepare=outreach_service.promote_reserves)
    return False


def dispatch_pending(db: Session, *, case_id: int | None = None) -> None:
    """Best-effort post-commit work and job recovery; errors never escape to callers.

    At most 20 offers per sweep, oldest first, including new waves created by
    delivery failure. HTTP requests enqueue background work with a fresh session.
    The session guard prevents recursion while this sweep reloads due offers.
    """
    if not settings.real_line_enabled:
        return
    schedule = db.info.get("line_delivery_scheduler")
    if schedule is not None:
        schedule(case_id)
        return
    if db.info.get("line_dispatching"):
        return
    db.info["line_dispatching"] = True
    try:
        visited: set[int] = set()
        for _ in range(20):
            now = clock.now()
            query = (
                select(CandidateOutreach.id)
                .where(
                    CandidateOutreach.delivery_status == "PENDING",
                    CandidateOutreach.id.not_in(visited),
                    or_(
                        CandidateOutreach.delivery_next_attempt_at.is_(None),
                        CandidateOutreach.delivery_next_attempt_at <= now,
                    ),
                    or_(
                        CandidateOutreach.delivery_lease_until.is_(None),
                        CandidateOutreach.delivery_lease_until <= now,
                    ),
                )
                .order_by(CandidateOutreach.id)
                .limit(1)
            )
            if case_id is not None:
                query = query.where(CandidateOutreach.case_id == case_id)
            outreach_id = db.scalar(query)
            db.rollback()
            if outreach_id is None:
                break
            visited.add(outreach_id)
            try:
                claim = _claim(db, outreach_id)
                if claim is None:
                    continue
                result = (
                    "TIMEOUT" if claim.exhausted else client.push(claim.payload, claim.retry_key)
                )
                if _finish(db, claim, result):
                    break
            except Exception as error:
                db.rollback()
                # No remote body, database parameters or credentials in logs.
                logger.error("LINE delivery %s deferred (%s)", outreach_id, type(error).__name__)
    except Exception as error:
        db.rollback()
        logger.error("LINE delivery sweep deferred (%s)", type(error).__name__)
    finally:
        db.info.pop("line_dispatching", None)
