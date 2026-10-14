"""Bedrock adapter against botocore's Stubber. No network, dummy credentials only."""

from decimal import Decimal

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import (
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    NoRegionError,
    ReadTimeoutError,
)
from botocore.stub import Stubber

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmRequest, bedrock

SECRET_MESSAGE = "SECRET-SDK-MESSAGE-do-not-leak"
PROMPT = "PROMPT-TEXT-do-not-leak"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(settings, "llm_model_id", "test-model")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "llm_max_output_tokens", 321)
    monkeypatch.setattr(settings, "llm_input_price_per_mtok_usd", Decimal("3"))
    monkeypatch.setattr(settings, "llm_output_price_per_mtok_usd", Decimal("15"))


def _request():
    return LlmRequest(
        system="system text",
        prompt=PROMPT,
        payload={},
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=7.5,
    )


def _real_client():
    return boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"}),
    )


def _response(text="สรุป", stop="end_turn", usage=True):
    body = {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": stop,
        "metrics": {"latencyMs": 5},
    }
    if usage:
        body["usage"] = {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18}
    return body


def test_request_shape_and_usage_mapping(monkeypatch):
    client = _real_client()
    expected = {
        "modelId": "test-model",
        "system": [{"text": "system text"}],
        "messages": [{"role": "user", "content": [{"text": PROMPT}]}],
        "inferenceConfig": {"maxTokens": 321, "temperature": 0},
    }
    with Stubber(client) as stubber:
        stubber.add_response("converse", _response(), expected)
        monkeypatch.setattr(bedrock, "_client", lambda timeout: client)
        attempt = bedrock.generate(_request())
        stubber.assert_no_pending_responses()
    assert attempt.status == LlmCallStatus.SUCCEEDED
    assert attempt.text == "สรุป"
    assert (attempt.input_tokens, attempt.output_tokens, attempt.total_tokens) == (11, 7, 18)
    assert attempt.provider == "bedrock"
    assert attempt.model_id == "test-model" and attempt.region == "us-east-1"
    assert attempt.input_rate == Decimal("3") and attempt.output_rate == Decimal("15")
    assert attempt.duration_ms is not None and attempt.duration_ms >= 0


def test_missing_usage_is_unknown_not_zero(monkeypatch):
    class _NoUsage:
        def converse(self, **_kwargs):
            return _response(usage=False)

    monkeypatch.setattr(bedrock, "_client", lambda timeout: _NoUsage())
    attempt = bedrock.generate(_request())
    assert attempt.status == LlmCallStatus.SUCCEEDED
    assert attempt.input_tokens is None and attempt.output_tokens is None
    assert attempt.total_tokens is None


def test_max_tokens_is_truncated(monkeypatch):
    client = _real_client()
    with Stubber(client) as stubber:
        stubber.add_response("converse", _response(stop="max_tokens"))
        monkeypatch.setattr(bedrock, "_client", lambda timeout: client)
        attempt = bedrock.generate(_request())
    assert attempt.status == LlmCallStatus.TRUNCATED
    assert attempt.text is None
    assert attempt.total_tokens == 18


def test_client_config_timeouts_and_no_sdk_retries(monkeypatch):
    client = bedrock._client(7.5)
    config = client.meta.config
    assert config.read_timeout == 7.5
    assert config.connect_timeout == 7.5
    assert config.retries["total_max_attempts"] == 1
    assert client.meta.region_name == "us-east-1"


@pytest.mark.parametrize(
    "code,expected",
    [
        ("ThrottlingException", LlmCallStatus.THROTTLED),
        ("ServiceUnavailableException", LlmCallStatus.SERVICE_ERROR),
        ("InternalServerException", LlmCallStatus.SERVICE_ERROR),
        ("ModelNotReadyException", LlmCallStatus.SERVICE_ERROR),
        ("ModelTimeoutException", LlmCallStatus.SERVICE_ERROR),
        ("AccessDeniedException", LlmCallStatus.CONFIG_ERROR),
        ("ValidationException", LlmCallStatus.CONFIG_ERROR),
        ("ResourceNotFoundException", LlmCallStatus.CONFIG_ERROR),
        ("UnrecognizedClientException", LlmCallStatus.CONFIG_ERROR),
        ("SomethingNew", LlmCallStatus.SERVICE_ERROR),
    ],
)
def test_client_error_codes_map(monkeypatch, code, expected):
    client = _real_client()
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "converse", service_error_code=code, service_message=SECRET_MESSAGE
        )
        monkeypatch.setattr(bedrock, "_client", lambda timeout: client)
        attempt = bedrock.generate(_request())
    assert attempt.status == expected
    assert attempt.error_type == code
    assert attempt.text is None
    assert attempt.input_tokens is None and attempt.output_tokens is None
    assert SECRET_MESSAGE not in repr(attempt)
    assert PROMPT not in repr(attempt)


class _Raising:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def converse(self, **_kwargs):
        raise self.error


@pytest.mark.parametrize(
    "error,expected",
    [
        (ReadTimeoutError(endpoint_url=SECRET_MESSAGE), LlmCallStatus.TIMEOUT),
        (ConnectTimeoutError(endpoint_url=SECRET_MESSAGE), LlmCallStatus.TIMEOUT),
        (EndpointConnectionError(endpoint_url=SECRET_MESSAGE), LlmCallStatus.TIMEOUT),
        (NoCredentialsError(), LlmCallStatus.CONFIG_ERROR),
        (NoRegionError(), LlmCallStatus.CONFIG_ERROR),
        (RuntimeError(SECRET_MESSAGE), LlmCallStatus.SERVICE_ERROR),
    ],
)
def test_exceptions_map_and_never_leak_message(monkeypatch, error, expected):
    monkeypatch.setattr(bedrock, "_client", lambda timeout: _Raising(error))
    attempt = bedrock.generate(_request())
    assert attempt.status == expected
    assert attempt.error_type == type(error).__name__
    assert SECRET_MESSAGE not in repr(attempt)


@pytest.mark.parametrize("field", ["llm_model_id", "aws_region"])
def test_missing_config_makes_no_client(monkeypatch, field):
    monkeypatch.setattr(settings, field, None)

    def boom(timeout):
        raise AssertionError("client must not be created")

    monkeypatch.setattr(bedrock, "_client", boom)
    attempt = bedrock.generate(_request())
    assert attempt.status == LlmCallStatus.CONFIG_ERROR
