"""Trusted CLI calls the running Backend so demo Clock is not process-local drift.

python -m app.line_accounts issue-code --staff-id 201
python -m app.line_accounts unlink --staff-id 201
Raw codes are displayed only after the Backend commits; deliver privately.
"""

import argparse
import json
import urllib.error
import urllib.request

from app.core.config import settings
from app.core.constants import MAX_BIGINT

ADMIN_BASE_URL = "http://localhost:8000/internal/line-accounts"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local LINE account administration")
    parser.add_argument("command", choices=["issue-code", "unlink"])
    parser.add_argument("--staff-id", type=int, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.staff_id <= MAX_BIGINT:
        parser.error("staff-id must be a positive bigint")
    if not settings.internal_job_secret:
        raise SystemExit("INTERNAL_JOB_SECRET is required")
    request = urllib.request.Request(
        f"{ADMIN_BASE_URL}/{args.staff_id}/{args.command}",
        method="POST",
        headers={"X-Internal-Secret": settings.internal_job_secret},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        if args.command == "issue-code":
            print(f"LINK {result['code']}")
            print(f"Expires at {result['expires_at']}")
        else:
            print(f"Unlinked {result['unlinked_contacts']} contact(s); unused codes revoked.")
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"LINE account command refused ({error.code}); no code is displayed."
        ) from None
    except Exception:
        # No remote body, SQL parameters, credentials or link code in errors.
        raise SystemExit("LINE account command failed; check the running Backend.") from None


if __name__ == "__main__":
    main()
