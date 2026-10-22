"""Offline large demo import. `python -m app.mock_data` previews; --apply writes once.

Run inside the backend container after alembic upgrade head. Stop the job service
and pause demo traffic during apply. Reads the running backend clock so the data
matches the page, including a frozen demo. No environment secrets are printed.
"""

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime

from sqlalchemy import select, text

from app.db.models import DemoDataset
from app.db.session import SessionLocal
from app.seed.large_demo import DAYS, PROFILE, STAFF_COUNT, WARD_COUNT, counts, generate
from app.services.auth_service import hold_auth_gate


def backend_reference() -> datetime:
    """Read only the local clock; report transport/format errors without a traceback."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/clock", timeout=5) as response:
            view = json.load(response)
        reference = datetime.fromisoformat(view["now"])
        if reference.tzinfo is None:
            raise ValueError("Clock must include timezone")
        return reference
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(
            "Cannot read a valid local Backend /clock. Start the backend, wait for it "
            "to become healthy, then retry. No dataset was written."
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="add the dataset in one transaction")
    args = parser.parse_args()
    with SessionLocal() as db:
        hold_auth_gate(db)
        db.execute(text("SELECT pg_advisory_xact_lock(6210, 2)"))
        existing = db.scalar(select(DemoDataset).where(DemoDataset.profile == PROFILE))
        print(
            json.dumps(
                {
                    "profile": PROFILE,
                    "planned": {
                        "staff": STAFF_COUNT,
                        "wards": WARD_COUNT,
                        "days": DAYS,
                        "shifts": WARD_COUNT * DAYS * 2,
                    },
                    "already_loaded": existing is not None,
                    "reference_at": existing.reference_at.isoformat() if existing else None,
                    "current_namespace": counts(db),
                }
            )
        )
        if not args.apply:
            return
        if existing is not None:
            reference = existing.reference_at
        else:
            try:
                reference = backend_reference()
            except ValueError as error:
                parser.exit(1, f"Import refused: {error}\n")
        result = generate(db, reference)
        db.commit()
        print(json.dumps({"loaded": result, "profile": PROFILE}))


if __name__ == "__main__":
    main()
