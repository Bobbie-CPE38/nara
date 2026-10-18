"""Manual env startup checks; no AWS credentials, network or real secrets required."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "SITE_DOMAIN",
    "ACME_EMAIL",
    "BASIC_AUTH_USER",
    "BASIC_AUTH_HASH",
    "POSTGRES_PASSWORD",
    "INTERNAL_JOB_SECRET",
)
FILLED = "\n".join(f"{name}='test-value'" for name in REQUIRED) + "\n"


class ManualEnvValidation(unittest.TestCase):
    def check_env(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nara.env"
            path.write_text(content, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "validate-manual-env.py"), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_unedited_example_is_rejected(self):
        self.assertNotEqual(self.check_env((ROOT / "manual.env.example").read_text()).returncode, 0)

    def test_missing_or_empty_required_values_are_rejected(self):
        for name in REQUIRED:
            for replacement in ("", f"{name}=''\n", f"{name}='   '\n"):
                with self.subTest(name=name, replacement=replacement):
                    content = FILLED.replace(f"{name}='test-value'\n", replacement)
                    self.assertNotEqual(self.check_env(content).returncode, 0)

    def test_filled_file_with_optional_empty_values_and_literal_hash_is_accepted(self):
        content = FILLED.replace(
            "BASIC_AUTH_HASH='test-value'", "BASIC_AUTH_HASH='$2b$hash$literal'"
        )
        result = self.check_env(content + "LINE_CHANNEL_SECRET=''\n# comment\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_duplicate_required_value_and_invalid_format_are_rejected(self):
        for content in (
            FILLED + "SITE_DOMAIN='duplicate'\n",
            FILLED.replace("SITE_DOMAIN='test-value'", 'SITE_DOMAIN="double-quoted"'),
            FILLED.replace("SITE_DOMAIN='test-value'", "SITE_DOMAIN=unquoted"),
        ):
            with self.subTest(content=content):
                self.assertNotEqual(self.check_env(content).returncode, 0)

    def test_failure_does_not_log_secret_or_execute_shell_content(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "executed"
            content = FILLED + f"UNUSED='$(touch {marker})'\n"
            self.assertEqual(self.check_env(content).returncode, 0)
            self.assertFalse(marker.exists())
        result = self.check_env(FILLED + "BASIC_AUTH_HASH='private-test-secret'\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-test-secret", result.stderr + result.stdout)

    def test_drop_in_validates_after_resetting_parameter_store_prestart(self):
        lines = (ROOT / "manual-env.conf").read_text().splitlines()
        commands = [line for line in lines if line.startswith("ExecStartPre=")]
        self.assertEqual(
            commands,
            [
                "ExecStartPre=",
                "ExecStartPre=/usr/bin/test -s /etc/nara/nara.env",
                "ExecStartPre=/usr/bin/python3 /opt/nara/deploy/aws/validate-manual-env.py "
                "/etc/nara/nara.env",
            ],
        )


if __name__ == "__main__":
    unittest.main()
