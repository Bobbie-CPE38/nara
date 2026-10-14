"""Signed event adapter. One event owns one transaction, including deduplication."""

import base64
import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import parse_qs

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.db.models import LineWebhookEvent
from app.domain.enums import CandidateResponse
from app.integrations.line import client
from app.services import line_contact_service, outreach_service

logger = logging.getLogger(__name__)


def valid_signature(body: bytes, signature: str | None) -> bool:
    secret = settings.line_channel_secret
    if secret is None or signature is None:
        return False
    expected = base64.b64encode(
        hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).digest()
    )
    return hmac.compare_digest(expected, signature.encode())


def _remember(db: Session, event_id: str) -> None:
    db.add(LineWebhookEvent(webhook_event_id=event_id))
    db.flush()


def _duplicate(error: IntegrityError) -> bool:
    return (
        getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        == "pk_line_webhook_event"
    )


def _reply(db: Session, event: dict[str, Any], message: str) -> None:
    token = event.get("replyToken")
    if not isinstance(token, str) or not token:
        return
    schedule = db.info.get("line_reply_scheduler")
    if schedule is not None:
        schedule(token, message)
        return
    send_reply(token, message)


def send_reply(token: str, message: str) -> None:
    """Best-effort, no database access; also used by response background work."""
    try:
        result = client.reply(token, message)
        if not result.startswith("2"):
            logger.warning("LINE reply was not accepted (%s)", result)
    except Exception as error:
        logger.warning("LINE reply failed (%s)", type(error).__name__)


def _business_refusal(db: Session, event_id: str) -> bool:
    db.rollback()
    try:
        _remember(db, event_id)
        db.commit()
        return True
    except IntegrityError as error:
        db.rollback()
        if _duplicate(error):
            return False
        raise


def process_event(db: Session, event: dict[str, Any]) -> None:
    """Process an event or raise for retry. Expected refusals are terminal, not HTTP errors.

    Unsupported event types are acknowledged without workflow changes. PR K
    extends this dispatcher for LINK messages using the same event table.
    """
    event_id = event.get("webhookEventId")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 256:
        raise ValueError("Missing or invalid webhook event ID")
    if db.get(LineWebhookEvent, event_id) is not None:
        db.rollback()
        return
    try:
        if event.get("type") != "postback":
            _remember(db, event_id)
            db.commit()
            return
        source = event.get("source", {})
        uid = source.get("userId") if isinstance(source, dict) else None
        staff = line_contact_service.staff_for_line_uid(db, uid) if isinstance(uid, str) else None
        if staff is None:
            if _business_refusal(db, event_id):
                _reply(db, event, "ยังไม่ได้ผูกบัญชี LINE กับพนักงาน")
            return
        postback = event.get("postback", {})
        data = postback.get("data") if isinstance(postback, dict) else None
        try:
            params = parse_qs(data, strict_parsing=True) if isinstance(data, str) else {}
            if set(params) != {"outreach_id", "response"} or any(
                len(v) != 1 for v in params.values()
            ):
                raise ValueError("Invalid offer action")
            raw_id = params["outreach_id"][0]
            if not raw_id.isascii() or not raw_id.isdecimal() or len(raw_id) > 19:
                raise ValueError("Invalid offer ID")
            outreach_id = int(raw_id)
            if not 1 <= outreach_id <= MAX_BIGINT:
                raise ValueError("Invalid offer ID")
            response = CandidateResponse(params["response"][0])
        except (ValueError, KeyError):
            if _business_refusal(db, event_id):
                _reply(db, event, "ข้อมูลข้อเสนอไม่ถูกต้อง กรุณาดูข้อเสนอล่าสุด")
            return
        outreach_service.record_response(
            db,
            staff_id=staff[0],
            actor_id=staff[1],
            outreach_id=outreach_id,
            response=response,
            after_lock=lambda session: _remember(session, event_id),
        )
    except IntegrityError as error:
        db.rollback()
        if _duplicate(error):
            return
        raise
    except outreach_service.OpenOfferConflictError as error:
        if _business_refusal(db, event_id):
            _reply(
                db,
                event,
                "ข้อเสนอนี้หมดเวลาแล้ว"
                if isinstance(error, outreach_service.OfferExpiredError)
                else "ข้อเสนอนี้ตอบไม่ได้แล้ว หรือกำลังรอผลอนุมัติจากเคสอื่น",
            )
        logger.info("LINE offer response refused (%s)", type(error).__name__)
        return
    except Exception:
        db.rollback()
        # Post-commit notifications cannot turn a committed answer into failure.
        if db.get(LineWebhookEvent, event_id) is not None:
            db.rollback()
            logger.warning("LINE post-commit work deferred")
            return
        db.rollback()
        raise
    _reply(
        db,
        event,
        "บันทึกการปฏิเสธข้อเสนอแล้ว"
        if response == CandidateResponse.REJECT
        else "บันทึกคำตอบแล้ว โปรดตรวจสถานะล่าสุด การตอบรับยังไม่ยืนยันให้เข้าเวร",
    )
