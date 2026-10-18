"""Validate the documented manual env format without evaluating or printing secrets."""

import re
import sys
from pathlib import Path

REQUIRED = (
    "SITE_DOMAIN",
    "ACME_EMAIL",
    "BASIC_AUTH_USER",
    "BASIC_AUTH_HASH",
    "POSTGRES_PASSWORD",
    "INTERNAL_JOB_SECRET",
)


def validate(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    if "REPLACE_WITH_" in content:
        raise ValueError("Manual env still contains placeholders; replace them before starting.")
    values: dict[str, str] = {}
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.strip().partition("=")
        name = name.strip()
        if name not in REQUIRED:
            continue
        if name in values:
            raise ValueError(f"Duplicate required setting: {name}")
        # Match the example's single-line, single-quoted literal values. Never source
        # the file: shell expansion would both execute code and alter bcrypt hashes.
        match = re.fullmatch(r"'([^'\r\n]*)'", value.strip()) if separator else None
        if match is None or not match[1].strip():
            raise ValueError(f"Required setting {name} must have a nonempty single-quoted value.")
        values[name] = match[1]
    missing = [name for name in REQUIRED if name not in values]
    if missing:
        raise ValueError("Missing required settings: " + ", ".join(missing))
    # Compose interpolates this directly into DATABASE_URL without URL encoding.
    if re.fullmatch(r"[A-Za-z0-9]+", values["POSTGRES_PASSWORD"]) is None:
        raise ValueError("POSTGRES_PASSWORD must contain ASCII letters and digits only.")


if __name__ == "__main__":
    try:
        validate(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError):
        # Do not expose values or decoder excerpts in systemd's journal.
        print(
            "Manual env validation failed: provide all six required settings as nonempty "
            "single-quoted values, remove duplicates and replace REPLACE_WITH_ placeholders. "
            "POSTGRES_PASSWORD must contain ASCII letters and digits only.",
            file=sys.stderr,
        )
        sys.exit(1)
