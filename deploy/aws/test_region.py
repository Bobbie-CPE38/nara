"""Check that the Region of Parameter Store and the Region of Bedrock never mix.

Run: python3 deploy/aws/test_region.py
Two different Regions are in play on the AWS test machine (docs/deploy-aws.md):
  * NARA_PARAMETER_REGION, set in /etc/nara/aws.conf, is where load-env.sh reads
    Parameter Store;
  * AWS_REGION, a Parameter written into /etc/nara/nara.env, is where the app calls Bedrock.
systemd puts everything in aws.conf into the environment of `docker compose`, and Compose
takes a variable from the process environment over --env-file. So a Parameter Store Region
named AWS_REGION in aws.conf would silently replace the Bedrock Region. These tests keep
the two names apart with different values on purpose.
Needs Docker (Compose 2.24 or later) and, for the loader test, a python:3.11-slim image.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
PARAMETER_REGION = "ap-southeast-1"
BEDROCK_REGION = "ap-northeast-1"
COMPOSE_FILES = ["-f", "docker-compose.yml", "-f", "deploy/aws/docker-compose.aws.yml"]
ENV_FILE = (
    "SITE_DOMAIN='nara-test.example.test'\n"
    "ACME_EMAIL='a@example.test'\n"
    "BASIC_AUTH_USER='team'\n"
    "BASIC_AUTH_HASH='x'\n"
    "POSTGRES_PASSWORD='pw0123'\n"
    "INTERNAL_JOB_SECRET='js0123'\n"
    f"AWS_REGION='{BEDROCK_REGION}'\n"
)


def backend_region(environment, *, unset_aws_region=False):
    """The AWS_REGION that the rendered backend service would get.

    `unset_aws_region` removes AWS_REGION from the process environment, which is what
    `/usr/bin/env -u AWS_REGION` does in nara.service."""
    process_environment = {**os.environ, **environment}
    if unset_aws_region:
        process_environment.pop("AWS_REGION", None)
    with tempfile.TemporaryDirectory() as folder:
        env_file = Path(folder) / "nara.env"
        env_file.write_text(ENV_FILE, encoding="utf-8")
        output = subprocess.run(
            ["docker", "compose", "--env-file", str(env_file), *COMPOSE_FILES, "config"],
            cwd=REPO,
            env=process_environment,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    return [line.split(":", 1)[1].strip() for line in output.splitlines() if "AWS_REGION:" in line]


@unittest.skipUnless(shutil.which("docker"), "needs docker")
class RegionsStayApart(unittest.TestCase):
    def test_the_parameter_store_region_variable_does_not_reach_the_backend(self):
        # What aws.conf now holds: the loader variable, not AWS_REGION
        self.assertEqual(
            backend_region({"NARA_PARAMETER_REGION": PARAMETER_REGION}), [BEDROCK_REGION]
        )

    def test_a_leftover_aws_region_in_the_process_would_override_the_bedrock_region(self):
        # The bug this test file exists for, kept as a control: without the guard,
        # an AWS_REGION in the process environment wins over the env file
        self.assertEqual(backend_region({"AWS_REGION": PARAMETER_REGION}), [PARAMETER_REGION])

    def test_the_unit_removes_aws_region_before_it_starts_compose(self):
        unit = (ROOT / "nara.service").read_text(encoding="utf-8")
        for key in ("ExecStart=", "ExecStop="):
            line = next(line for line in unit.splitlines() if line.startswith(key))
            self.assertIn("/usr/bin/env -u AWS_REGION /usr/bin/docker compose", line, line)
        # The same command line, run with a leftover AWS_REGION, gives the Bedrock Region
        self.assertEqual(
            backend_region({"AWS_REGION": PARAMETER_REGION}, unset_aws_region=True),
            [BEDROCK_REGION],
        )

    def run_loader(self, environment):
        """Run load-env.sh in a container with a stub `aws` that records its arguments."""
        stub = (
            "#!/bin/sh\n"
            'echo "$@" > /tmp/aws-arguments\n'
            'echo \'{"Parameters":[{"Name":"/nara/test/SITE_DOMAIN","Value":"x"},'
            '{"Name":"/nara/test/ACME_EMAIL","Value":"x"},'
            '{"Name":"/nara/test/BASIC_AUTH_USER","Value":"x"},'
            '{"Name":"/nara/test/BASIC_AUTH_HASH","Value":"x"},'
            '{"Name":"/nara/test/POSTGRES_PASSWORD","Value":"x"},'
            '{"Name":"/nara/test/INTERNAL_JOB_SECRET","Value":"x"},'
            f'{{"Name":"/nara/test/AWS_REGION","Value":"{BEDROCK_REGION}"}}]}}\'\n'
        )
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "aws").write_text(stub, encoding="utf-8", newline="\n")
            command = ["docker", "run", "--rm", "-e", "NARA_ENV_FILE=/tmp/out/nara.env"]
            for name, value in environment.items():
                command += ["-e", f"{name}={value}"]
            command += [
                "-v", f"{Path(folder) / 'aws'}:/usr/local/bin/aws:ro",
                "-v", f"{ROOT / 'load-env.sh'}:/load-env.sh:ro",
                "python:3.11-slim",
                "bash", "-c",
                "chmod +x /usr/local/bin/aws 2>/dev/null; cp /usr/local/bin/aws /tmp/aws && "
                "chmod +x /tmp/aws && PATH=/tmp:$PATH bash /load-env.sh; code=$?; "
                "echo CODE=$code; cat /tmp/aws-arguments 2>/dev/null; cat /tmp/out/nara.env 2>/dev/null",
            ]  # fmt: skip
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            return result.stdout

    def test_the_loader_reads_parameter_store_in_its_own_region_and_keeps_the_parameter(self):
        output = self.run_loader(
            {"NARA_PARAMETER_REGION": PARAMETER_REGION, "AWS_REGION": "us-east-1"}
        )
        self.assertIn("CODE=0", output)
        self.assertIn(f"--region {PARAMETER_REGION}", output)
        self.assertNotIn("--region us-east-1", output)
        # The AWS_REGION parameter reaches nara.env unchanged
        self.assertIn(f"AWS_REGION='{BEDROCK_REGION}'", output)

    def test_the_loader_refuses_the_old_name_and_says_what_to_change(self):
        output = self.run_loader({"AWS_REGION": PARAMETER_REGION})
        self.assertNotIn("CODE=0", output)
        self.assertIn("NARA_PARAMETER_REGION", output)


if __name__ == "__main__":
    unittest.main()
