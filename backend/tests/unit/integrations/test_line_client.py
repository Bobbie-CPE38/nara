"""Actual adapter serialization/status handling, with no network calls."""

import io
import json
from email.message import Message
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.integrations.line import client


def test_push_uses_fixed_body_token_and_retry_key(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-only-token"))
    response = MagicMock()
    response.__enter__.return_value.status = 200
    transport = MagicMock(return_value=response)
    monkeypatch.setattr(client.urllib.request, "urlopen", transport)
    payload = {"to": "U_TEST", "messages": [{"type": "text", "text": "ทดสอบ"}]}
    assert client.push(payload, "retry-test") == "200"
    request = transport.call_args.args[0]
    assert request.full_url == "https://api.line.me/v2/bot/message/push"
    assert json.loads(request.data) == payload
    assert request.get_header("Authorization") == "Bearer test-only-token"
    assert request.get_header("X-line-retry-key") == "retry-test"
    assert transport.call_args.kwargs["timeout"] == 5


@pytest.mark.parametrize(
    "code,confirmed,expected",
    [
        (409, True, "409"),
        (409, False, "400"),
        (401, False, "401"),
        (429, False, "429"),
        (500, False, "500"),
    ],
)
def test_http_errors_are_classified_without_logging_secrets(
    monkeypatch, caplog, code, confirmed, expected
):
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("private-test-token"))
    headers = Message()
    if confirmed:
        headers["x-line-accepted-request-id"] = "accepted"
    error = HTTPError(
        "https://api.line.me",
        code,
        "error",
        headers,
        io.BytesIO(b'{"message":"private-test-token"}'),
    )
    monkeypatch.setattr(client.urllib.request, "urlopen", MagicMock(side_effect=error))
    assert client.push({"to": "U_TEST"}, "retry-test") == expected
    assert "private-test-token" not in caplog.text


def test_network_failure_is_retryable_and_missing_token_never_calls_network(monkeypatch):
    transport = MagicMock(side_effect=URLError("test network failure"))
    monkeypatch.setattr(client.urllib.request, "urlopen", transport)
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-only-token"))
    assert client.push({}, "retry-test") == "TIMEOUT"
    monkeypatch.setattr(settings, "line_channel_access_token", None)
    assert client.push({}, "retry-test") == "401"
    assert transport.call_count == 1
