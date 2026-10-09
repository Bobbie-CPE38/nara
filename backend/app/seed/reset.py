"""Rebuild the demo database for POST /demo/reset (docs/walking-skeleton.md step 2.3).

Runs inside the API process because the frozen clock lives in process memory.
"""

from datetime import datetime
from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core import clock
from app.db.session import SessionLocal, engine
from app.seed import load

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_reset_lock = Lock()


def reset_demo() -> datetime:
    """Drop everything, migrate to head, load the Golden Case, freeze the clock at D 21:00.

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
    demo_time = clock.now().replace(hour=21, minute=0, second=0, microsecond=0)

    # Dropping the schema also removes alembic_version and resets every sequence
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    command.upgrade(Config(str(ALEMBIC_INI)), "head")

    # golden_case.seed() requires the frozen demo clock, and created_at reads it
    clock.set_time(demo_time)
    with SessionLocal.begin() as db:
        load(db)

    return demo_time
