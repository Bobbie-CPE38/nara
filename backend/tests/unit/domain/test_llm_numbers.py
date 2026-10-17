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
        "อันดับ 1, 2 และ 12",  # a list with spaces
        "อันดับสูงสุดคือ 1.",  # the full stop ends the sentence
        "รวม 0.33.",
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
        # Review of PR #108: read whole, never in pieces
        ("คะแนน .5", [".5"]),  # not the 5 of a rank
        ("คะแนน 1e3", ["1e3"]),  # not 1 and 3
        ("คะแนน 2.5e0", ["2.5e0"]),
        ("ประมาณ 1k ชั่วโมง", ["1k"]),
        ("ครึ่งหนึ่งคือ 1/2", ["1/2"]),
        ("อันดับ 1,2", ["1,2"]),  # a list without a space, or a decimal comma
        ("รุ่น 1.2.5", ["1.2.5"]),
        ("ได้ 2½ คะแนน", ["½"]),
        ("ค่า 2²", ["²"]),
    ],
)
def test_numbers_not_in_the_payload_are_reported(text: str, bad: list[str]) -> None:
    assert unverified_numbers(text, PAYLOAD) == bad


def test_booleans_are_not_numbers() -> None:
    assert payload_numbers({"first_wave": True, "partial": False}) == set()
    assert unverified_numbers("1", {"first_wave": True}) == ["1"]


def test_the_review_cases_fail_with_the_payloads_that_held_their_pieces() -> None:
    assert unverified_numbers("คะแนน .5", {"rank": 5}) == [".5"]
    assert unverified_numbers("คะแนน 1e3", {"rank": 1, "gap": 3}) == ["1e3"]
