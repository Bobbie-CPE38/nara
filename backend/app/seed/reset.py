"""Rebuild the demo database for POST /demo/reset (docs/walking-skeleton.md step 2.3).

Runs inside the API process because the frozen clock lives in process memory.

The LLM ledger survives a reset (round 6 PR B1): the daily and trial quota counters and
every LLM_CALL_LOG row with its cost. Otherwise a reset would renew the paid allowance
of the same real day and erase what was spent. The rebuild is one transaction, so a
failed reset leaves the old database as it was.

The ledger tables are locked exclusively before they are copied and until the commit, so
a gateway write is either in the copy or waits and then lands in the rebuilt tables: none
is lost. A write that holds another table's lock while it waits can deadlock with the
DROP; PostgreSQL ends one side, and the reset starts over (a few times).

Web accounts and the permanent people behind them survive too (round 6 PR AU1,
docs/workflow.md 6.33.7): every STAFF row with its auth_subject, their USER actors and
every AUTH_ACCOUNT with its password hash, closed flag, must-change flag and credential
version. Every AUTH_SESSION is gone, so everyone logs in again. Before copying anything
the reset takes the exclusive side of the Auth reset gate (auth_service), which every
auth write and session check takes shared: a login or a password change is either in
the copy or waits and runs on the rebuilt tables.

A seeded staff ID gets back the subject, role, home ward and status it had, so a reset
never changes what an account may do; the rest of the Golden Case is reloaded as usual.
A kept staff row that the seed does not create is put back as it was. If any kept
person's role or ward no longer exists, the whole reset fails and rolls back rather
than drop that person or their account.
"""

import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import SessionLocal, engine
from app.domain.enums import ActorType, LlmWorkType
from app.seed import load
from app.services import auth_service

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_reset_lock = Lock()
_DEADLOCK_RETRIES = 3

# Kept across a reset. A table missing before the reset (an older schema) is skipped.
# The order is the order the gateway takes its locks (counter, then log), so the reset's
# LOCK TABLE cannot deadlock with a gateway write on these three
LLM_LEDGER_TABLES = ("llm_daily_usage", "llm_trial_usage", "llm_call_log")
# References to demo rows that the reset deletes. The ids restart after a reset, so the
# kept log rows lose them and record when instead (detached_at). A model trial refers to
# no demo row and keeps everything
_DEMO_REFERENCES = ("explanation_id", "case_id", "plan_id", "subject_id")


class IdentityConflictError(RuntimeError):
    """A kept person or account cannot be put back, so the reset rolled back."""


def reset_demo() -> datetime:
    """Drop everything but the LLM ledger, migrate to head, load the Golden Case, freeze
    the clock at D 21:00.

    Safe to call repeatedly in this API process. Concurrent requests wait their turn.
    Returns the frozen demo time.
    """
    # Schema changes, Alembic's in-process context, and the demo clock must not overlap.
    # A context manager releases the lock even if migration or seeding raises.
    with _reset_lock:
        for attempt in range(_DEADLOCK_RETRIES + 1):
            try:
                return _reset_demo()
            except OperationalError as error:
                deadlock = isinstance(error.orig, psycopg.errors.DeadlockDetected)
                if not deadlock or attempt == _DEADLOCK_RETRIES:
                    raise
    raise AssertionError("unreachable")


