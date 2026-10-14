"""Test-only echo backend. Never forwards to Nara, LINE or a database."""

import base64
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    seen = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(str(Handler.seen).encode())

    def do_POST(self):
        Handler.seen += 1
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        expected = base64.b64encode(
            hmac.new(b"test-only-secret", body, hashlib.sha256).digest()
        ).decode()
        valid = hmac.compare_digest(self.headers.get("X-Line-Signature", ""), expected)
        self.send_response(200 if valid else 401)
        self.end_headers()
        self.wfile.write(
            json.dumps({"uri": self.path, "body": base64.b64encode(body).decode()}).encode()
        )


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
