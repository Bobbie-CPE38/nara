"""LLM adapters. Shared request/result types live here so adapters never import services."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.enums import LlmCallStatus


@dataclass(frozen=True)
class LlmRequest:
    system: str
    prompt: str
    # Only the fake adapter reads this, to build a deterministic sentence.
    payload: Mapping[str, Any]
    max_output_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class LlmAttempt:
    """Result of one attempt. None tokens mean unknown, never zero."""

    status: LlmCallStatus
    text: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    duration_ms: int | None
    error_type: str | None
    provider: str
    model_id: str | None
    region: str | None
    input_rate: Decimal | None
    output_rate: Decimal | None
