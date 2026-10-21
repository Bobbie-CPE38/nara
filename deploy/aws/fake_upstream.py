"""Test-only upstream for deploy/aws/test_gate.py. Never talks to Nara, LINE or a database.

One file plays both the backend (port 8000) and the frontend (port 3000): the first
argument is the name and the second the port. Every request it receives is printed
as "<name> <method> <path>" so the test can read what got past the gate.
"""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NAME = sys.argv[1]
PORT = int(sys.argv[2])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        print(f"{NAME} {self.command} {self.path}", flush=True)
        # The real backend refuses a webhook without a good LINE signature with 401
        # (no WWW-Authenticate header, which is how the gate's own 401 is told apart)
        status = 200
        if NAME == "backend" and self.path == "/line/webhook":
            # Isolated gate tests can model a real-mode or unconfigured backend.
            status_file = Path("/tmp/nara-test-webhook-status")
            status = int(status_file.read_text()) if status_file.exists() else 401
        body = b"ok"
        self.send_response(status)
        if (NAME == "backend" and self.path == "/line/webhook"
                and Path("/tmp/nara-test-webhook-basic").exists()):
            self.send_header("WWW-Authenticate", 'Basic realm="test-webhook"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = respond


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
