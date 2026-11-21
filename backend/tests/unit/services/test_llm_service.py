"""llm_service gateway: provider selection, output validation, retry and cost helpers."""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest, bedrock, fake
from app.services import llm_service


def _request():
    return LlmRequest(system="s", prompt="p", payload={}, max_output_tokens=10, timeout_seconds=1)


def _attempt(status=LlmCallStatus.SUCCEEDED, text="ok", **overrides):
    base = LlmAttempt(
        status=status,
        text=text,
        input_tokens=1_000_000,
        output_tokens=500_000,
        total_tokens=1_500_000,
        duration_ms=1,
        error_type=None,
        provider="bedrock",
        model_id="m",
        region="r",
        input_rate=Decimal("3"),
        output_rate=Decimal("15"),
    )
    return replace(base, **overrides)


def test_fake_selected_by_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    attempt = llm_service.generate_explanation(_request())
    assert attempt.provider == "fake"
    assert attempt.status == LlmCallStatus.SUCCEEDED


def test_bedrock_failure_never_falls_back_to_fake(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(
        bedrock,
        "generate",
        lambda request: _attempt(LlmCallStatus.SERVICE_ERROR, text=None, error_type="X"),
    )
    calls = []
    monkeypatch.setattr(fake, "generate", lambda request: calls.append(request))
    attempt = llm_service.generate_explanation(_request())
    assert attempt.status == LlmCallStatus.SERVICE_ERROR
    assert attempt.provider == "bedrock"
    assert calls == []


def test_bedrock_chosen_only_by_setting(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    calls = []
    monkeypatch.setattr(bedrock, "generate", lambda request: calls.append(request))
    llm_service.generate_explanation(_request())
    assert calls == []


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n ",
        "x" * (llm_service.MAX_EXPLANATION_CHARS + 1),
        "bad\x00char",
        "tab\there",
        "a\x7fb",
        "c1\x85next",
        "csi\x9bx",
        "bidi‮override",
        "isolate⁦x",
        "mark‎x",
    ],
)
def test_invalid_output_rejected(monkeypatch, text):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text=text))
    attempt = llm_service.generate_explanation(_request())
    assert attempt.status == LlmCallStatus.INVALID_OUTPUT
    assert attempt.text is None


def test_valid_output_is_stripped_and_keeps_newlines(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text="  a\nb  "))
    attempt = llm_service.generate_explanation(_request())
    assert attempt.status == LlmCallStatus.SUCCEEDED
    assert attempt.text == "a\nb"


def test_max_length_boundary_ok(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    text = "x" * llm_service.MAX_EXPLANATION_CHARS
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text=text))
    assert llm_service.generate_explanation(_request()).status == LlmCallStatus.SUCCEEDED


@pytest.mark.parametrize(
    "status,expected",
    [
        (LlmCallStatus.TIMEOUT, True),
        (LlmCallStatus.THROTTLED, True),
        (LlmCallStatus.SERVICE_ERROR, True),
        (LlmCallStatus.SUCCEEDED, False),
        (LlmCallStatus.IN_FLIGHT, False),
        (LlmCallStatus.CONFIG_ERROR, False),
        (LlmCallStatus.TRUNCATED, False),
        (LlmCallStatus.INVALID_OUTPUT, False),
    ],
)
def test_is_retryable(status, expected):
    assert llm_service.is_retryable(status) is expected


def test_estimate_cost_known():
    assert llm_service.estimate_cost(_attempt()) == Decimal("10.5")


def test_estimate_cost_zero_rates():
    attempt = _attempt(input_rate=Decimal(0), output_rate=Decimal(0))
    assert llm_service.estimate_cost(attempt) == Decimal(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_tokens": None},
        {"output_tokens": None},
        {"input_rate": None},
        {"output_rate": None},
    ],
)
def test_estimate_cost_unknown_is_none(overrides):
    assert llm_service.estimate_cost(_attempt(**overrides)) is None


def test_a_number_not_in_the_payload_is_invalid_output(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text="อันดับ 2 ได้ 7 คะแนน"))
    request = replace(_request(), payload={"candidates": [{"rank": 2, "points": 5}]})

    attempt = llm_service.generate_explanation(request)

    assert attempt.status == LlmCallStatus.INVALID_OUTPUT
    assert attempt.text is None and attempt.error_type == llm_service.UNVERIFIED_NUMBER
    # Usage is still recorded: the call was made and billed
    assert attempt.input_tokens == 1_000_000


def test_numbers_from_the_payload_pass(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text="อันดับ ๒ ได้ 5 คะแนน"))
    request = replace(_request(), payload={"candidates": [{"rank": 2, "points": 5}]})

    assert llm_service.generate_explanation(request).status == LlmCallStatus.SUCCEEDED


@pytest.mark.parametrize(
    "text,payload",
    [("คะแนน .5", {"rank": 5}), ("คะแนน 1e3", {"rank": 1, "gap": 3})],
)
def test_a_number_read_in_pieces_is_invalid_output(monkeypatch, text, payload):
    """Review of PR #108: .5 and 1e3 must not pass on the 5, or the 1 and 3, of the payload."""
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text=text))

    attempt = llm_service.generate_explanation(replace(_request(), payload=payload))

    assert attempt.status == LlmCallStatus.INVALID_OUTPUT
    assert attempt.error_type == llm_service.UNVERIFIED_NUMBER and attempt.text is None


def test_a_rounded_decimal_still_passes(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(bedrock, "generate", lambda request: _attempt(text="รวม 0.33 คะแนน"))
    request = replace(_request(), payload={"total": 0.3333333333333333})

    assert llm_service.generate_explanation(request).status == LlmCallStatus.SUCCEEDED
