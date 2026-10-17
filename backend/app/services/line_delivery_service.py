"""Offer, Handover and final-outcome outboxes: lock, release, send, recheck.

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
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    OfferOutcomeNotification,
    RosterAssignment,
    Shift,
    StructuredHandover,
    Ward,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    AuditAction,
    EntityType,
    OutreachStatus,
    RosterStatus,
)
from app.integrations.line import client
from app.services import (
    actor_service,
    attendance_service,
    audit_service,
    line_contact_service,
    outreach_service,
)

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
    staff_id = db.scalar(
        select(CandidateItem.staff_id).where(CandidateItem.id == row.candidate_item_id)
    )
    if staff_id is None or line_contact_service.line_uid_for_staff(
        db, staff_id
    ) != row.delivery_payload.get("to"):
        # Unlink/rebind must not redirect an immutable intent to the old recipient.
        # Keep the offer answerable through simulator/web and its normal deadline.
        row.delivery_status = "NO_CONTACT"
        row.delivery_claim = None
        row.delivery_lease_until = None
        db.commit()
        return None
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
    if not _record_result(row, result):
        db.commit()
        return result in {"401", "403"}
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


def _record_result(
    row: CandidateOutreach | StructuredHandover | OfferOutcomeNotification, result: str
) -> bool:
    """Shared retry policy. Return True only for terminal delivery failure."""
    if result.startswith("2") or result == "409":
        row.delivery_status = "ACCEPTED"
    elif result in {"429", "401", "403"}:
        row.delivery_attempts -= 1
        row.delivery_next_attempt_at = clock.now() + timedelta(seconds=30)
        logger.error("LINE delivery deferred: HTTP %s", result)
    elif not result.startswith("4") and row.delivery_attempts < 3:
        row.delivery_next_attempt_at = clock.now() + timedelta(seconds=30)
    else:
        row.delivery_status = "FAILED"
        return True
    return False


def _check_in_instructions(roster: RosterAssignment, shift: Shift) -> str:
    """Use validation's exact local-time bounds, including partial/replacement shifts."""
    earliest = attendance_service.earliest_check_in_at(roster, shift).astimezone(clock.APP_TIMEZONE)
    end = attendance_service.effective_end_at(roster, shift).astimezone(clock.APP_TIMEZONE)
    return (
        "เมื่อมาถึงแล้ว กดเช็กอินเข้าเวร\n"
        f"กดได้ตั้งแต่ {earliest:%d/%m/%Y %H:%M:%S} น.\n"
        f"ถึงก่อน {end:%d/%m/%Y %H:%M:%S} น. (เวลาไทย)"
    )


def prepare_handover_delivery(db: Session, handover: StructuredHandover) -> None:
    """Write once, alongside the snapshot. No commit and no network."""
    uid = (
        line_contact_service.line_uid_for_staff(db, handover.incoming_staff_id)
        if handover.incoming_staff_id is not None
        else None
    )
    if uid is None:
        handover.delivery_status = "NO_CONTACT"
        return
    roster = db.get(RosterAssignment, handover.roster_assignment_id)
    shift = db.get(Shift, handover.shift_id)
    if roster is None or shift is None:
        raise LookupError("Handover assignment or shift is missing")
    check_in_text = _check_in_instructions(roster, shift)
    content = handover.content
    requirements = content["requirement"]
    detail = (
        f"ยืนยันการจัดเวร / Handover #{handover.id}\n"
        f"หอ: {content['shift']['ward_name']}\n"
        f"ช่วงทำงาน: {content['cover_start_at']} – {content['cover_end_at']}\n"
        f"เหตุ: {content['reason']} | ผู้ป่วย: {content['patient_count']}\n"
        "Role: "
        + ", ".join(f"{r['name']} {r['required_count']}" for r in requirements["roles"])
        + "\n"
        "Skill: "
        + ", ".join(f"{r['name']} {r['required_count']}" for r in requirements["skills"])
        + "\n"
        "เพื่อนร่วมเวร: " + ", ".join(c["name"] for c in content["co_workers"])
    )
    handover.delivery_status = "PENDING"
    handover.delivery_retry_key = str(uuid4())
    handover.delivery_next_attempt_at = clock.now()
    handover.delivery_payload = {
        "to": uid,
        "messages": [
            {"type": "text", "text": detail[:4900]},
            {
                "type": "template",
                "altText": "เช็กอินเวรที่ได้รับมอบหมาย",
                "template": {
                    "type": "buttons",
                    "text": check_in_text,
                    "actions": [
                        {
                            "type": "postback",
                            "label": "เช็กอิน",
                            "data": f"action=CHECK_IN&shift_id={handover.shift_id}",
                        }
                    ],
                },
            },
        ],
    }


