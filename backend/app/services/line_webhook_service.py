"""Signed event adapter. One event owns one transaction, including deduplication."""

import base64
import hashlib
import hmac
import logging
import re
from typing import Any
from urllib.parse import parse_qs

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.db.models import LineWebhookEvent
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    CandidateResponse,
    CheckInSource,
    OutreachStatus,
)
from app.domain.errors import ShiftNotFoundError
from app.integrations.line import client
from app.services import (
    attendance_service,
    auth_service,
    line_account_service,
    line_contact_service,
    outreach_service,
    registration_service,
    unavailability_service,
)

logger = logging.getLogger(__name__)
_LINK_COMMAND = re.compile(r"LINK(?:\s+|$)", re.IGNORECASE | re.ASCII)
_OFFER_BUTTON_GUIDANCE = (
    "หากต้องการตอบข้อเสนอเข้าเวร กรุณากดปุ่มในข้อความข้อเสนอที่ยังตอบได้ เพื่อบันทึกคำตอบ "
    "การพิมพ์แชตยังไม่ถือเป็นการตอบข้อเสนอค่ะ"
)
_LINK_GUIDANCE = (
    "สวัสดีค่ะ กรุณาผูกบัญชี LINE กับ Nara ก่อนใช้งาน โดยขอรหัสผูกบัญชีจากผู้ดูแล "
    "แล้วส่งข้อความ LINK <รหัสที่ได้รับ> มาที่แชตนี้ค่ะ"
)
_WAITING_GUIDANCE = "ระบบบันทึกการตอบรับของคุณแล้ว ขณะนี้อยู่ระหว่างรอผล กรุณารอการแจ้งยืนยันก่อนเข้าเวรค่ะ"
_IDLE_GUIDANCE = (
    "สวัสดีค่ะ นี่คือระบบแจ้งเตือนเวรของ Nara "
    "ขณะนี้คุณไม่มีข้อเสนอเข้าเวรที่รอดำเนินการ "
    "หากต้องการความช่วยเหลือ กรุณาติดต่อหัวหน้าหอค่ะ"
)


def _message_guidance(db: Session, uid: str) -> str:
    """Read the sender's current offers; never infer a response from their text."""
    staff = line_contact_service.staff_for_line_uid(db, uid)
    if staff is None:
        return _LINK_GUIDANCE
    offers = outreach_service.list_offers(db, staff_id=staff[0])
    if any(offer.can_accept or offer.can_reject for offer in offers):
        return _OFFER_BUTTON_GUIDANCE
    if any(
        offer.status == OutreachStatus.ACCEPTED
        and offer.case_status not in AUTOMATION_STOPPED_STATUSES
        and not offer.is_assigned
        and offer.final_outcome is None
        for offer in offers
    ):
        return _WAITING_GUIDANCE
    return _IDLE_GUIDANCE


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


def _check_in_event(db: Session, event: dict[str, Any], event_id: str) -> bool:
    """Adapt CHECKIN <shift_id> / CHECK_IN postbacks; identity never comes from data."""
    message = event.get("message")
    text = (
        message.get("text") if isinstance(message, dict) and message.get("type") == "text" else None
    )
    command = (
        re.match(r"CHECKIN(?:\s+|$)", text, re.IGNORECASE | re.ASCII)
        if isinstance(text, str) and event.get("type") == "message"
        else None
    )
    postback = event.get("postback")
    data = postback.get("data") if isinstance(postback, dict) else None
    params = (
        parse_qs(data, keep_blank_values=True)
        if isinstance(data, str) and event.get("type") == "postback"
        else {}
    )
    if command is None and "CHECK_IN" not in params.get("action", []):
        return False
    try:
        if command is not None:
            assert isinstance(text, str)
            raw_id = text[command.end() :].strip()
        else:
            params = parse_qs(data, keep_blank_values=True, strict_parsing=True)
            if (
                set(params) != {"action", "shift_id"}
                or any(len(v) != 1 for v in params.values())
                or params["action"] != ["CHECK_IN"]
            ):
                raise ValueError("Invalid check-in action")
            raw_id = params["shift_id"][0]
        if (
            not raw_id.isascii()
            or not raw_id.isdecimal()
            or len(raw_id) > 19
            or not 1 <= int(raw_id) <= MAX_BIGINT
        ):
            raise ValueError("Invalid shift ID")
    except (ValueError, KeyError):
        if _business_refusal(db, event_id):
            _reply(db, event, "คำสั่งเช็กอินไม่ถูกต้อง ใช้ CHECKIN ตามด้วยเลขเวร")
        return True
    source = event.get("source")
    uid = (
        source.get("userId") if isinstance(source, dict) and source.get("type") == "user" else None
    )
    staff = line_contact_service.staff_for_line_uid(db, uid) if isinstance(uid, str) else None
    if staff is None:
        if _business_refusal(db, event_id):
            _reply(db, event, "กรุณาเช็กอินจากบัญชี LINE ส่วนตัวที่ผูกกับพนักงานแล้ว")
        return True
    try:
        result = attendance_service.check_in(
            db,
            staff_id=staff[0],
            actor_id=staff[1],
            shift_id=int(raw_id),
            source=CheckInSource.SELF,
            after_lock=lambda session: _remember(session, event_id),
        )
    except (
        ShiftNotFoundError,
        unavailability_service.NoAssignedRosterError,
        attendance_service.CheckInOutsideWindowError,
    ):
        if _business_refusal(db, event_id):
            _reply(db, event, "เช็กอินไม่ได้ กรุณาตรวจเวรที่ได้รับมอบหมายและช่วงเวลาที่เปิดเช็กอิน")
        return True
    at = result.check_in_at.astimezone(clock.APP_TIMEZONE).strftime("%H:%M")
    timing = "ทันเวลา" if result.on_time else "มาสาย"
    message = (
        f"คุณเช็กอินเวร {result.shift_id} แล้ว เวลา {at} น. ({timing}) ไม่ต้องเช็กอินซ้ำ"
        if result.already_checked_in
        else f"เช็กอินเวร {result.shift_id} สำเร็จ เวลา {at} น. ({timing})"
    )
    _reply(db, event, message)
    return True


