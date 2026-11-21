"""Offline deterministic adapter. No credentials, no network, no failure switches."""

from decimal import Decimal
from typing import Any

from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest


def _largest_term(candidate: dict[str, Any]) -> tuple[str, str] | None:
    best: tuple[float, str, str] | None = None
    for term in candidate.get("terms") or []:
        try:
            points = float(term["points"])
            name = str(term["name"])
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or points > best[0]:
            best = (points, name, str(term["points"]))
    return None if best is None else (best[1], best[2])


def _text(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("work_type") == "CASE_SUMMARY":
        return (
            f"[fake] สถานะเคส {payload['case_status']} "
            f"ข้อเสนอที่บันทึกไว้ {payload['offer_count']} รายการ"
        )
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        return "[fake] ไม่มีข้อมูลผู้สมัครสำหรับแผนนี้"
    first = candidates[0]
    wave = "อยู่ในกลุ่มแรก" if first.get("first_wave") else "อยู่ในกลุ่มสำรอง"
    text = f"[fake] อันดับ {first.get('rank', 1)} {wave}"
    largest = _largest_term(first)
    if largest is not None:
        text += f" โดยปัจจัยที่มากที่สุดคือ {largest[0]} จำนวน {largest[1]} คะแนน"
    return text


def generate(request: LlmRequest) -> LlmAttempt:
    text = _text(request.payload)
    input_tokens = len(request.prompt) // 4 + 1
    output_tokens = len(text) // 4 + 1
    return LlmAttempt(
        status=LlmCallStatus.SUCCEEDED,
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        duration_ms=0,
        error_type=None,
        provider="fake",
        model_id=None,
        region=None,
        input_rate=Decimal(0),
        output_rate=Decimal(0),
    )
