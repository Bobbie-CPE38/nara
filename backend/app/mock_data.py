"""Offline large demo import. `python -m app.mock_data` previews; --apply writes once.

Run inside the backend container after alembic upgrade head. Stop the job service
and pause demo traffic during apply. Reads the running backend clock so the data
matches the page, including a frozen demo. No environment secrets are printed.
"""

import argparse
import json
import urllib.request
from datetime import datetime

from sqlalchemy import select, text

from app.db.models import DemoDataset
from app.db.session import SessionLocal
from app.seed.large_demo import DAYS, PROFILE, STAFF_COUNT, WARD_COUNT, counts, generate
from app.services.auth_service import hold_auth_gate


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
                    "current_namespace": counts(db),
                }
            )
        )
        if not args.apply:
            return
        with urllib.request.urlopen("http://127.0.0.1:8000/clock", timeout=5) as response:
            view = json.load(response)
        reference = datetime.fromisoformat(view["now"])
        result = generate(db, reference)
        db.commit()
        print(json.dumps({"loaded": result, "profile": PROFILE}))


if __name__ == "__main__":
    main()
