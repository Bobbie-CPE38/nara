import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def _test_database_url() -> str:
    """TEST_DATABASE_URL if set, otherwise DATABASE_URL with `_test` appended to the DB name."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        dev = make_url(os.environ["DATABASE_URL"])
        url = dev.set(database=f"{dev.database}_test")
    # The session fixture drops this database, so never let it point at a real one
    if not (url.database or "").endswith("_test"):
        raise RuntimeError(f"Test database name must end with '_test', got {url.database!r}")
    return url.render_as_string(hide_password=False)


# Must run before anything under `app` is imported: settings, engine and
# alembic/env.py all read DATABASE_URL once at import time
TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.db.session import engine  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> Iterator[None]:
    """Recreate the test DB from scratch and migrate it to head, once per run."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")

    yield
    # Left in place after the run so failures can be inspected
    engine.dispose()


@pytest.fixture
def db() -> Iterator[Session]:
    """Fresh session per test; everything it writes is rolled back at the end.

    `create_savepoint` turns session.commit() inside service code into a
    savepoint release, so the outer transaction still discards it.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
