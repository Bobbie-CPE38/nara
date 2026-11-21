"""Web account script (round 6 PR AU1, docs/workflow.md 6.33.2). No HTTP route does this.

Run it in the backend container, for example:
python -m app.auth_accounts create --staff-id 105
python -m app.auth_accounts reset-password --staff-id 105
python -m app.auth_accounts disable --staff-id 105
python -m app.auth_accounts enable --staff-id 105
python -m app.auth_accounts demo-accounts            (AUTH_MODE=demo and APP_ENV=dev only)

The password is never an argument (argv shows in `ps` and shell history). It is asked
twice without echo, or read as one line from standard input with --password-stdin; only
the line ending is removed. `create` and `reset-password` set a temporary password that
must be changed at the first login; reset-password and disable end every session.
demo-accounts gives every seeded staff member without an account the same password,
with no forced change, for a local demo.

Talks to the database directly, unlike app.line_accounts: accounts use real time, not
the Backend's Demo Clock. Nothing secret is printed.
"""

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import passwords
from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.db.models import AuthAccount, Staff
from app.db.session import SessionLocal
from app.seed.scenarios import golden_case, multi_ward
from app.services import auth_service

COMMANDS = ("create", "reset-password", "disable", "enable", "demo-accounts")


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        line = sys.stdin.readline()
        password = line.removesuffix("\n").removesuffix("\r")
    else:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat it: ") != password:
            raise SystemExit("The passwords do not match; nothing changed.")
    if not passwords.acceptable_password(password):
        raise SystemExit(
            f"A password must be {passwords.PASSWORD_MIN_LENGTH} to "
            f"{passwords.PASSWORD_MAX_LENGTH} characters; nothing changed."
        )
    return password


def demo_staff_ids() -> list[int]:
    return [row[0] for row in (*golden_case.STAFF_DATA, *multi_ward.STAFF_DATA)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Web account administration")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--staff-id", type=int)
    parser.add_argument(
        "--password-stdin", action="store_true", help="read the password from standard input"
    )
    args = parser.parse_args(argv)
    if args.command == "demo-accounts":
        if args.staff_id is not None:
            parser.error("demo-accounts takes no --staff-id")
        if settings.auth_mode != "demo" or settings.app_env != "dev":
            raise SystemExit("demo-accounts runs only with AUTH_MODE=demo and APP_ENV=dev.")
    elif args.staff_id is None or not 1 <= args.staff_id <= MAX_BIGINT:
        parser.error("--staff-id must be a positive bigint")

    # None only for demo-accounts, which does not use it
    staff_id = int(args.staff_id or 0)
    needs_password = args.command in ("create", "reset-password", "demo-accounts")
    password = read_password(args.password_stdin) if needs_password else ""
    with SessionLocal() as db:
        try:
            if args.command == "create":
                auth_service.create_account(db, staff_id, password)
                print(f"Account for staff {staff_id} created; change the password at login.")
            elif args.command == "reset-password":
                auth_service.reset_password(db, staff_id, password)
                print(f"Password of staff {staff_id} reset; every session ended.")
            elif args.command in ("disable", "enable"):
                auth_service.set_disabled(db, staff_id, args.command == "disable")
                print(f"Account of staff {staff_id} {args.command}d.")
            else:
                created = _demo_accounts(db, password)
                print(f"Created {len(created)} demo account(s): {created}")
        except auth_service.AccountError as error:
            raise SystemExit(f"{error}; nothing changed.") from None


def _demo_accounts(db: Session, password: str) -> list[int]:
    have = set(
        db.scalars(
            select(Staff.id).join(AuthAccount, AuthAccount.staff_subject == Staff.auth_subject)
        )
    )
    created = []
    for staff_id in demo_staff_ids():
        if staff_id in have or db.get(Staff, staff_id) is None:
            continue
        auth_service.create_account(db, staff_id, password, must_change_password=False)
        created.append(staff_id)
    return created


if __name__ == "__main__":
    main()