@dataclass(frozen=True)
class HandoverClaim:
    handover_id: int
    token: str
    payload: dict[str, Any]
    retry_key: str
    exhausted: bool


def _lock_handover(db: Session, handover_id: int) -> tuple[StructuredHandover, bool] | None:
    """SHIFT → ROSTER → HANDOVER; no case lock (resolved cases still need delivery)."""
    row = db.get(StructuredHandover, handover_id)
    if row is None:
        return None
    shift = db.scalar(
        select(Shift)
        .where(Shift.id == row.shift_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    roster = db.scalar(
        select(RosterAssignment)
        .where(RosterAssignment.id == row.roster_assignment_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    row = db.scalar(
        select(StructuredHandover)
        .where(StructuredHandover.id == handover_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or shift is None or roster is None:
        return None
    active = roster.status == RosterStatus.ASSIGNED and clock.now() < (
        roster.actual_end_at or shift.end_at
    )
    return row, active


def _claim_handover(db: Session, handover_id: int) -> HandoverClaim | None:
    locked = _lock_handover(db, handover_id)
    if locked is None:
        db.rollback()
        return None
    row, active = locked
    if row.delivery_status != "PENDING":
        db.rollback()
        return None
    if not active:
        row.delivery_status = "CANCELLED"
        row.delivery_claim = row.delivery_lease_until = None
        db.commit()
        return None
    now = clock.now()
    if (row.delivery_lease_until is not None and row.delivery_lease_until > now) or (
        row.delivery_next_attempt_at is not None and row.delivery_next_attempt_at > now
    ):
        db.rollback()
        return None
    if not row.delivery_retry_key or row.delivery_payload is None:
        raise RuntimeError("Handover intent has no retry key or payload")
    if row.incoming_staff_id is None or line_contact_service.line_uid_for_staff(
        db, row.incoming_staff_id
    ) != row.delivery_payload.get("to"):
        row.delivery_status = "NO_CONTACT"
        row.delivery_claim = row.delivery_lease_until = None
        db.commit()
        return None
    exhausted = row.delivery_attempts >= 3
    if not exhausted:
        row.delivery_attempts += 1
    token = str(uuid4())
    row.delivery_claim = token
    row.delivery_lease_until = now + timedelta(seconds=60)
    claim = HandoverClaim(row.id, token, row.delivery_payload, row.delivery_retry_key, exhausted)
    db.commit()
    return claim


def _finish_handover(db: Session, claim: HandoverClaim, result: str) -> bool:
    locked = _lock_handover(db, claim.handover_id)
    if locked is None:
        db.rollback()
        return False
    row, active = locked
    if row.delivery_claim != claim.token or row.delivery_status != "PENDING":
        db.rollback()
        return False
    row.delivery_claim = row.delivery_lease_until = None
    row.delivery_last_result = result
    if not active:
        row.delivery_status = "CANCELLED"
    else:
        _record_result(row, result)
    # Delivery failure changes only the outbox: never roster/case/audit.
    db.commit()
    return result in {"401", "403"}


@dataclass(frozen=True)
class OutcomeClaim:
    notification_id: int
    token: str
    payload: dict[str, Any]
    retry_key: str
    exhausted: bool


def _lock_outcome(db: Session, notification_id: int) -> OfferOutcomeNotification | None:
    row = db.get(OfferOutcomeNotification, notification_id)
    if row is None:
        return None
    outreach_service.lock_case_for_outreach(db, row.case_id)
    return db.scalar(
        select(OfferOutcomeNotification)
        .where(OfferOutcomeNotification.id == notification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _claim_outcome(db: Session, notification_id: int) -> OutcomeClaim | None:
    from app.services import offer_outcome_service

    row = _lock_outcome(db, notification_id)
    if row is None or row.delivery_status != "PENDING":
        db.rollback()
        return None
    if not offer_outcome_service.eligible(db, row):
        row.delivery_status = "CANCELLED"
        row.delivery_claim = row.delivery_lease_until = None
        db.commit()
        return None
    now = clock.now()
    if (row.delivery_lease_until is not None and row.delivery_lease_until > now) or (
        row.delivery_next_attempt_at is not None and row.delivery_next_attempt_at > now
    ):
        db.rollback()
        return None
    if row.delivery_payload is None or not row.delivery_retry_key:
        raise RuntimeError("Outcome intent has no retry key or payload")
    if line_contact_service.line_uid_for_staff(db, row.staff_id) != row.delivery_payload.get("to"):
        row.delivery_status = "NO_CONTACT"
        row.delivery_claim = row.delivery_lease_until = None
        db.commit()
        return None
    exhausted = row.delivery_attempts >= 3
    if not exhausted:
        row.delivery_attempts += 1
    token = str(uuid4())
    row.delivery_claim = token
    row.delivery_lease_until = now + timedelta(seconds=60)
    claim = OutcomeClaim(row.id, token, row.delivery_payload, row.delivery_retry_key, exhausted)
    db.commit()
    return claim


def _finish_outcome(db: Session, claim: OutcomeClaim, result: str) -> bool:
    from app.services import offer_outcome_service

    row = _lock_outcome(db, claim.notification_id)
    if row is None or row.delivery_status != "PENDING" or row.delivery_claim != claim.token:
        db.rollback()
        return False
    row.delivery_claim = row.delivery_lease_until = None
    row.delivery_last_result = result
    if not offer_outcome_service.eligible(db, row):
        row.delivery_status = "CANCELLED"
    elif _record_result(row, result):
        logger.error(
            "LINE notification %s failed after %s attempts (%s)",
            row.id,
            row.delivery_attempts,
            result,
        )
    # An unsuccessful notification is never an unsuccessful offer delivery.
    db.commit()
    return result in {"401", "403"}


def dispatch_pending(db: Session, *, case_id: int | None = None) -> None:
    """Best-effort post-commit work and job recovery; errors never escape to callers.

    At most 20 rows of each kind per sweep, oldest first, including new waves created by
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
        for model in (CandidateOutreach, StructuredHandover, OfferOutcomeNotification):
            if _dispatch_model(db, model, case_id=case_id):
                break
    except Exception as error:
        db.rollback()
        logger.error("LINE delivery sweep deferred (%s)", type(error).__name__)
    finally:
        db.info.pop("line_dispatching", None)


def _dispatch_model(
    db: Session,
    model: type[CandidateOutreach] | type[StructuredHandover] | type[OfferOutcomeNotification],
    *,
    case_id: int | None,
) -> bool:
    visited: set[int] = set()
    for _ in range(20):
        now = clock.now()
        query = (
            select(model.id)
            .where(
                model.delivery_status == "PENDING",
                model.id.not_in(visited),
                or_(
                    model.delivery_next_attempt_at.is_(None),
                    model.delivery_next_attempt_at <= now,
                ),
                or_(
                    model.delivery_lease_until.is_(None),
                    model.delivery_lease_until <= now,
                ),
            )
            .order_by(model.id)
            .limit(1)
        )
        if case_id is not None:
            query = query.where(model.case_id == case_id)
        outreach_id = db.scalar(query)
        db.rollback()
        if outreach_id is None:
            break
        visited.add(outreach_id)
        try:
            if model is CandidateOutreach:
                claim: Claim | HandoverClaim | OutcomeClaim | None = _claim(db, outreach_id)
            elif model is StructuredHandover:
                claim = _claim_handover(db, outreach_id)
            else:
                claim = _claim_outcome(db, outreach_id)
            if claim is None:
                continue
            result = "TIMEOUT" if claim.exhausted else client.push(claim.payload, claim.retry_key)
            if isinstance(claim, Claim):
                stop = _finish(db, claim, result)
            elif isinstance(claim, HandoverClaim):
                stop = _finish_handover(db, claim, result)
            else:
                stop = _finish_outcome(db, claim, result)
            if stop:
                return True
        except Exception as error:
            db.rollback()
            # No remote body, database parameters or credentials in logs.
            logger.error("LINE delivery %s deferred (%s)", outreach_id, type(error).__name__)
    return False
