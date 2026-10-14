"""Bedrock Converse adapter. One attempt, SDK retries off.

Never log or return exception messages, prompt text or response text.
"""

import time
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    NoRegionError,
    ReadTimeoutError,
)

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

_CONFIG_CODES = {
    "AccessDeniedException",
    "ValidationException",
    "ResourceNotFoundException",
    "UnrecognizedClientException",
}


def _client(timeout_seconds: float) -> "BedrockRuntimeClient":
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries={"total_max_attempts": 1, "mode": "standard"},
        ),
    )


def _classify(error: Exception) -> tuple[LlmCallStatus, str]:
    """Map an exception to (status, error_type). Only the class name or code is kept."""
    if isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code", "ClientError"))
        if code == "ThrottlingException":
            return LlmCallStatus.THROTTLED, code
        if code in _CONFIG_CODES:
            return LlmCallStatus.CONFIG_ERROR, code
        # ServiceUnavailable, InternalServer, ModelNotReady, ModelTimeout and any
        # other code are all retryable service errors.
        return LlmCallStatus.SERVICE_ERROR, code
    name = type(error).__name__
    if isinstance(error, ReadTimeoutError | ConnectTimeoutError | EndpointConnectionError):
        return LlmCallStatus.TIMEOUT, name
    if isinstance(error, NoCredentialsError | NoRegionError):
        return LlmCallStatus.CONFIG_ERROR, name
    return LlmCallStatus.SERVICE_ERROR, name


def generate(request: LlmRequest) -> LlmAttempt:
    started = time.monotonic()

    def result(
        status: LlmCallStatus,
        *,
        text: str | None = None,
        usage: tuple[int | None, int | None, int | None] = (None, None, None),
        error_type: str | None = None,
    ) -> LlmAttempt:
        return LlmAttempt(
            status=status,
            text=text,
            input_tokens=usage[0],
            output_tokens=usage[1],
            total_tokens=usage[2],
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=error_type,
            provider="bedrock",
            model_id=settings.llm_model_id,
            region=settings.aws_region,
            input_rate=settings.llm_input_price_per_mtok_usd,
            output_rate=settings.llm_output_price_per_mtok_usd,
        )

    if not settings.llm_model_id or not settings.aws_region:
        return result(LlmCallStatus.CONFIG_ERROR, error_type="MissingConfig")
    try:
        response = _client(request.timeout_seconds).converse(
            modelId=settings.llm_model_id,
            system=[{"text": request.system}],
            messages=[{"role": "user", "content": [{"text": request.prompt}]}],
            inferenceConfig={"maxTokens": request.max_output_tokens, "temperature": 0},
        )
    except Exception as error:  # classified by type only; the message is never read
        status, error_type = _classify(error)
        return result(status, error_type=error_type)

    usage_raw = response.get("usage")
    usage: tuple[int | None, int | None, int | None] = (
        (
            usage_raw.get("inputTokens"),
            usage_raw.get("outputTokens"),
            usage_raw.get("totalTokens"),
        )
        if usage_raw
        else (None, None, None)
    )
    if response.get("stopReason") == "max_tokens":
        return result(LlmCallStatus.TRUNCATED, usage=usage)
    parts = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(str(part["text"]) for part in parts if "text" in part)
    return result(LlmCallStatus.SUCCEEDED, text=text, usage=usage)