def _is_my_id(event: dict[str, Any]) -> bool:
    message = event.get("message")
    text = message.get("text") if isinstance(message, dict) else None
    return bool(
        event.get("type") == "message"
        and isinstance(message, dict)
        and message.get("type") == "text"
        and isinstance(text, str)
        and re.fullmatch(r"MYID[ \t\r\n]*", text, re.IGNORECASE | re.ASCII)
    )


def _my_id_event(db: Session, event: dict[str, Any], event_id: str) -> bool:
    """MYID reveals only the active private sender's own staff ID, never a supplied ID."""
    if not _is_my_id(event):
        return False
    source = event.get("source")
    # Never disclose staff identity in a group or room.
    if not isinstance(source, dict) or source.get("type") != "user":
        _remember(db, event_id)
        db.commit()
        return True
    uid = source.get("userId")
    staff = (
        line_contact_service.staff_for_line_uid(db, uid) if isinstance(uid, str) and uid else None
    )
    reply = f"รหัสพนักงาน NARA ของคุณคือ {staff[0]}" if staff is not None else _LINK_GUIDANCE
    _remember(db, event_id)
    db.commit()
    _reply(db, event, reply)
    return True


def _is_register(event: dict[str, Any]) -> bool:
    message = event.get("message")
    text = message.get("text") if isinstance(message, dict) else None
    return bool(
        event.get("type") == "message"
        and isinstance(message, dict)
        and message.get("type") == "text"
        and isinstance(text, str)
        and re.fullmatch(r"REGISTER[ \t\r\n]*", text, re.IGNORECASE | re.ASCII)
    )


def _register_event(db: Session, event: dict[str, Any], event_id: str) -> None:
    source = event.get("source")
    uid = source.get("userId") if isinstance(source, dict) else None
    try:
        if (
            not isinstance(source, dict)
            or source.get("type") != "user"
            or not isinstance(uid, str)
            or not 1 <= len(uid) <= 255
        ):
            raise registration_service.RegistrationError("Invalid sender")
        issued = registration_service.issue(db, uid)
    except registration_service.RegistrationError as error:
        if _business_refusal(db, event_id):
            message = (
                "คุณมีบัญชีเว็บแล้ว กรุณาเข้าสู่ระบบ หรือติดต่อผู้ดูแลหากลืมรหัสผ่าน"
                if isinstance(error, registration_service.AlreadyRegisteredError)
                else "ขอรหัสบ่อยเกินไป กรุณารออย่างน้อยหนึ่งนาทีแล้วส่ง REGISTER อีกครั้ง"
                if isinstance(error, registration_service.IssuanceLimitedError)
                else "กรุณาส่ง REGISTER จากบัญชี LINE ส่วนตัวที่ผูกกับพนักงานที่พร้อมใช้งานแล้ว"
            )
            _reply(db, event, message)
        return
    _remember(db, event_id)
    db.commit()
    _reply(
        db,
        event,
        (
            "รหัสสมัครบัญชีเว็บ Nara (ใช้ได้ครั้งเดียวภายใน 10 นาที):\n"
            f"{issued.code.get_secret_value()}\n"
            "เปิดหน้าสมัครสมาชิกของเว็บ Nara แล้วกรอกรหัสนี้พร้อมตั้งรหัสผ่าน "
            "ห้ามส่งรหัสนี้ให้ผู้อื่น หากไม่ได้รับรหัสหรือรหัสหมดอายุให้ส่ง REGISTER ใหม่"
        ),
    )


