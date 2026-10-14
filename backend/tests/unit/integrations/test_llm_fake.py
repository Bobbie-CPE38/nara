"""Fake LLM adapter: offline, deterministic, no credentials."""

from decimal import Decimal

from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmRequest, fake

PAYLOAD = {
    "candidate_count": 2,
    "candidates": [
        {
            "rank": 1,
            "first_wave": True,
            "total": "5",
            "terms": [
                {"name": "OVERTIME", "value": "1", "weight": "1", "points": "1"},
                {"name": "CONSECUTIVE", "value": "2", "weight": "2", "points": "4"},
            ],
        },
        {"rank": 2, "first_wave": False, "total": "9", "terms": []},
    ],
}


def _request(payload=PAYLOAD, prompt="prompt text"):
    return LlmRequest(
        system="system",
        prompt=prompt,
        payload=payload,
        max_output_tokens=100,
        timeout_seconds=5,
    )


def test_deterministic_and_prefixed():
    first = fake.generate(_request())
    second = fake.generate(_request())
    assert first == second
    assert first.status == LlmCallStatus.SUCCEEDED
    assert first.text is not None and first.text.startswith("[fake] ")
    assert "อันดับ 1" in first.text
    assert "CONSECUTIVE" in first.text and "4" in first.text


def test_text_carries_no_names_from_payload():
    attempt = fake.generate(_request())
    assert attempt.text is not None
    # The payload has no names, so the sentence cannot contain any.
    assert "staff" not in attempt.text.lower()


def test_tokens_rates_and_provider():
    prompt = "x" * 40
    attempt = fake.generate(_request(prompt=prompt))
    assert attempt.text is not None
    assert attempt.input_tokens == 11
    assert attempt.output_tokens == len(attempt.text) // 4 + 1
    assert attempt.total_tokens == attempt.input_tokens + attempt.output_tokens
    assert attempt.duration_ms == 0
    assert attempt.input_rate == Decimal(0) and attempt.output_rate == Decimal(0)
    assert attempt.provider == "fake"
    assert attempt.error_type is None


def test_empty_payload_still_succeeds():
    attempt = fake.generate(_request(payload={}))
    assert attempt.status == LlmCallStatus.SUCCEEDED
    assert attempt.text is not None and attempt.text.startswith("[fake] ")
