"""Project authoritative final-outcome audits into a transactional notification outbox.

Called by audit_service after flushing the audit, never by reads or a backfill job.
No commit, network, workflow transition or additional lock acquisition here: the
writer already owns the offer/workflow locks. Unique (outreach_id, kind) makes
repeated audits one logical notice; each retry offer has a different outreach_id.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    OfferOutcomeNotification,
    RosterAssignment,
    Shift,
    StaffingCase,
    StructuredHandover,
    Ward,
)
from app.domain.enums import AUTOMATION_STOPPED_STATUSES, AuditAction, CaseStatus, OutreachStatus
from app.services import line_contact_service

DIRECT_REASONS = {
    AuditAction.APPROVAL_REJECTED: "APPROVAL_REJECTED",
    AuditAction.APPROVAL_TIMEOUT: "APPROVAL_TIMEOUT",
    AuditAction.OFFER_TIMEOUT: "OFFER_TIMEOUT",
    AuditAction.TRANSFER_CHECK_FAILED: "TRANSFER_CHECK_FAILED",
    AuditAction.SAFETY_FAILED: "SAFETY_FAILED",
}
LIST_REASONS = {
    AuditAction.CASE_RESOLVED: "CASE_RESOLVED",
    AuditAction.MANUAL_HANDOFF: "MANUAL_HANDOFF",
    AuditAction.ASSIGNMENT_CREATED: "CONFLICTING_ASSIGNMENT",
    AuditAction.ASSIGNMENT_TRANSFERRED: "CONFLICTING_ASSIGNMENT",
    AuditAction.MANUAL_ASSIGNMENT_CREATED: "CONFLICTING_ASSIGNMENT",
    AuditAction.CASE_CLOSED_UNRESOLVED: "CANCELLED",
}
WORDING = {
    "APPROVAL_REJECTED": "ไม่ได้รับอนุมัติ",
    "APPROVAL_TIMEOUT": "หมดเวลารออนุมัติแล้ว",
    "OFFER_TIMEOUT": "หมดเวลาตอบรับแล้ว",
    "CASE_RESOLVED": "ถูกยกเลิก เนื่องจากจัดคนครบแล้ว",
    "NO_LONGER_NEEDED": "ถูกยกเลิก เนื่องจากไม่ต้องการคนแทนเพิ่มเติมในช่วงนี้แล้ว",
    "CONFLICTING_ASSIGNMENT": "ถูกยกเลิก เนื่องจากคุณได้รับมอบหมายเวรอื่นที่ขัดกับช่วงเวลานี้",
    "TRANSFER_CHECK_FAILED": "ถูกยกเลิก เนื่องจากไม่สามารถย้ายมาช่วยเวรนี้ได้",
    "SAFETY_FAILED": "ถูกยกเลิก เนื่องจากไม่ผ่านเงื่อนไขการจัดเวร",
    "MANUAL_HANDOFF": "ถูกยกเลิก โดยหัวหน้าจะดำเนินการจัดคนต่อ",
    "EXECUTION_FAILED": "ยังไม่สามารถยืนยันการจัดเวรได้ กรุณาติดต่อหัวหน้าหอ",
    "CANCELLED": "ถูกยกเลิกแล้ว หากมีข้อสงสัย กรุณาติดต่อหัวหน้าหอ",
    "RESERVE_PROMOTED": ("คุณได้รับเลือกจากรายชื่อตัวสำรองแล้ว ขณะนี้กำลังรอหัวหน้าอนุมัติ ยังไม่ยืนยันให้เข้าเวร"),
}


def prepare_audit(db: Session, audit: AuditLog) -> None:
    """Use audit action/IDs, not CANCELLED alone; never expose free-text reasons."""
    action, payload = audit.action, audit.payload
    targets: dict[int, str] = {}
    if action == AuditAction.APPROVAL_REQUESTED:
        request_id = payload.get("approval_id")
        if not isinstance(request_id, int):
            return  # Historical/minimal timeline audits have no request reference.
        request = db.get(ApprovalRequest, request_id)
        offer = (
            db.get(CandidateOutreach, request.outreach_id)
            if request is not None and request.outreach_id is not None
            else None
        )
        if offer is not None and offer.accepted_as_reserve:
            _prepare(db, audit, offer.id, "RESERVE_PROMOTED", kind="RESERVE_PROMOTED")
        return
    if action in DIRECT_REASONS:
        if isinstance(payload.get("outreach_id"), int):
            targets[payload["outreach_id"]] = DIRECT_REASONS[action]
    elif action in LIST_REASONS:
        targets = {
            oid: LIST_REASONS[action]
            for oid in payload.get("cancelled_outreach_ids", [])
            if isinstance(oid, int)
        }
    elif action in {
        AuditAction.OFFER_CANCELLED_NOT_NEEDED,
        AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT,
    }:
        oid = payload.get("cancelled_outreach_id")
        if isinstance(oid, int):
            targets[oid] = (
                "NO_LONGER_NEEDED"
                if action == AuditAction.OFFER_CANCELLED_NOT_NEEDED
                else "CONFLICTING_ASSIGNMENT"
            )
    elif action == AuditAction.WORKFLOW_FAILED and audit.case_id is not None:
        # The D11 savepoint has rolled back execution. Previously committed
        # assignments survive; eligible() suppresses their failure notification.
        offers = list(
            db.scalars(
                select(CandidateOutreach).where(
                    CandidateOutreach.case_id == audit.case_id,
                    CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
                )
            )
        )
        approved_offer_ids = (
            set(
                db.scalars(
                    select(ApprovalRequest.outreach_id).where(
                        ApprovalRequest.outreach_id.in_([offer.id for offer in offers]),
                        ApprovalRequest.is_approved.is_(True),
                        ApprovalRequest.is_pending.is_(False),
                    )
                )
            )
            if offers
            else set()
        )
        for offer in offers:
            targets[offer.id] = (
                "EXECUTION_FAILED" if offer.id in approved_offer_ids else "CANCELLED"
            )
    for oid, reason in targets.items():
        _prepare(db, audit, oid, reason)


def _prepare(
    db: Session, audit: AuditLog, outreach_id: int, reason: str, *, kind: str = "FINAL"
) -> None:
    offer = db.get(CandidateOutreach, outreach_id)
    if offer is None or offer.status in {OutreachStatus.REJECTED, OutreachStatus.FAILED}:
        return
    item = db.get(CandidateItem, offer.candidate_item_id)
    if item is None:
        raise LookupError("Outcome candidate is missing")
    shift = db.get(Shift, item.proposed_shift_id)
    if shift is None:
        raise LookupError("Outcome shift is missing")
    ward = db.get(Ward, shift.ward_id)
    if ward is None:
        raise LookupError("Outcome ward is missing")
    start = (item.cover_start_at or shift.start_at).astimezone(clock.APP_TIMEZONE)
    end = (item.cover_end_at or shift.end_at).astimezone(clock.APP_TIMEZONE)
    message = (
        f"ข้อเสนอเข้าเวร #{offer.id} หอ {ward.name}\n"
        f"วันที่ {start:%d/%m/%Y} เวลา {start:%H:%M} น. "
        f"ถึงวันที่ {end:%d/%m/%Y} เวลา {end:%H:%M} น. (เวลาไทย)\n"
        f"{WORDING.get(reason, WORDING['CANCELLED'])}"
        + ("\nคุณไม่ได้รับมอบหมายให้เข้าเวรจากข้อเสนอนี้" if kind == "FINAL" else "")
    )
    values: dict[str, Any] = {
        "outreach_id": offer.id,
        "kind": kind,
        "case_id": offer.case_id,
        "staff_id": item.staff_id,
        "audit_id": audit.id,
        "reason": reason,
        "message": message,
        "created_at": clock.now(),
        "delivery_attempts": 0,
    }
    if settings.real_line_enabled:
        uid = line_contact_service.line_uid_for_staff(db, item.staff_id)
        values["delivery_status"] = "NO_CONTACT" if uid is None else "PENDING"
        if uid is not None:
            values.update(
                delivery_payload={"to": uid, "messages": [{"type": "text", "text": message}]},
                delivery_retry_key=str(uuid4()),
                delivery_next_attempt_at=clock.now(),
            )
    db.execute(
        insert(OfferOutcomeNotification)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["outreach_id", "kind"])
    )


def eligible(db: Session, row: OfferOutcomeNotification) -> bool:
    """A later confirmed assignment for this case/person/interval wins over failure.

    Unrelated roster rows and successful offers in other cases do not suppress
    this outcome. Handover snapshots are durable proof of successful execution,
    including after a later transfer/completion, unlike an approved flag alone.
    """
    offer = db.get(CandidateOutreach, row.outreach_id, populate_existing=True)
    if offer is None or offer.status in {OutreachStatus.REJECTED, OutreachStatus.FAILED}:
        return False
    item = db.get(CandidateItem, offer.candidate_item_id)
    if item is None:
        return False
    shift = db.get(Shift, item.proposed_shift_id)
    if shift is None:
        return False
    start, end = item.cover_start_at or shift.start_at, item.cover_end_at or shift.end_at
    confirmed = db.scalar(
        select(StructuredHandover.id)
        .join(RosterAssignment, RosterAssignment.id == StructuredHandover.roster_assignment_id)
        .where(
            StructuredHandover.case_id == row.case_id,
            StructuredHandover.incoming_staff_id == row.staff_id,
            StructuredHandover.shift_id == item.proposed_shift_id,
            func.coalesce(RosterAssignment.actual_start_at, shift.start_at) < end,
            func.coalesce(RosterAssignment.actual_end_at, shift.end_at) > start,
        )
        .limit(1)
    )
    if confirmed is not None:
        return False
    case = db.get(StaffingCase, row.case_id, populate_existing=True)
    if row.kind == "RESERVE_PROMOTED":
        return (
            offer.status == OutreachStatus.ACCEPTED
            and case is not None
            and case.status not in AUTOMATION_STOPPED_STATUSES
            and db.scalar(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.outreach_id == offer.id,
                    ApprovalRequest.is_pending.is_(True),
                    ApprovalRequest.expires_at > clock.now(),
                )
            )
            is not None
        )
    if offer.status in {OutreachStatus.CANCELLED, OutreachStatus.TIMEOUT}:
        return True
    # D11 deliberately preserves accepted offers; other nonterminal states may
    # not receive cancellation/failure notices after a case has resumed.
    return case is not None and case.status == CaseStatus.FAILED
