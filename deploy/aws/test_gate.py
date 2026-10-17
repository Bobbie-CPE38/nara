"""Run the real Caddyfile of the AWS test machine against fake upstreams using Docker.

Run: python3 deploy/aws/test_gate.py
It starts Caddy with deploy/aws/Caddyfile (plain HTTP on a local port, no certificate),
a fake backend and a fake frontend, then runs deploy/aws/check-gate.sh against it.
No AWS account, real domain, LINE credential, Nara service or database is used.
Needs Docker, bash and curl. The rule under test is docs/workflow.md 6.30: every path
needs the login except the exact request `POST /api/line/webhook`.
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
# What may reach the upstreams in one run of check-gate.sh. The no-login probes of
# gated paths must never appear here, so a hole in the gate fails the test
EXPECTED_BACKEND = ["backend GET /clock", "backend GET /health", "backend POST /line/webhook"]
EXPECTED_FRONTEND = ["frontend GET /", "frontend GET /demo/control"]


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


@unittest.skipUnless(shutil.which("docker") and shutil.which("bash"), "needs docker and bash")
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
        port = docker("port", cls.names["caddy"], "80/tcp").splitlines()[0].rsplit(":", 1)[1]
        cls.base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                urllib.request.urlopen(cls.base + "/", timeout=2)
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 401:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Caddy did not start: " + docker("logs", cls.names["caddy"]))
            time.sleep(0.2)

    @classmethod
    def cleanup(cls):
        for name in cls.names.values():
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", cls.network], capture_output=True)

    def seen(self, name):
        """Every request the upstream has logged so far, in the order they came."""
        logs = subprocess.run(
            ["docker", "logs", self.names[name]], capture_output=True, text=True
        ).stdout
        return [line.strip() for line in logs.splitlines() if line.startswith(name + " ")]

    def new_requests(self, name, before):
        """Only the requests that arrived after `before`, so a test does not depend on
        what the other tests already sent through the shared containers."""
        return sorted(self.seen(name)[len(before):])

    def test_check_gate_script_passes_and_only_allowed_requests_reach_the_upstreams(self):
        before = {name: self.seen(name) for name in ("backend", "frontend")}
        result = subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, PASSWORD],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("All checks passed", result.stdout)
        # A path that got past the gate by mistake would show up here
        self.assertEqual(self.new_requests("backend", before["backend"]), EXPECTED_BACKEND)
        self.assertEqual(self.new_requests("frontend", before["frontend"]), EXPECTED_FRONTEND)

    def test_the_script_fails_with_a_wrong_password(self):
        # Shows that the script can fail at all: with a wrong password the "with the
        # login" checks must fail. That the script catches a hole in the Caddyfile is
        # shown by putting the old `path` matcher back (docs/deploy-aws.md)
        result = subprocess.run(
            ["bash", "check-gate.sh", self.base, USER, "not-the-password"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
