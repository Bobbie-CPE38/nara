"""Exercise the real nginx config against an isolated fake backend using Docker.

Run: python3 dev/line-webhook-proxy/test_proxy.py
No real LINE credential, public tunnel, Nara service or database is used.
"""

import base64
import hashlib
import hmac
import http.client
import importlib.util
import io
import json
import subprocess
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
BODY = '{ "events": [], "text": "ทดสอบ" }\n'.encode()


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def request(port, method, uri, body=b"", signature="", *, chunked=False):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            method, uri, body=body, headers={"X-Line-Signature": signature}, encode_chunked=chunked
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


class ProxyGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tag = uuid4().hex[:12]
        cls.network = f"nara-proxy-test-{tag}"
        cls.backend = f"nara-proxy-backend-{tag}"
        cls.proxy = f"nara-proxy-{tag}"
        cls.addClassCleanup(cls.cleanup)
        docker("network", "create", cls.network)
        docker(
            "run",
            "-d",
            "--name",
            cls.backend,
            "--network",
            cls.network,
            "--network-alias",
            "host.docker.internal",
            "-p",
            "127.0.0.1::8000",
            "-v",
            f"{ROOT / 'fake_backend.py'}:/fake_backend.py:ro",
            "python:3.11-slim",
            "python",
            "/fake_backend.py",
        )
        docker(
            "run",
            "-d",
            "--name",
            cls.proxy,
            "--network",
            cls.network,
            "-p",
            "127.0.0.1::8080",
            "-v",
            f"{ROOT / 'nginx.conf'}:/etc/nginx/nginx.conf:ro",
            "nginx:1.28-alpine",
        )
        cls.backend_port = int(docker("port", cls.backend, "8000/tcp").rsplit(":", 1)[1])
        cls.proxy_port = int(docker("port", cls.proxy, "8080/tcp").rsplit(":", 1)[1])
        deadline = time.monotonic() + 20
        while True:
            try:
                assert request(cls.backend_port, "GET", "/seen")[0] == 200
                assert request(cls.proxy_port, "GET", "/")[0] == 404
                break
            except (OSError, http.client.HTTPException):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    @classmethod
    def cleanup(cls):
        for name in (cls.proxy, cls.backend):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", cls.network], capture_output=True)

    def seen(self):
        return int(request(self.backend_port, "GET", "/seen")[1])

    def test_local_and_public_check_script_against_fake_upstream(self):
        spec = importlib.util.spec_from_file_location("check_gate", ROOT / "check_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        output = io.StringIO()
        with (
            patch.object(
                gate.sys, "argv", ["check_gate.py", f"http://127.0.0.1:{self.proxy_port}"]
            ),
            patch.object(gate.getpass, "getpass", return_value="test-only-secret"),
            redirect_stdout(output),
        ):
            gate.main()
        self.assertIn("Gate checks passed", output.getvalue())

    def test_exact_post_preserves_body_and_signature(self):
        signature = base64.b64encode(
            hmac.new(b"test-only-secret", BODY, hashlib.sha256).digest()
        ).decode()
        status, payload = request(self.proxy_port, "POST", "/line/webhook", BODY, signature)
        self.assertEqual(status, 200)
        result = json.loads(payload)
        self.assertEqual(result["uri"], "/line/webhook")
        self.assertEqual(base64.b64decode(result["body"]), BODY)

    def test_invalid_signature_still_reaches_backend_validation(self):
        self.assertEqual(request(self.proxy_port, "POST", "/line/webhook", BODY, "invalid")[0], 401)

    def test_raw_uri_variants_never_reach_upstream(self):
        paths = [
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
            "/internal/merge-windows/close-due",
            "/api/line/webhook",
        ]
        for uri in paths:
            with self.subTest(uri=uri):
                before = self.seen()
                self.assertEqual(request(self.proxy_port, "POST", uri, BODY)[0], 404)
                self.assertEqual(self.seen(), before)

    def test_non_post_methods_never_reach_upstream(self):
        for method in ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]:
            with self.subTest(method=method):
                before = self.seen()
                self.assertEqual(
                    request(self.proxy_port, method, "/line/webhook")[0],
                    405 if method == "TRACE" else 404,
                )
                self.assertEqual(self.seen(), before)

    def test_body_limit_blocks_known_length_and_chunked(self):
        for chunked in [False, True]:
            with self.subTest(chunked=chunked):
                before = self.seen()
                body = b"x" * (1024 * 1024 + 1)
                if chunked:
                    body = iter([body[: 1024 * 1024], body[1024 * 1024 :]])
                self.assertEqual(
                    request(self.proxy_port, "POST", "/line/webhook", body, chunked=chunked)[0], 413
                )
                self.assertEqual(self.seen(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