def process_event(db: Session, event: dict[str, Any]) -> None:
    """Process an event or raise for retry. Expected refusals are terminal, not HTTP errors.

    LINK text is handled before binding lookup. Unsupported event types are
    acknowledged without workflow changes. Each LINK owns its dedup transaction.
    """
    event_id = event.get("webhookEventId")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 256:
        raise ValueError("Missing or invalid webhook event ID")
    if _is_register(event) or _is_my_id(event):
        # Before even the dedup read: reset takes the exclusive gate before table locks.
        auth_service.hold_auth_gate(db)
    if db.get(LineWebhookEvent, event_id) is not None:
        db.rollback()
        return
    try:
        if _is_register(event):
            _register_event(db, event, event_id)
            return
        if _my_id_event(db, event, event_id):
            return
        if _check_in_event(db, event, event_id):
            return
        message = event.get("message")
        text = message.get("text") if isinstance(message, dict) else None
        command = _LINK_COMMAND.match(text) if isinstance(text, str) else None
        if (
            event.get("type") == "message"
            and isinstance(message, dict)
            and message.get("type") == "text"
            and isinstance(text, str)
            and command is not None
        ):
            source = event.get("source")
            uid = source.get("userId") if isinstance(source, dict) else None
            if (
                not isinstance(source, dict)
                or source.get("type") != "user"
                or not isinstance(uid, str)
            ):
                raise line_account_service.InvalidLinkCodeError("Invalid LINE sender")
            line_account_service.link(db, text[command.end() :].strip(), uid)
            _remember(db, event_id)
            db.commit()
            _reply(db, event, "ผูกบัญชี LINE สำเร็จแล้ว")
            return
        if event.get("type") != "postback":
            # Read status before dedup commits, then use the existing post-commit
            # reply path. Incoming text is never persisted, interpreted or echoed.
            source = event.get("source")
            guidance = None
            if (
                event.get("type") == "message"
                and isinstance(source, dict)
                and source.get("type") == "user"
                and isinstance(source.get("userId"), str)
                and source["userId"]
            ):
                guidance = _message_guidance(db, source["userId"])
            _remember(db, event_id)
            db.commit()
            if guidance is not None:
                _reply(db, event, guidance)
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
        outreach, _ = outreach_service.record_response(
            db,
            staff_id=staff[0],
            actor_id=staff[1],
            outreach_id=outreach_id,
            response=response,
            after_lock=lambda session: _remember(session, event_id),
        )
        # Report the current response order, not the Solver's provisional rank.
        accepted_as_reserve = False
        if response == CandidateResponse.ACCEPT:
            accepted_as_reserve = any(
                view.id == outreach.id and view.is_reserve
                for view in outreach_service.list_offers(db, staff_id=staff[0])
            )
    except IntegrityError as error:
        db.rollback()
        if _duplicate(error):
            return
        raise
    except line_account_service.LineAccountError as error:
        if _business_refusal(db, event_id):
            _reply(
                db,
                event,
                "บัญชี LINE หรือพนักงานนี้ผูกบัญชีแล้ว ให้ผู้ดูแลปลดก่อน"
                if isinstance(error, line_account_service.LineAccountAlreadyBoundError)
                else "รหัสผูกบัญชีไม่ถูกต้อง หมดอายุ ถูกใช้แล้ว หรือพนักงานไม่พร้อมใช้งาน",
            )
        return
    except outreach_service.OpenOfferConflictError as error:
        if _business_refusal(db, event_id):
            _reply(
                db,
                event,
                "ข้อเสนอนี้หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้"
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
        else "บันทึกการตอบรับแล้ว ขณะนี้คุณเป็นตัวสำรอง กรุณารอการยืนยันก่อนเข้าเวร"
        if accepted_as_reserve
        else "บันทึกคำตอบแล้ว โปรดตรวจสถานะล่าสุด การตอบรับยังไม่ยืนยันให้เข้าเวร",
    )