def _reset_demo() -> datetime:
    # D = today in real time, not whatever an earlier reset froze. The clock is not unfrozen
    # for this: the migration takes seconds, and a clock that followed real time meanwhile
    # showed on the pages as unfrozen and let the job use real time
    reset_at = datetime.now(clock.APP_TIMEZONE)
    demo_time = reset_at.replace(hour=21, minute=0, second=0, microsecond=0)
    config = Config(str(ALEMBIC_INI))

    with engine.begin() as connection:
        # Before any table lock: auth transactions take this gate before their row locks
        auth_service.take_reset_gate(connection)
        held = _hold_llm_ledger(connection)
        subjects = _hold_identities(connection)
        large_profile = False
        if _columns(connection, "public.demo_dataset"):
            profiles = connection.scalars(text("SELECT profile FROM demo_dataset")).all()
            from app.seed.large_demo import PROFILE

            if any(profile != PROFILE for profile in profiles):
                raise IdentityConflictError("Unknown demo dataset profile; reset refused.")
            large_profile = PROFILE in profiles
        # Dropping the schema also removes alembic_version and resets every sequence
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        # golden_case.seed() requires the frozen demo clock, and created_at reads it
        clock.set_time(demo_time)
        options = {key: SessionLocal.kw[key] for key in ("autoflush", "expire_on_commit")}
        with Session(bind=connection, **options) as db:
            load(db, preserved_subjects=subjects, large_profile=large_profile)
            db.flush()
        # After the seed: load() refuses to seed a table that already has rows
        if subjects is not None:
            _restore_identities(connection)
        _restore_llm_ledger(connection, held, reset_at)
    engine.dispose()

    return demo_time


def _held(table: str) -> str:
    return f"held_{table}"


def _hold_llm_ledger(connection: Connection) -> list[str]:
    """Lock the ledger, then copy it into temporary tables, which DROP SCHEMA public does
    not reach. The lock lasts until the transaction ends."""
    existing = [
        table
        for table in LLM_LEDGER_TABLES
        if connection.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"})
    ]
    if existing:
        # Waits for gateway transactions in progress, so their writes are in the copy
        connection.execute(text(f"LOCK TABLE {', '.join(existing)} IN ACCESS EXCLUSIVE MODE"))
    for table in existing:
        connection.execute(
            text(f"CREATE TEMPORARY TABLE {_held(table)} ON COMMIT DROP AS TABLE {table}")
        )
    return existing


def _hold_identities(connection: Connection) -> dict[int, uuid.UUID] | None:
    """Copy every staff row, the USER actors and the accounts, and return each staff
    ID's subject. None for a schema from before PR AU1, which has nothing to keep."""
    if "auth_subject" not in _columns(connection, "public.staff"):
        return None
    connection.execute(text("CREATE TEMPORARY TABLE held_staff ON COMMIT DROP AS TABLE staff"))
    connection.execute(
        text(
            "CREATE TEMPORARY TABLE held_user_actors ON COMMIT DROP AS"
            " SELECT name, actor_type, staff_id FROM actors WHERE actor_type = :user"
        ),
        {"user": ActorType.USER.value},
    )
    # The account table arrived in the same migration as the subject column
    connection.execute(
        text("CREATE TEMPORARY TABLE held_auth_account ON COMMIT DROP AS TABLE auth_account")
    )
    rows = connection.execute(text("SELECT id, auth_subject FROM held_staff"))
    return {staff_id: subject for staff_id, subject in rows}


