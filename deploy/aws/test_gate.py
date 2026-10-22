"""Run the real Caddyfile of the AWS test machine against fake upstreams using Docker.

Run: python3 deploy/aws/test_gate.py
It starts Caddy with deploy/aws/Caddyfile (plain HTTP on a local port, no certificate),
a fake backend and a fake frontend, then runs deploy/aws/check-gate.sh against it.
No AWS account, real domain, LINE credential, Nara service or database is used.
Needs Docker, Python and bash. AU4 policy is docs/workflow.md 6.33.5: Basic
protects Demo, app identity comes from sessions, and only an exact POST is a webhook.
"""

import shutil
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
PASSWORD = "test-only-password"
USER = "team"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


@unittest.skipUnless(
    shutil.which("docker") and shutil.which("bash"), "needs docker and bash"
)
class AwsGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tag = uuid4().hex[:12]
        cls.network = f"nara-aws-gate-{tag}"
        cls.names = {
            "backend": f"nara-aws-gate-backend-{tag}",
            "frontend": f"nara-aws-gate-frontend-{tag}",
            "caddy": f"nara-aws-gate-caddy-{tag}",
        }
        cls.addClassCleanup(cls.cleanup)
        docker("network", "create", cls.network)
        for name, port in (("backend", "8000"), ("frontend", "3000")):
            docker(
                "run", "-d", "--name", cls.names[name], "--network", cls.network,
                "--network-alias", name,
                "-v", f"{ROOT / 'fake_upstream.py'}:/fake_upstream.py:ro",
                "python:3.11-slim", "python", "/fake_upstream.py", name, port,
            )  # fmt: skip
        password_hash = docker(
            "run", "--rm", "caddy:2.10-alpine", "caddy", "hash-password", "--plaintext", PASSWORD
        )  # fmt: skip
        docker(
            "run", "-d", "--name", cls.names["caddy"], "--network", cls.network,
            "-p", "127.0.0.1::80",
            "-v", f"{ROOT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "-e", "SITE_DOMAIN=http://:80",
            "-e", "ACME_EMAIL=test@example.test",
            "-e", f"BASIC_AUTH_USER={USER}",
            "-e", f"BASIC_AUTH_HASH={password_hash}",
            "caddy:2.10-alpine",
        )  # fmt: skip
        port = (
            docker("port", cls.names["caddy"], "80/tcp")
            .splitlines()[0]
            .rsplit(":", 1)[1]
        )
        cls.base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                response = urllib.request.urlopen(cls.base + "/", timeout=2)
                response.close()
                break
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 200:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Caddy did not start: " + docker("logs", cls.names["caddy"])
                )
            time.sleep(0.2)

    @classmethod
    def cleanup(cls):
        for name in cls.names.values():
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False
            )
        subprocess.run(
            ["docker", "network", "rm", cls.network], capture_output=True, check=False
        )

    def seen(self, name):
        """Every request the upstream has logged so far, in the order they came."""
        logs = subprocess.run(
            ["docker", "logs", self.names[name]],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [
            line.strip() for line in logs.splitlines() if line.startswith(name + " ")
        ]

    def new_requests(self, name, before):
        """Only the requests that arrived after `before`, so a test does not depend on
        what the other tests already sent through the shared containers."""
        return sorted(self.seen(name)[len(before) :])

    def probe(self, method, path, *, basic=False, headers=None):
        import base64

        headers = dict(headers or {})
        if basic:
            headers["Authorization"] = (
                "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
            )
        request = urllib.request.Request(
            self.base + path, headers=headers, method=method
        )
        try:
            answer = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            answer = error
        with answer:
            return answer.code, answer.headers, answer.read()

    def run_gate(self, *extra):
        return subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, PASSWORD, *extra],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def flag(self, name, content=None):
        script = f"from pathlib import Path; p=Path('/tmp/{name}'); " + (
            "p.unlink(missing_ok=True)"
            if content is None
            else f"p.write_text({content!r})"
        )
        docker("exec", self.names["backend"], "python", "-c", script)

    def test_external_preflight(self):
        result = self.run_gate("--require-real-line")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("live AU4 checklist remains required", result.stdout)

    def test_optional_account_checks_keep_the_cookie_and_log_out(self):
        result = subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, PASSWORD, "--staff-id", "101"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            input="fake-account-password\n",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok  other simulator identity forbidden: HTTP 403", result.stdout)
        self.assertIn("ok  logged out session: HTTP 401", result.stdout)
        self.assertNotIn("test-session", result.stdout)
        self.assertNotIn("fake-account-password", result.stdout)

    def test_private_password_prompts_and_wrong_basic_credentials(self):
        result = subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, "--staff-id", "101"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            input=PASSWORD + "\nfake-account-password\n",
            timeout=180,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(PASSWORD, result.stdout)
        self.assertNotIn("test-session", result.stdout)
        result = subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, "wrong-password"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL  Demo page with Basic", result.stdout)

    def test_demo_and_private_bypasses_never_reach_upstreams(self):
        for path in (
            "/api/internal/x",
            "/api/INTERNAL/x",
            "/api/%69nternal/x",
            "/api//internal/x",
            "/api/internal/../internal/x",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json",
            "/api/DEMO/reset",
            "/api/%64emo/reset",
            "/api//demo/reset",
            "/api/demo/../demo/reset",
            "/%61pi/demo/reset",
            "/API/demo/reset",
            "/%64emo/control",
            "/DEMO/control",
            "/demo//control",
            "/demo/../demo/control",
        ):
            before = {name: self.seen(name) for name in ("backend", "frontend")}
            for basic in (False, True):
                code, _, _ = self.probe("POST", path, basic=basic)
                self.assertEqual(code, 404, (path, basic, code))
            for name, old_requests in before.items():
                self.assertEqual(self.new_requests(name, old_requests), [], path)

    def test_demo_requires_basic_but_business_uses_session(self):
        for path in ("/demo", "/demo/control", "/api/demo", "/api/demo/reset"):
            code, headers, _ = self.probe("POST", path)
            self.assertEqual(code, 401, path)
            self.assertTrue(headers.get("WWW-Authenticate", "").startswith("Basic"))
        code, headers, _ = self.probe("GET", "/api/dashboard", basic=True)
        self.assertEqual(code, 401)
        self.assertIsNone(headers.get("WWW-Authenticate"))

    def test_signed_webhook_only_exact_raw_post(self):
        for path in (
            "/api/line/webhook?x=1",
            "/api/line/webhook/",
            "/api/LINE/webhook",
            "/api//line/webhook",
            "/api/%6Cine/webhook",
            "/api/line/webhook%2f",
            "/api/line/webhook/../health",
            "/api/line/webhooks",
        ):
            before = self.seen("backend")
            code, _, _ = self.probe(
                "POST", path, basic=True, headers={"X-Line-Signature": "test-signed"}
            )
            self.assertEqual(code, 404, path)
            self.assertEqual(self.new_requests("backend", before), [], path)
        code, _, _ = self.probe(
            "POST", "/api/line/webhook", headers={"X-Line-Signature": "test-signed"}
        )
        self.assertEqual(code, 200)
        self.assertEqual(self.probe("GET", "/api/line/webhook")[0], 404)

    def test_client_cannot_supply_its_own_forwarded_identity(self):
        import json

        _, _, raw = self.probe(
            "GET",
            "/api/health",
            headers={
                "X-Forwarded-For": "203.0.113.200",
                "X-Forwarded-Proto": "https",
            },
        )
        body = json.loads(raw)
        self.assertNotIn("203.0.113.200", body["forwarded_for"])
        self.assertEqual(body["forwarded_proto"], "http")

    def test_preflight_fails_when_aws_reports_demo(self):
        self.flag("nara-test-demo", "1")
        try:
            result = self.run_gate()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AWS must report AUTH_MODE=session", result.stdout)
        finally:
            self.flag("nara-test-demo")

    def test_real_line_rejects_basic_challenge(self):
        self.flag("nara-test-webhook-basic", "1")
        try:
            result = self.run_gate("--require-real-line")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL  webhook missing signature", result.stdout)
        finally:
            self.flag("nara-test-webhook-basic")

    def test_strict_real_line_rejects_503(self):
        self.flag("nara-test-webhook-status", "503")
        try:
            self.assertEqual(self.run_gate().returncode, 0)
            result = self.run_gate("--require-real-line")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL  webhook missing signature", result.stdout)
        finally:
            self.flag("nara-test-webhook-status")


if __name__ == "__main__":
    unittest.main()
