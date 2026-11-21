"""Check the production frontend image of the AWS test machine (round 6 PR F3).

Run: python3 deploy/aws/test_frontend.py
Needs Docker (Compose 2.24.4 or later) and a network to pull node:24-alpine and the npm
packages. It builds the image with the build arguments that docker-compose.aws.yml
renders, starts it alone and checks the points of docs/workflow.md 6.30, part A:

  * the container runs `next start` in production mode, with no code mounted in and no
    value read from the environment;
  * every page answers, and an unknown path is a 404;
  * the browser bundle holds the API address of the machine and no `localhost:8000`
    outside the .map files, and none of the machine's secrets.

The first run takes a few minutes (npm ci and next build).
"""

import json
import os
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
DOMAIN = "nara-test.example.test"
API_URL = f"https://{DOMAIN}/api"
COMPOSE_FILES = ["-f", "docker-compose.yml", "-f", "deploy/aws/docker-compose.aws.yml"]
ENV_FILE = (
    f"SITE_DOMAIN='{DOMAIN}'\n"
    "ACME_EMAIL='a@example.test'\n"
    "BASIC_AUTH_USER='team'\n"
    "BASIC_AUTH_HASH='x'\n"
    "POSTGRES_PASSWORD='pw0123'\n"
    "INTERNAL_JOB_SECRET='js0123456'\n"
    "AWS_REGION='ap-southeast-1'\n"
)
# Every page of the app (docs/workflow.md 6.30), with the kind of page that is a 404
PAGES = [
    "/", "/gap", "/handoff", "/approvals", "/cases/1", "/me/offers", "/roster",
    "/demo/control", "/demo/line-sim", "/status",
]  # fmt: skip
# Names that exist only on the server side. None may be in what the browser downloads
SERVER_ONLY_NAMES = [
    "INTERNAL_JOB_SECRET", "POSTGRES_PASSWORD", "BASIC_AUTH_HASH", "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN", "DATABASE_URL",
]  # fmt: skip


def run(command, **kwargs):
    # UTF-8 on every machine: the pages hold Thai, and Windows would read them as cp1252
    return subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", check=True, **kwargs
    ).stdout


def sh(image, script):
    """A shell command inside the image, without starting the server."""
    return run(["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", script])


def rendered_frontend(env_file):
    output = run(
        ["docker", "compose", "--env-file", env_file, *COMPOSE_FILES, "config", "--format", "json"],
        cwd=REPO,
    )
    return json.loads(output)["services"]["frontend"]


class ProductionFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        env_file = Path(cls.folder.name, "nara.env")
        env_file.write_text(ENV_FILE, encoding="utf-8")
        cls.service = rendered_frontend(str(env_file))
        cls.image = f"nara-f3-test:{uuid.uuid4().hex[:8]}"
        cls.container = f"nara-f3-test-{uuid.uuid4().hex[:8]}"
        build = cls.service.get("build")
        if build is None:
            raise AssertionError(
                "docker-compose.aws.yml gives the frontend no build: it would run the dev server"
            )
        arguments = []
        for name, value in build["args"].items():
            arguments += ["--build-arg", f"{name}={value}"]
        run(
            ["docker", "build", "-f", str(REPO / "deploy/aws/frontend.Dockerfile"), *arguments,
             "-t", cls.image, str(REPO / "frontend")],
        )  # fmt: skip
        run(["docker", "run", "-d", "--name", cls.container, cls.image])
        cls.wait_until_ready()

    @classmethod
    def wait_until_ready(cls):
        for _ in range(60):
            probe = subprocess.run(
                ["docker", "exec", cls.container, "wget", "-qO", "/dev/null", "http://127.0.0.1:3000/"],
                capture_output=True,
            )
            if probe.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError(run(["docker", "logs", cls.container]))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "rm", "-f", cls.container], capture_output=True)
        subprocess.run(["docker", "rmi", "-f", cls.image], capture_output=True)
        cls.folder.cleanup()

    def status(self, path):
        probe = subprocess.run(
            ["docker", "exec", self.container, "wget", "-S", "-qO", "/dev/null", f"http://127.0.0.1:3000{path}"],
            capture_output=True,
            text=True,
        )
        lines = [line.strip() for line in probe.stderr.splitlines() if line.strip().startswith("HTTP/")]
        return int(lines[0].split()[1])

    def body(self, path, cookie=None):
        header = ["--header", f"Cookie: {cookie}"] if cookie else []
        return run(
            ["docker", "exec", self.container, "wget", "-qO-", *header, f"http://127.0.0.1:3000{path}"]
        )

    # --- the Compose layer ---------------------------------------------------
    def test_the_compose_layer_mounts_no_code_and_reads_nothing_from_the_environment(self):
        service = self.service
        self.assertNotIn("volumes", service)
        # Rendered as null: the image's own CMD runs, not the dev command of the main file
        self.assertIsNone(service.get("command"))
        self.assertIsNone(service.get("entrypoint"))
        self.assertNotIn("environment", service)
        self.assertNotIn("ports", service)
        self.assertEqual(service["image"], "nara-staffing-frontend:aws")

    def test_the_only_build_argument_is_the_api_address_of_the_machine(self):
        self.assertEqual(self.service["build"]["args"], {"NEXT_PUBLIC_API_BASE_URL": API_URL})

    def test_the_build_context_leaves_out_env_files_node_modules_and_tests(self):
        # next build bakes every NEXT_PUBLIC_* of an env file into the browser bundle, so an
        # env file of a developer's frontend folder must never reach the build stage
        with tempfile.TemporaryDirectory() as context:
            folder = Path(context)
            (folder / ".dockerignore").write_text(
                (REPO / "frontend/.dockerignore").read_text(encoding="utf-8"), encoding="utf-8"
            )
            for name in [".env", ".env.local", ".env.production", "node_modules/x", ".next/x", "tests/x"]:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("NEXT_PUBLIC_SECRET_THING=1\n", encoding="utf-8")
            for name in ["package.json", "src/app.ts"]:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            tag = f"nara-f3-context-{uuid.uuid4().hex[:8]}"
            dockerfile = "FROM node:24-alpine\nCOPY . /context\nRUN cd /context && find . -type f | sort > /listing\n"
            run(["docker", "build", "-q", "-f", "-", "-t", tag, str(folder)], input=dockerfile)
            try:
                listing = run(["docker", "run", "--rm", tag, "cat", "/listing"]).split()
            finally:
                subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)
        # The control: what the build needs is still in the context
        self.assertEqual(sorted(listing), ["./.dockerignore", "./package.json", "./src/app.ts"])

    # --- the running container ----------------------------------------------
    def test_the_container_runs_next_start_in_production_mode_as_a_plain_user(self):
        info = json.loads(run(["docker", "inspect", self.container]))[0]
        self.assertEqual(info["Mounts"], [])
        self.assertEqual(info["Config"]["User"], "node")
        self.assertIn("NODE_ENV=production", info["Config"]["Env"])
        self.assertEqual(info["Config"]["Cmd"][:2], ["./node_modules/.bin/next", "start"])
        # What actually runs: the production server, never the dev one
        processes = run(["docker", "exec", self.container, "ps"])
        self.assertIn("next-server", processes)
        self.assertNotIn("next dev", processes)
        self.assertNotIn("npm run dev", processes)
        logs = run(["docker", "logs", self.container])
        self.assertIn("Ready in", logs)
        self.assertNotIn("dev server", logs.lower())

    def test_every_page_answers_and_an_unknown_path_is_404(self):
        for path in PAGES:
            self.assertEqual(self.status(path), 200, path)
        self.assertEqual(self.status("/no-such-page"), 404)

    def test_the_logo_and_the_icon_of_the_team_are_served(self):
        # The image has only .next, node_modules and public: a file left out of it is a 404
        for path in ["/nara-logo.svg", "/icon.svg"]:
            self.assertEqual(self.status(path), 200, path)

    def test_the_pages_are_in_thai_unless_the_cookie_says_english(self):
        thai = self.body("/")
        self.assertIn('<html lang="th">', thai)
        self.assertIn("เมนูหลัก", thai)
        english = self.body("/", cookie="nara-lang=en")
        self.assertIn('<html lang="en">', english)
        self.assertIn("Main navigation", english)

    # --- the browser bundle --------------------------------------------------
    def files_with(self, text, folder=".next"):
        """Files under `folder` in the image that hold `text`, source maps left out."""
        script = f"find {folder} -type f ! -name '*.map' -exec grep -lF '{text}' {{}} + || true"
        return sh(self.image, script).split()

    def test_the_bundle_has_the_api_address_of_the_machine_and_no_localhost_8000(self):
        # Control first: the address is found in a client chunk, so the search sees the right files
        with_address = self.files_with(API_URL)
        self.assertTrue(any(name.startswith(".next/static/") for name in with_address), with_address)
        # The point: no fallback to the developer's address in any file but a source map
        self.assertEqual(self.files_with("localhost:8000"), [])

    def test_the_browser_downloads_no_server_secret_name(self):
        for name in SERVER_ONLY_NAMES:
            self.assertEqual(self.files_with(name, ".next/static"), [], name)


if __name__ == "__main__":
    os.chdir(REPO)
    unittest.main()
