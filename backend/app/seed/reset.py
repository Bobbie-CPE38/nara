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
"""

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
from app.domain.enums import LlmWorkType
from app.seed import load

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
        held = _hold_llm_ledger(connection)
        # Dropping the schema also removes alembic_version and resets every sequence
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        # golden_case.seed() requires the frozen demo clock, and created_at reads it
        clock.set_time(demo_time)
        options = {key: SessionLocal.kw[key] for key in ("autoflush", "expire_on_commit")}
        with Session(bind=connection, **options) as db:
            load(db)
            db.flush()
        # After the seed: load() refuses to seed a table that already has rows
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
