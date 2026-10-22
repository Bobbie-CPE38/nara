"""Render the actual AWS overlay with hostile local defaults; never start the app."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class SessionDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder, "test.env")
            env.write_text(
                "SITE_DOMAIN=example.test\nACME_EMAIL=a@example.test\nBASIC_AUTH_USER=team\n"
                "BASIC_AUTH_HASH=x\nPOSTGRES_PASSWORD=pw0123\nINTERNAL_JOB_SECRET=secret0123\n"
            )
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env),
                    "-f",
                    "docker-compose.yml",
                    "-f",
                    "deploy/aws/docker-compose.aws.yml",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=REPO,
                env={
                    **os.environ,
                    "APP_ENV": "dev",
                    "AUTH_MODE": "demo",
                    "AUTH_COOKIE_SECURE": "false",
                    "WEB_CONCURRENCY": "8",
                    "FORWARDED_ALLOW_IPS": "*",
                },
                text=True,
                capture_output=True,
                check=True,
            )
            cls.config = json.loads(result.stdout)

    def test_aws_cannot_inherit_demo_or_insecure_cookie(self):
        env = self.config["services"]["backend"]["environment"]
        self.assertEqual(env["APP_ENV"], "aws")
        self.assertEqual(env["AUTH_MODE"], "session")
        self.assertEqual(env["AUTH_COOKIE_SECURE"], "true")
        self.assertNotIn("WEB_CONCURRENCY", env)
        self.assertNotIn("FORWARDED_ALLOW_IPS", env)

    def test_one_worker_only_trusts_caddy(self):
        backend = self.config["services"]["backend"]
        command = " ".join(backend["command"])
        self.assertNotIn("--reload", command)
        self.assertIn("--workers 1", command)
        self.assertIn("--forwarded-allow-ips=172.30.64.2", command)
        caddy = self.config["services"]["caddy"]
        self.assertEqual(
            caddy["networks"]["staffing_net"]["ipv4_address"], "172.30.64.2"
        )
        self.assertEqual(
            self.config["networks"]["staffing_net"]["ipam"]["config"],
            [{"subnet": "172.30.64.0/24", "ip_range": "172.30.64.128/25"}],
        )

    def test_only_caddy_publishes_ports(self):
        for name, service in self.config["services"].items():
            if name == "caddy":
                self.assertEqual({p["target"] for p in service["ports"]}, {80, 443})
            else:
                self.assertFalse(service.get("ports"), name)


if __name__ == "__main__":
    unittest.main()
