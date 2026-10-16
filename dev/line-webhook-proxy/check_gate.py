"""Check the opt-in nginx gate locally or through a Quick Tunnel.

Only an empty LINE verification body is forwarded. No staff answer/reset is sent.
"""

import base64
import getpass
import hashlib
import hmac
import http.client
import sys
from urllib.parse import urlsplit


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python3 check_gate.py http://127.0.0.1:18080 OR https://<tunnel-host>"
        )
    url = urlsplit(sys.argv[1])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or url.username
    ):
        raise SystemExit("Supply only the proxy/tunnel base URL, without credentials or paths.")
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit(
            "HTTP is permitted only for the loopback proxy; public checks require HTTPS."
        )
    secret = getpass.getpass("LINE Channel secret (not logged or stored): ")
    if not secret:
        raise SystemExit("A secret is required for the signed verification check.")
    body = b'{"events":[]}'
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

    def check(method, uri, expected, payload=b"", signed="", chunked=False):
        factory = (
            http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        )
        connection = factory(url.hostname, url.port, timeout=20)
        try:
            connection.request(
                method,
                uri,
                body=payload,
                headers={"X-Line-Signature": signed},
                encode_chunked=chunked,
            )
            response = connection.getresponse()
            response.read()
            if response.status != expected:
                raise SystemExit(
                    f"INCOMPLETE: {method} {uri} returned {response.status}, expected {expected}"
                )
            print(f"PASS {method} {uri}: {response.status}")
        finally:
            connection.close()

    check("POST", "/line/webhook", 200, body, signature)
    check("POST", "/line/webhook", 401, body, "invalid")
    for uri in [
        "/",
        "/line/webhook/",
        "/line/webhook/anything",
        "/line/webhooks",
        "/line/webhook?x=1",
        "/line/%77ebhook",
        "/line/webhook%2F",
        "//line/webhook",
        "/line//webhook",
        "/line/webhook/..",
        "/LINE/webhook",
        "/line/Webhook",
        "/demo/reset",
        "/demo/attendance/check-in",
        "/internal/merge-windows/close-due",
        "/internal/line-accounts/201/issue-code",
        "/internal/line-accounts/201/unlink",
        "/api/line/webhook",
    ]:
        check("POST", uri, 404, body)
    for method in ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]:
        check(method, "/line/webhook", 405 if method == "TRACE" else 404)
    check("POST", "/line/webhook", 413, b"x" * (1024 * 1024 + 1))
    check("POST", "/line/webhook", 413, iter([b"x" * (1024 * 1024), b"x"]), chunked=True)
    print("Gate checks passed. This is not a live candidate accept/reject test.")


if __name__ == "__main__":
    main()
