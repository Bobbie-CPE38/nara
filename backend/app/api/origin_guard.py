"""Origin check and no-store for browser session/admin APIs (docs/workflow.md 6.33.3).

A browser attaches the session cookie and Basic Auth to any request, even one another
site makes it send. So a state-changing request (POST, PUT, PATCH, DELETE) must carry
an Origin that is exactly one of CORS_ORIGINS, or it gets 403 AUTH_ORIGIN_FORBIDDEN
before any route runs: always under /auth and /admin, and on every path when AUTH_MODE=session.
A missing Origin or "null" is refused too, including non-browser admin clients.
CORS only stops the page from reading the answer, after the write.

Not checked, because no cookie is how they prove who they are: exactly
POST /line/webhook (the LINE signature; the raw path, so /line/webhook/ or an encoded
form is not exempt) and /internal/* (the job secret).

Pure ASGI rather than BaseHTTPMiddleware, so the routes' BackgroundTasks still run
after the response as before.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

AUTH_ORIGIN_FORBIDDEN = "AUTH_ORIGIN_FORBIDDEN"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WEBHOOK_PATH = b"/line/webhook"


def _is_sensitive_path(path: str) -> bool:
    return (
        path == "/auth"
        or path.startswith("/auth/")
        or path == "/admin"
        or path.startswith("/admin/")
    )


def _exempt(method: str, path: str, raw_path: bytes) -> bool:
    if method == "POST" and raw_path == WEBHOOK_PATH:
        return True
    return path == "/internal" or path.startswith("/internal/")


def _origin(scope: Scope) -> str | None:
    values = [value for name, value in scope["headers"] if name == b"origin"]
    # Two Origin headers are not one allowed origin
    return values[0].decode("latin-1") if len(values) == 1 else None


class AuthHttpGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        method: str = scope["method"]
        sensitive_path = _is_sensitive_path(path)
        raw_path: bytes = scope.get("raw_path") or path.encode()
        checked = sensitive_path or settings.auth_mode == "session"
        if (
            checked
            and method in UNSAFE_METHODS
            and not _exempt(method, path, raw_path.split(b"?", 1)[0])
            and _origin(scope) not in settings.cors_origins
        ):
            await _forbidden(send, no_store=sensitive_path)
            return
        if not sensitive_path:
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"cache-control"
                ]
                message["headers"] = [*headers, (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, receive, send_no_store)


async def _forbidden(send: Send, *, no_store: bool) -> None:
    body = json.dumps({"detail": AUTH_ORIGIN_FORBIDDEN}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if no_store:
        headers.append((b"cache-control", b"no-store"))
    await send({"type": "http.response.start", "status": 403, "headers": headers})
    await send({"type": "http.response.body", "body": body})
