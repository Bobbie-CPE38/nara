"""Rebuild the demo database for POST /demo/reset (docs/walking-skeleton.md step 2.3).

Runs inside the API process because the frozen clock lives in process memory.

The LLM ledger survives a reset (round 6 PR B1): the daily and trial quota counters and
every LLM_CALL_LOG row with its cost. Otherwise a reset would renew the paid allowance
of the same real day and erase what was spent. The rebuild is one transaction, so a
failed reset leaves the old database as it was.
"""

from datetime import datetime
from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import SessionLocal, engine
from app.domain.enums import LlmWorkType
from app.seed import load

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_reset_lock = Lock()

# Kept across a reset. A table missing before the reset (an older schema) is skipped
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
        return _reset_demo()


def _reset_demo() -> datetime:
    # D = today in real time, not whatever an earlier reset froze
    clock.reset()
    reset_at = clock.now()
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
    """Copy the ledger into temporary tables, which DROP SCHEMA public does not reach."""
    held = []
    for table in LLM_LEDGER_TABLES:
        if connection.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}):
            connection.execute(
                text(f"CREATE TEMPORARY TABLE {_held(table)} ON COMMIT DROP AS TABLE {table}")
            )
            held.append(table)
    return held


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
        columns = [c for c in _columns(connection, f"public.{table}") if c in kept]
        values = [_restored_value(table, column) for column in columns]
        connection.execute(
            text(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"SELECT {', '.join(values)} FROM {_held(table)}"
            ),
            {"trial": LlmWorkType.MODEL_TRIAL.value, "reset_at": reset_at}
            if table == "llm_call_log"
            else {},
        )
    if "llm_call_log" in held:
        # The ids are kept, so an attempt in flight during the reset still finds its row
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('llm_call_log', 'id'), max(id))"
                " FROM llm_call_log HAVING max(id) IS NOT NULL"
            )
        )


def _restored_value(table: str, column: str) -> str:
    if table != "llm_call_log":
        return column
    if column in _DEMO_REFERENCES:
        return f"CASE WHEN work_type = :trial THEN {column} END"
    if column == "detached_at":
        return "CASE WHEN work_type = :trial THEN NULL ELSE coalesce(detached_at, :reset_at) END"
    return column
