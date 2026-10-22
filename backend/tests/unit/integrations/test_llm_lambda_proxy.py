"""The Lambda proxy adapter (round 6 PR B3): what it sends and how it reads every answer.

No network: `_post` is replaced, except in the guard test, which shows a real call to an
AWS host fails the test.
"""

import json
import logging
import sys
import threading
import urllib.error
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmRequest, lambda_proxy
from app.services import llm_gateway, llm_service

URL = "https://abc123.execute-api.ap-southeast-1.amazonaws.com/prod"
KEY = "API-KEY-do-not-leak"
PROMPT = "PROMPT-TEXT-do-not-leak"
SUCCESS = {
    "ok": True,
    "model_id": "global.amazon.nova-2-lite-v1:0",
    "region": "ap-southeast-1",
    "stopReason": "end_turn",
    "output": {"message": {"role": "assistant", "content": [{"text": "อันดับ 1"}]}},
    "usage": {"inputTokens": 1200, "outputTokens": 80, "totalTokens": 1280},
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "lambda")
    monkeypatch.setattr(settings, "llm_lambda_url", URL)
    monkeypatch.setattr(settings, "llm_lambda_api_key", SecretStr(KEY))
    monkeypatch.setattr(settings, "llm_model_id", None)
    monkeypatch.setattr(settings, "aws_region", None)
    monkeypatch.setattr(settings, "llm_input_price_per_mtok_usd", Decimal("0.41"))
    monkeypatch.setattr(settings, "llm_output_price_per_mtok_usd", Decimal("3.39"))


def _request() -> LlmRequest:
    return LlmRequest(
        system="system text",
        prompt=PROMPT,
        payload={"candidates": [{"rank": 1}]},
        max_output_tokens=321,
        timeout_seconds=7.5,
    )


class Recorder:
    def __init__(self, status: int = 200, body: object = SUCCESS) -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, dict, str, float]] = []

    def __call__(self, url: str, body: bytes, api_key: str, timeout: float) -> tuple[int, bytes]:
        self.calls.append((url, json.loads(body), api_key, timeout))
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return self.status, raw


def test_success_reads_the_converse_answer_and_the_proxys_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(lambda_proxy, "_post", recorder)

    attempt = lambda_proxy.generate(_request())

    assert attempt.status is LlmCallStatus.SUCCEEDED
    assert attempt.text == "อันดับ 1"
    assert (attempt.input_tokens, attempt.output_tokens, attempt.total_tokens) == (1200, 80, 1280)
    assert (attempt.provider, attempt.model_id, attempt.region) == (
        "lambda",
        "global.amazon.nova-2-lite-v1:0",
        "ap-southeast-1",
    )
    assert (attempt.input_rate, attempt.output_rate) == (Decimal("0.41"), Decimal("3.39"))
    url, body, key, timeout = recorder.calls[0]
    assert (url, key, timeout) == (URL, KEY, 7.5)
    # The payload is never sent: the proxy only needs the prompt the app already rendered
    assert body == {"system": "system text", "prompt": PROMPT, "max_output_tokens": 321}


def test_a_cut_off_answer_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lambda_proxy, "_post", Recorder(body={**SUCCESS, "stopReason": "max_tokens"})
    )
    attempt = lambda_proxy.generate(_request())
    assert (attempt.status, attempt.text) == (LlmCallStatus.TRUNCATED, None)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("ThrottlingException", LlmCallStatus.THROTTLED),
        ("AccessDeniedException", LlmCallStatus.CONFIG_ERROR),
        ("ValidationException", LlmCallStatus.CONFIG_ERROR),
        ("ReadTimeoutError", LlmCallStatus.TIMEOUT),
        ("ModelNotReadyException", LlmCallStatus.SERVICE_ERROR),
        ("TimeoutError", LlmCallStatus.SERVICE_ERROR),
    ],
)
def test_bedrock_errors_from_the_proxy_use_the_bedrock_rules(
    monkeypatch: pytest.MonkeyPatch, code: str, status: LlmCallStatus
) -> None:
    body = {"ok": False, "error_code": code, "model_id": "m", "region": "r"}
    monkeypatch.setattr(lambda_proxy, "_post", Recorder(body=body))

    attempt = lambda_proxy.generate(_request())

    assert (attempt.status, attempt.error_type) == (status, code)
    assert (attempt.model_id, attempt.region, attempt.text) == ("m", "r", None)


