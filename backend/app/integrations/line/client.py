"""Small synchronous LINE adapter. Never log credentials, bodies or reply tokens."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings

API = "https://api.line.me/v2/bot/message/"
logger = logging.getLogger(__name__)


def _post(path: str, payload: dict[str, Any], retry_key: str | None = None) -> str:
    token = settings.line_channel_access_token
    if token is None:
        return "401"
    headers = {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "Content-Type": "application/json",
    }
    if retry_key is not None:
        headers["X-Line-Retry-Key"] = retry_key
    request = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            # Only known throttle messages are safe to log. Never log a raw
            # response body that might contain identifiers or reflected input.
            try:
                payload_error = json.loads(error.read(4096))
                message = payload_error.get("message") if isinstance(payload_error, dict) else None
            except (ValueError, OSError):
                message = None
            known = {"You have reached your monthly limit.", "Too many requests."}
            logger.warning("LINE throttling: %s", message if message in known else "HTTP 429")
        # A retry-key conflict is only accepted with LINE's confirmation header.
        if error.code == 409 and not (
            error.headers and error.headers.get("x-line-accepted-request-id")
        ):
            return "400"
        return str(error.code)
    except (OSError, urllib.error.URLError):
        return "TIMEOUT"


def push(payload: dict[str, Any], retry_key: str) -> str:
    return _post("push", payload, retry_key)


def reply(reply_token: str, message: str) -> str:
    return _post(
        "reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
    )
