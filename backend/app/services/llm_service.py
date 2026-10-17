"""Provider selection and output checks. Provider is chosen strictly by settings; there is
no fallback. Only app.services.llm_gateway may call generate_explanation (round 6 PR B1):
the gateway counts the quota and writes the call log around it.
"""

import unicodedata
from dataclasses import replace
from decimal import Decimal

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.domain.llm_numbers import unverified_numbers
from app.integrations.llm import LlmAttempt, LlmRequest, bedrock, fake

__all__ = [
    "MAX_EXPLANATION_CHARS",
    "UNVERIFIED_NUMBER",
    "LlmAttempt",
    "LlmRequest",
    "estimate_cost",
    "generate_explanation",
    "is_retryable",
]

MAX_EXPLANATION_CHARS = 2000
# LLM_CALL_LOG.error_type of an INVALID_OUTPUT that quoted a number not in the payload
UNVERIFIED_NUMBER = "UNVERIFIED_NUMBER"
# Bidirectional controls can make the page show text that differs from what is stored
_BIDI_CONTROLS = frozenset(
    chr(code) for code in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
_RETRYABLE = frozenset(
    {LlmCallStatus.TIMEOUT, LlmCallStatus.THROTTLED, LlmCallStatus.SERVICE_ERROR}
)


def is_retryable(status: LlmCallStatus) -> bool:
    return status in _RETRYABLE


def estimate_cost(attempt: LlmAttempt) -> Decimal | None:
    if (
        attempt.input_tokens is None
        or attempt.output_tokens is None
        or attempt.input_rate is None
        or attempt.output_rate is None
    ):
        return None
    return (
        Decimal(attempt.input_tokens) / Decimal(1_000_000) * attempt.input_rate
        + Decimal(attempt.output_tokens) / Decimal(1_000_000) * attempt.output_rate
    )


def _valid_text(text: str) -> bool:
    if not text or len(text) > MAX_EXPLANATION_CHARS:
        return False
    return not any(
        (unicodedata.category(c) == "Cc" and c != "\n") or c in _BIDI_CONTROLS for c in text
    )


def generate_explanation(request: LlmRequest) -> LlmAttempt:
    """One attempt. The caller owns retries."""
    if settings.llm_provider == "bedrock":
        attempt = bedrock.generate(request)
    else:
        attempt = fake.generate(request)
    if attempt.status != LlmCallStatus.SUCCEEDED:
        return replace(attempt, text=None)
    text = (attempt.text or "").strip()
    if not _valid_text(text):
        return replace(attempt, status=LlmCallStatus.INVALID_OUTPUT, text=None)
    if unverified_numbers(text, request.payload):
        # Round 6 (6.28): a number the payload does not hold is never shown
        return replace(
            attempt, status=LlmCallStatus.INVALID_OUTPUT, text=None, error_type=UNVERIFIED_NUMBER
        )
    return replace(attempt, text=text)