def _restore_identities(connection: Connection) -> None:
    """Put back every person's authorization metadata, their actors, and every account.

    Runs after the seed, which already gave each seeded staff ID its old subject. A
    seeded person also gets back the role, home ward and status they had: the seed's
    values would otherwise change what an existing account may do, for example make a
    closed-out head nurse ACTIVE again (6.33.7). Their name and the scenario rows come
    from the seed. A person the seed did not create comes back as the whole old row."""
    changed = connection.scalars(
        text(
            "SELECT h.id FROM held_staff h JOIN staff s ON s.id = h.id"
            " WHERE s.auth_subject <> h.auth_subject"
        )
    ).all()
    if changed:
        raise IdentityConflictError(f"Seeded staff {sorted(changed)} lost their subject")
    orphans = connection.scalars(
        text(
            "SELECT h.id FROM held_staff h"
            " WHERE NOT EXISTS (SELECT 1 FROM role r WHERE r.id = h.role_id)"
            " OR NOT EXISTS (SELECT 1 FROM ward w WHERE w.id = h.home_ward_id)"
        )
    ).all()
    if orphans:
        raise IdentityConflictError(
            f"Staff {sorted(orphans)} refer to a role or ward the demo no longer has"
        )

    connection.execute(
        text(
            "UPDATE staff s SET role_id = h.role_id, home_ward_id = h.home_ward_id,"
            " status = h.status FROM held_staff h WHERE s.id = h.id"
        )
    )

    for table, held_rows in (("staff", "held_staff"), ("auth_account", "held_auth_account")):
        kept = set(_columns(connection, f"pg_temp.{held_rows}"))
        columns = ", ".join(c for c in _columns(connection, f"public.{table}") if c in kept)
        # Only staff rows the seed did not create; every account
        missing = (
            " WHERE NOT EXISTS (SELECT 1 FROM staff s WHERE s.id = h.id)"
            if table == "staff"
            else ""
        )
        connection.execute(
            text(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {held_rows} h{missing}")
        )
        if table == "staff":
            # Seeded people already have their actor. A kept one gets a new actor ID
            connection.execute(
                text(
                    "INSERT INTO actors (name, actor_type, staff_id)"
                    " SELECT name, actor_type, staff_id FROM held_user_actors a"
                    " WHERE NOT EXISTS (SELECT 1 FROM actors x WHERE x.staff_id = a.staff_id)"
                )
            )
    # Kept staff IDs can be above what the seed synced
    connection.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('staff', 'id'), max(id))"
            " FROM staff HAVING max(id) IS NOT NULL"
        )
    )


def _columns(connection: Connection, relation: str) -> list[str]:
    return list(
        connection.scalars(
            text(
                "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(:relation)"
                " AND attnum > 0 AND NOT attisdropped ORDER BY attnum"
            ),
            {"relation": relation},
        )
    )


def _restore_llm_ledger(connection: Connection, held: list[str], reset_at: datetime) -> None:
    for table in held:
        kept = set(_columns(connection, _held(table)))
        current = _columns(connection, f"public.{table}")
        if table == "llm_call_log":
            _restore_call_log(connection, kept, current, reset_at)
            continue
        columns = [c for c in current if c in kept]
        connection.execute(
            text(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"SELECT {', '.join(columns)} FROM {_held(table)}"
            )
        )
    if "llm_call_log" in held:
        # The ids are kept, so an attempt in flight during the reset still finds its row
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('llm_call_log', 'id'), max(id))"
                " FROM llm_call_log HAVING max(id) IS NOT NULL"
            )
        )


def _restore_call_log(
    connection: Connection, kept: set[str], current: list[str], reset_at: datetime
) -> None:
    """Put the held log rows into the current shape. A log from before PR B1 has no
    work_type, so every row of it is a ranking explanation."""
    # A trial refers to no demo row and keeps everything; every other row is detached
    is_trial = "work_type = :trial" if "work_type" in kept else "false"
    values: dict[str, str] = {}
    for column in current:
        if column == "work_type":
            values[column] = "work_type" if column in kept else ":rank"
        elif column == "detached_at":
            old = "detached_at" if column in kept else "NULL"
            values[column] = f"CASE WHEN {is_trial} THEN NULL ELSE coalesce({old}, :reset_at) END"
        elif column in _DEMO_REFERENCES:
            if column in kept:
                values[column] = f"CASE WHEN {is_trial} THEN {column} END"
        elif column in kept:
            values[column] = column
    connection.execute(
        text(
            f"INSERT INTO llm_call_log ({', '.join(values)}) "
            f"SELECT {', '.join(values.values())} FROM {_held('llm_call_log')}"
        ),
        {
            "trial": LlmWorkType.MODEL_TRIAL.value,
            "rank": LlmWorkType.RANK_EXPLANATION.value,
            "reset_at": reset_at,
        },
    )
