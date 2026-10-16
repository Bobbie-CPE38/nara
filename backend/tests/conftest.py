import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request

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

from app.core import clock  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.integrations.line import client as line_client  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests own their LINE mode, regardless of the developer's real credentials.

    Autouse fixtures run before explicit fixtures, so real-mode tests can still
    opt in and replace push/reply or the HTTP transport with deterministic doubles.
    Guard the transport too: accidentally enabling real mode must never send LINE.
    urllib.request is shared; leave unrelated local HTTP tests working normally.
    """
    monkeypatch.setenv("LINE_MODE", "simulation")
    monkeypatch.setattr(settings, "line_mode", "simulation")

    original_urlopen = line_client.urllib.request.urlopen

    def guarded_http(url: str | Request, *args: Any, **kwargs: Any) -> Any:
        hostname = urlsplit(url.full_url if isinstance(url, Request) else url).hostname or ""
        if hostname == "line.me" or hostname.endswith(".line.me"):
            # Escape best-effort `except Exception`: fail, don't defer the send.
            pytest.fail("Unmocked LINE HTTP call: replace the LINE transport in this test")
        return original_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(line_client.urllib.request, "urlopen", guarded_http)


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
def restore_empty_database() -> Iterator[None]:
    """Clean up tests that commit or rebuild the schema instead of using `db`.

    Opt in explicitly: ordinary tests keep their rollback-only sessions.
    Reset tests can leave connections behind when a child process is killed.
    """
    assert (engine.url.database or "").endswith("_test")
    try:
        yield
    finally:
        try:
            with engine.begin() as connection:
                # A backend waiting on a schema lock may not notice its client
                # died. End those connections before DROP can wait on them.
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                )
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
            engine.dispose()
            command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
        finally:
            clock.reset()


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