@pytest.mark.parametrize(
    ("http_status", "status", "error_type"),
    [
        (400, LlmCallStatus.CONFIG_ERROR, "ProxyRejected"),
        (403, LlmCallStatus.CONFIG_ERROR, "ProxyForbidden"),
        (413, LlmCallStatus.CONFIG_ERROR, "ProxyRejected"),
        (429, LlmCallStatus.THROTTLED, "ProxyThrottled"),
        (502, LlmCallStatus.SERVICE_ERROR, "ProxyError"),
        (504, LlmCallStatus.TIMEOUT, "ProxyTimeout"),
    ],
)
def test_gateway_answers_map_to_statuses(
    monkeypatch: pytest.MonkeyPatch, http_status: int, status: LlmCallStatus, error_type: str
) -> None:
    monkeypatch.setattr(lambda_proxy, "_post", Recorder(status=http_status, body=b""))
    attempt = lambda_proxy.generate(_request())
    assert (attempt.status, attempt.error_type) == (status, error_type)


@pytest.mark.parametrize(
    ("error", "status", "error_type"),
    [
        (TimeoutError(), LlmCallStatus.TIMEOUT, "ProxyTimeout"),
        (urllib.error.URLError("refused"), LlmCallStatus.SERVICE_ERROR, "ProxyUnreachable"),
        (ConnectionResetError(), LlmCallStatus.SERVICE_ERROR, "ProxyUnreachable"),
    ],
)
def test_network_failures_map_to_statuses(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: LlmCallStatus, error_type: str
) -> None:
    def failing(*_args: object) -> tuple[int, bytes]:
        raise error

    monkeypatch.setattr(lambda_proxy, "_post", failing)
    attempt = lambda_proxy.generate(_request())
    assert (attempt.status, attempt.error_type) == (status, error_type)


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]"])
def test_a_body_that_is_not_an_object_is_a_service_error(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(lambda_proxy, "_post", Recorder(body=body))
    attempt = lambda_proxy.generate(_request())
    assert (attempt.status, attempt.error_type) == (LlmCallStatus.SERVICE_ERROR, "ProxyBadResponse")


@pytest.mark.parametrize(("url", "key"), [(None, KEY), (URL, None), (URL, "")])
def test_missing_config_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, url: str | None, key: str | None
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(lambda_proxy, "_post", recorder)
    monkeypatch.setattr(settings, "llm_lambda_url", url)
    monkeypatch.setattr(settings, "llm_lambda_api_key", None if key is None else SecretStr(key))

    attempt = lambda_proxy.generate(_request())

    assert (attempt.status, attempt.error_type) == (LlmCallStatus.CONFIG_ERROR, "MissingConfig")
    assert recorder.calls == []


def test_the_service_checks_numbers_of_a_lambda_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The number check of llm_service applies to every provider (6.28)."""
    made_up = {**SUCCESS, "output": {"message": {"content": [{"text": "อันดับ 9"}]}}}
    monkeypatch.setattr(lambda_proxy, "_post", Recorder(body=made_up))

    attempt = llm_service.generate_explanation(_request())

    assert attempt.status is LlmCallStatus.INVALID_OUTPUT
    assert attempt.text is None


def test_nothing_secret_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(lambda_proxy, "_post", Recorder())
    with caplog.at_level(logging.DEBUG):
        lambda_proxy.generate(_request())
    assert PROMPT not in caplog.text and KEY not in caplog.text


def test_a_real_call_to_aws_fails_the_test() -> None:
    """The conftest guard: even with a URL set by mistake, no test reaches API Gateway."""
    with pytest.raises(pytest.fail.Exception, match="Unmocked AWS HTTP call"):
        lambda_proxy.generate(_request())


# --------------------------------------------------------------------------- settings
def test_the_proxy_url_must_be_https() -> None:
    with pytest.raises(ValidationError, match="https"):
        Settings(llm_lambda_url="http://proxy.example/prod")


def test_blank_proxy_settings_are_unset() -> None:
    fresh = Settings(llm_lambda_url="", llm_lambda_api_key="")
    assert (fresh.llm_lambda_url, fresh.llm_lambda_api_key) == (None, None)


@pytest.mark.parametrize(
    ("url", "key", "configured"),
    [(URL, KEY, True), (None, KEY, False), (URL, None, False)],
)
def test_lambda_is_configured_with_url_and_key(
    url: str | None, key: str | None, configured: bool
) -> None:
    fresh = Settings(llm_provider="lambda", llm_lambda_url=url, llm_lambda_api_key=key)
    assert fresh.llm_configured is configured
    # The key never shows in the settings' text
    assert KEY not in repr(fresh)


# --------------------------------------------------------------------------- redirects, Thai
def _server(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize(
    "location_host", ["127.0.0.1", "localhost"], ids=["same-host", "other-host"]
)
def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(location_host: str) -> None:
    seen: list[dict[str, str]] = []

    class Target(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()

        do_GET = do_POST

        def log_message(self, *args: object) -> None:
            pass

    target = _server(Target)

    class Origin(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(307)  # 307 keeps the method and the body
            self.send_header("Location", f"http://{location_host}:{target.server_port}/x")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    origin = _server(Origin)
    try:
        code, body = lambda_proxy._post(
            f"http://127.0.0.1:{origin.server_port}/prod", b"{}", KEY, 5.0
        )
    finally:
        origin.shutdown()
        target.shutdown()

    assert code == 307
    assert body == b""
    assert seen == []


def test_a_redirect_is_a_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_proxy, "_post", Recorder(status=302, body=b""))

    attempt = lambda_proxy.generate(_request())

    assert attempt.status is LlmCallStatus.SERVICE_ERROR
    assert attempt.error_type == "ProxyError"


def test_thai_goes_over_the_wire_as_utf8_within_the_proxys_default_limit() -> None:
    """The largest input the app accepts (5000 Thai characters = 5000 estimated tokens)
    must fit MAX_INPUT_BYTES of the Lambda, which reads the body as the proxy does."""
    sys_path = str(Path(__file__).resolve().parents[4] / "deploy" / "aws" / "lambda")
    monkeypatch_path = sys.path[:]
    sys.path.insert(0, sys_path)
    try:
        import bedrock_proxy  # type: ignore[import-not-found]
    finally:
        sys.path[:] = monkeypatch_path

    sent: list[bytes] = []

    def capture(url: str, body: bytes, api_key: str, timeout: float) -> tuple[int, bytes]:
        sent.append(body)
        return 200, json.dumps(SUCCESS).encode()

    request = LlmRequest(
        system="",
        prompt="ก" * settings.llm_max_input_tokens,
        payload={},
        max_output_tokens=321,
        timeout_seconds=7.5,
    )
    assert llm_gateway.estimate_input_tokens(request) <= settings.llm_max_input_tokens
    original = lambda_proxy._post
    lambda_proxy._post = capture
    try:
        lambda_proxy.generate(request)
    finally:
        lambda_proxy._post = original

    body = sent[0]
    assert b"\u0e01" not in body
    assert len(body) < 20000 * 1  # the old default would have rejected 30054 bytes
    status, parsed = bedrock_proxy._read(
        {"body": body.decode("utf-8")}, bedrock_proxy.DEFAULT_MAX_INPUT_BYTES
    )
    assert status == 200
    assert parsed is not None and parsed["prompt"] == request.prompt
