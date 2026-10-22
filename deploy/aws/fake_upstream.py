"""Gate-test doubles only: no Nara database, LINE, real auth or AWS is used.

Logs paths only, never headers, cookies or bodies. Flags are private to each test
container. The real backend permissions are covered by backend integration tests.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NAME, PORT = sys.argv[1], int(sys.argv[2])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        print(f"{NAME} {self.command} {self.path}", flush=True)
        status, body = 200, {"status": "ok"}
        extra = {}
        path = self.path.split("?", 1)[0]
        if NAME == "backend":
            logged_in = (
                "nara_session=test-session" in self.headers.get("Cookie", "")
                and not Path("/tmp/nara-test-revoked").exists()
            )
            me = {
                "staff_id": 101,
                "role": "staff",
                "home_ward_id": 1,
                "must_change_password": False,
            }
            if path == "/auth/login":
                Path("/tmp/nara-test-revoked").unlink(missing_ok=True)
                body = me
                extra["Set-Cookie"] = (
                    "nara_session=test-session; Path=/; HttpOnly; SameSite=Lax"
                )
            elif path == "/auth/logout":
                Path("/tmp/nara-test-revoked").touch()
                status, body = 204, {}
                extra["Set-Cookie"] = "nara_session=; Path=/; Max-Age=0"
            elif path == "/auth/config":
                body = {
                    "auth_mode": "demo"
                    if Path("/tmp/nara-test-demo").exists()
                    else "session"
                }
            elif path == "/line/webhook":
                flag = Path("/tmp/nara-test-webhook-status")
                status = int(flag.read_text()) if flag.exists() else 401
                if self.headers.get("X-Line-Signature") == "test-signed":
                    status = 200
                if Path("/tmp/nara-test-webhook-basic").exists():
                    extra["WWW-Authenticate"] = 'Basic realm="test-webhook"'
            elif path == "/health":
                # Lets the real-Caddy test inspect forwarding without a diagnostic production route.
                body = {
                    "forwarded_for": self.headers.get("X-Forwarded-For"),
                    "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
                }
            elif path != "/clock":
                if not logged_in:
                    status, body = 401, {"detail": "AUTH_REQUIRED"}
                elif path in ("/approvals", "/events") or (
                    path == "/demo/line-sim/offers" and "staff_id=101" not in self.path
                ):
                    status, body = 403, {"detail": "AUTH_FORBIDDEN"}
                else:
                    body = me if path == "/auth/me" else []
        raw = json.dumps(body).encode()
        self.send_response(status)
        for key, value in extra.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = do_PUT = do_DELETE = respond


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
