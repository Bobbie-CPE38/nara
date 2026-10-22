"""Bedrock proxy Lambda for the Backend's LLM_PROVIDER=lambda (round 6 PR B3).

The EC2 instance of the test machine has no IAM role (the team account cannot create an
instance profile), so the Backend reaches Bedrock through this function behind API Gateway.
API Gateway checks the API key of the usage plan before this runs; the function's own role
allows bedrock:InvokeModel on the chosen model only (docs/deploy-aws.md).

One Converse call per request, no retries: the Backend's gateway owns retries, the daily
quota and the call log. This function enforces its own limits so that a leaked key cannot
send a bigger request than the app would: a fixed model (the caller cannot choose one), a
maximum request size and a maximum answer length.

Request body  {"system": str, "prompt": str, "max_output_tokens": int}
200           {"ok": true, "model_id", "region", "stopReason", "output", "usage"}
              {"ok": false, "error_code": <Bedrock code or exception class>, "model_id", "region"}
400 / 413     a body that is not that shape / bigger than MAX_INPUT_BYTES

Never logs the prompt, the answer or an exception message: one JSON line per request with
the request ID, the outcome, the token counts and the time taken.

Environment: MODEL_ID (required), MAX_INPUT_BYTES (32000), MAX_OUTPUT_TOKENS (1024),
BEDROCK_TIMEOUT_SECONDS (10, under the function timeout and the Backend's 15 seconds).
AWS_REGION is set by Lambda itself.
"""

import base64
import json
import os
import time
from typing import Any

# The app accepts 5000 estimated tokens = 15000 bytes of system + prompt (3 bytes a token);
# JSON quoting and escaping can double that, plus the keys: 2 * 15000 + overhead
DEFAULT_MAX_INPUT_BYTES = 32000
DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_BEDROCK_TIMEOUT_SECONDS = 10.0

_client: Any = None


def _bedrock() -> Any:
    """One client per container, made on first use. Imported here so tests need no boto3."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        timeout = float(
            os.environ.get("BEDROCK_TIMEOUT_SECONDS", DEFAULT_BEDROCK_TIMEOUT_SECONDS)
        )
        _client = boto3.client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=timeout,
                read_timeout=timeout,
                retries={"total_max_attempts": 1, "mode": "standard"},
            ),
        )
    return _client


def _answer(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def _error_code(error: Exception) -> str:
    """The Bedrock error code of a ClientError, else the exception's class name."""
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return type(error).__name__


def _read(
    event: dict[str, Any], max_input_bytes: int
) -> tuple[int, dict[str, Any] | None]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if len(raw.encode("utf-8")) > max_input_bytes:
        return 413, None
    try:
        body = json.loads(raw)
    except ValueError:
        return 400, None
    if (
        not isinstance(body, dict)
        or set(body) != {"system", "prompt", "max_output_tokens"}
        or not isinstance(body["system"], str)
        or not isinstance(body["prompt"], str)
        or not isinstance(body["max_output_tokens"], int)
        or isinstance(body["max_output_tokens"], bool)
        or body["max_output_tokens"] < 1
    ):
        return 400, None
    return 200, body


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.monotonic()
    model_id = os.environ["MODEL_ID"]
    region = os.environ.get("AWS_REGION", "")
    max_input = int(os.environ.get("MAX_INPUT_BYTES", DEFAULT_MAX_INPUT_BYTES))
    max_output = int(os.environ.get("MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS))
    request_id = getattr(context, "aws_request_id", None)

    def log(outcome: str, usage: dict[str, Any] | None = None) -> None:
        usage = usage or {}
        print(
            json.dumps(
                {
                    "request_id": request_id,
                    "outcome": outcome,
                    "input_tokens": usage.get("inputTokens"),
                    "output_tokens": usage.get("outputTokens"),
                    "ms": int((time.monotonic() - started) * 1000),
                }
            )
        )

    status, body = _read(event, max_input)
    if body is None:
        log("REJECTED")
        return _answer(status, {"ok": False, "error": "BAD_REQUEST"})
    try:
        response = _bedrock().converse(
            modelId=model_id,
            system=[{"text": body["system"]}],
            messages=[{"role": "user", "content": [{"text": body["prompt"]}]}],
            inferenceConfig={
                "maxTokens": min(body["max_output_tokens"], max_output),
                "temperature": 0,
            },
        )
    except Exception as error:  # noqa: BLE001 - only the code or class name leaves here
        code = _error_code(error)
        log(code)
        return _answer(
            200,
            {"ok": False, "error_code": code, "model_id": model_id, "region": region},
        )

    message = response.get("output", {}).get("message", {})
    # Only the text parts: reasoning or other blocks never leave the function
    content = [part for part in message.get("content", []) if "text" in part]
    usage = response.get("usage")
    log("OK", usage)
    return _answer(
        200,
        {
            "ok": True,
            "model_id": model_id,
            "region": region,
            "stopReason": response.get("stopReason"),
            "output": {
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": content,
                }
            },
            "usage": usage,
        },
    )
