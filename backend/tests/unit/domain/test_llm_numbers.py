"""Numbers in an LLM sentence must be numbers of its payload (round 6 PR B1, R6-Q8 ก)."""

from decimal import Decimal

import pytest

from app.domain.llm_numbers import payload_numbers, unverified_numbers

PAYLOAD = {
    "candidate_count": 12,
    "plan_penalty": {"value": 1250, "meaning": "selects which group becomes the first wave"},
    "candidates": [
        {"rank": 1, "total": 0.3333333333333333, "terms": [{"points": 2.5, "weight": 1}]},
        {"rank": 2, "total": -4, "first_wave": True, "ranking_key": {"hours": "37.5"}},
    ],
}


def test_payload_numbers_reads_values_and_numbers_inside_strings() -> None:
    assert payload_numbers(PAYLOAD) == {
        Decimal(n) for n in ("12", "1250", "1", "0.3333333333333333", "2.5", "2", "4", "37.5")
    }


@pytest.mark.parametrize(
    "text",
    [
        "อันดับ 1 และอันดับ 2 จากทั้งหมด 12 คน",
        "อันดับ ๑ ได้ ๒.๕ คะแนน",  # Thai digits
        "ค่าปรับของแผนคือ 1,250",  # thousands separator
        "ค่าปรับ 1250.0 และ 2.50 คะแนน",  # trailing zeros
        "รวม 0.33 คะแนน",  # a payload decimal rounded to what it shows
        "อันดับ 1-2 อยู่ในกลุ่มแรก",  # a dash is not a minus
        "ชั่วโมงสัปดาห์นี้ 37.5",
        "ไม่มีตัวเลข",
        "[fake] อันดับ 1 อยู่ในกลุ่มแรก",
    ],
)
def test_numbers_from_the_payload_pass(text: str) -> None:
    assert unverified_numbers(text, PAYLOAD) == []


@pytest.mark.parametrize(
    "text,bad",
    [
        ("อันดับ 3 เหมาะที่สุด", ["3"]),  # a rank that is not in the payload
        ("อันดับ ๓", ["๓"]),
        ("รวม 3.5 คะแนน", ["3.5"]),  # 1 + 2.5, a computed sum
        ("ประมาณ 3 คะแนน", ["3"]),  # a whole number never stands for a rounded 2.5
        ("รวม 0.34", ["0.34"]),
        ("ค่าปรับ 1,251", ["1,251"]),
        ("อันดับ 1 และ 99", ["99"]),
    ],
)
def test_numbers_not_in_the_payload_are_reported(text: str, bad: list[str]) -> None:
    assert unverified_numbers(text, PAYLOAD) == bad


def test_booleans_are_not_numbers() -> None:
    assert payload_numbers({"first_wave": True, "partial": False}) == set()
    assert unverified_numbers("1", {"first_wave": True}) == ["1"]
