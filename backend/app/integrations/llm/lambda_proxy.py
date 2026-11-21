"""Bedrock through a Lambda behind API Gateway (round 6 PR B3). One attempt, no retries.

The team account cannot give the EC2 instance an IAM role, so the Backend reaches Bedrock
through `deploy/aws/lambda/bedrock_proxy.py`: POST LLM_LAMBDA_URL with the API key of the
usage plan in `x-api-key`. The proxy makes one Converse call with its own model and limits
and answers in the shape below, which this adapter reads with the Bedrock adapter's rules
(`bedrock.parse_converse`, `bedrock.status_of_code`):

  request   {"system": str, "prompt": str, "max_output_tokens": int}
  200       {"ok": true, "model_id", "region", "stopReason", "output", "usage"}
            {"ok": false, "error_code": "<Bedrock code or botocore class>", "model_id", "region"}
  403       wrong or missing API key (API Gateway)
  429       usage-plan quota or throttling (API Gateway, best effort only)
  3xx       never followed (the key must not leave the configured URL): SERVICE_ERROR
  400/413   the proxy refused the request (its limits); 5xx/504 a proxy or gateway fault

The quota of the app (llm_gateway) is still the control: the usage plan is an extra limit
AWS applies on a best-effort basis. Never log the prompt, the answer, the key or a body.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.domain.enums import LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest
from app.integrations.llm.bedrock import Usage, parse_converse, status_of_code

PROVIDER = "lambda"
API_KEY_HEADER = "x-api-key"
# An HTTP answer of the gateway or proxy, as (status, error_type)
_HTTP_STATUSES: dict[int, tuple[LlmCallStatus, str]] = {
    400: (LlmCallStatus.CONFIG_ERROR, "ProxyRejected"),
    403: (LlmCallStatus.CONFIG_ERROR, "ProxyForbidden"),
    413: (LlmCallStatus.CONFIG_ERROR, "ProxyRejected"),
    429: (LlmCallStatus.THROTTLED, "ProxyThrottled"),
    504: (LlmCallStatus.TIMEOUT, "ProxyTimeout"),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib would resend `x-api-key` to wherever it points."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url: str, body: bytes, api_key: str, timeout_seconds: float) -> tuple[int, bytes]:
    """(HTTP status, body). An HTTP error answer, a redirect included, is returned, not raised."""
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", API_KEY_HEADER: api_key},
    )
    try:
        with _OPENER.open(request, timeout=timeout_seconds) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, b""


def generate(request: LlmRequest) -> LlmAttempt:
    started = time.monotonic()
    model_id, region = settings.llm_model_id, settings.aws_region

    def result(
        status: LlmCallStatus,
        *,
        text: str | None = None,
        usage: Usage = (None, None, None),
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
            provider=PROVIDER,
            model_id=model_id,
            region=region,
            input_rate=settings.llm_input_price_per_mtok_usd,
            output_rate=settings.llm_output_price_per_mtok_usd,
        )

    url, key = settings.llm_lambda_url, settings.llm_lambda_api_key
    if not url or key is None or not key.get_secret_value():
        return result(LlmCallStatus.CONFIG_ERROR, error_type="MissingConfig")
    body = json.dumps(
        {
            "system": request.system,
            "prompt": request.prompt,
            "max_output_tokens": request.max_output_tokens,
        },
        # Thai as UTF-8 (3 bytes), not \uXXXX (6 bytes): the proxy's size limit is in bytes
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        code, raw = _post(url, body, key.get_secret_value(), request.timeout_seconds)
    except TimeoutError:
        return result(LlmCallStatus.TIMEOUT, error_type="ProxyTimeout")
    except (urllib.error.URLError, OSError):
        return result(LlmCallStatus.SERVICE_ERROR, error_type="ProxyUnreachable")

    if code != 200:
        status, error_type = _HTTP_STATUSES.get(code, (LlmCallStatus.SERVICE_ERROR, "ProxyError"))
        return result(status, error_type=error_type)
    try:
        answer: Any = json.loads(raw)
        if not isinstance(answer, dict):
            raise ValueError("not an object")
    except ValueError:
        return result(LlmCallStatus.SERVICE_ERROR, error_type="ProxyBadResponse")
    # The proxy's own model and Region are what was called and what the log must show
    model_id = answer.get("model_id") or model_id
    region = answer.get("region") or region
    if answer.get("ok") is not True:
        error_code = str(answer.get("error_code") or "ProxyError")[:100]
        return result(status_of_code(error_code), error_type=error_code)
    status, text, usage = parse_converse(answer)
    return result(status, text=text, usage=usage)
