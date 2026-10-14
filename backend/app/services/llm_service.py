"""Single LLM gateway. Provider is chosen strictly by settings; there is no fallback."""

from dataclasses import replace
from decimal import Decimal

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest, bedrock, fake

__all__ = [
    "MAX_EXPLANATION_CHARS",
    "LlmAttempt",
    "LlmRequest",
    "estimate_cost",
    "generate_explanation",
    "is_retryable",
]

MAX_EXPLANATION_CHARS = 2000
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
    return not any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in text)


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
    return replace(attempt, text=text)
