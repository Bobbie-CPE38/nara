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


SUMMARY_PAYLOAD = {
    "window": {"start": "2026-10-22T23:00:00+07:00", "end": "2026-10-23T07:00:00+07:00"},
    "assessed_gap": 2,
}


def test_a_timestamp_copied_whole_from_the_payload_passes() -> None:
    """PR B3 live check: the model copied the window and the T glued '22T23' into a token."""
    text = "ช่วงเวลาจาก 2026-10-22T23:00:00+07:00 ถึง 2026-10-23T07:00:00+07:00 ขาด 2 คน"
    assert unverified_numbers(text, SUMMARY_PAYLOAD) == []


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        # another time zone: the digits changed even though the date is the same
        ("เริ่ม 2026-10-22T16:00:00+00:00", ["22T16", "00", "00"]),
        # a timestamp the payload does not hold
        ("เริ่ม 2026-10-22T23:30:00+07:00", ["22T23", "30"]),
    ],
)
def test_a_timestamp_that_is_not_in_the_payload_still_fails(text: str, bad: list[str]) -> None:
    assert unverified_numbers(text, SUMMARY_PAYLOAD)
    assert set(unverified_numbers(text, SUMMARY_PAYLOAD)) & set(bad)


TIMESTAMP = "2026-10-22T23:00:00+07:00"
ATTACHED_PAYLOAD = {"window": {"start": TIMESTAMP}, "rank": 1, "gap": 2}


@pytest.mark.parametrize(
    "text",
    [
        f"1{TIMESTAMP}",  # a digit glued before: 12026-10-22T...
        f"{TIMESTAMP}2",  # a digit glued after: ...+07:002
        f".{TIMESTAMP}",  # a point glued before
        f"{TIMESTAMP}.5",  # a decimal continuing the offset
        f"{TIMESTAMP}/2",
        f"{TIMESTAMP}x",
        f"{TIMESTAMP}-05:00",  # another offset attached
    ],
)
def test_a_timestamp_with_something_attached_is_not_exempt(text: str) -> None:
    """Review of PR B3 follow-up: the trusted part must not leave a stray 1 or 2 behind."""
    assert unverified_numbers(text, ATTACHED_PAYLOAD)


@pytest.mark.parametrize(
    "text",
    [
        TIMESTAMP,
        f"เริ่ม {TIMESTAMP} ถึง",
        f"({TIMESTAMP})",
        f"เริ่ม {TIMESTAMP}, ขาด 2 คน",
        f"เริ่ม {TIMESTAMP}. อันดับ 1",
        f"เริ่ม:{TIMESTAMP};",
        f"เริ่ม{TIMESTAMP}ถึง",  # Thai letters around it are ordinary prose
        f'"{TIMESTAMP}"',
    ],
)
def test_a_timestamp_in_ordinary_prose_and_punctuation_passes(text: str) -> None:
    assert unverified_numbers(text, ATTACHED_PAYLOAD) == []


def test_booleans_are_not_numbers() -> None:
    assert payload_numbers({"first_wave": True, "partial": False}) == set()
    assert unverified_numbers("1", {"first_wave": True}) == ["1"]


def test_the_review_cases_fail_with_the_payloads_that_held_their_pieces() -> None:
    assert unverified_numbers("คะแนน .5", {"rank": 5}) == [".5"]
    assert unverified_numbers("คะแนน 1e3", {"rank": 1, "gap": 3}) == ["1e3"]
