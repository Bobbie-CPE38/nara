"""Fixtures shared by the integration tests: the demo clock and the Golden Case seed."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import SessionLocal, engine
from app.seed import load

DEMO_NOW = datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE)


@pytest.fixture
def frozen_clock() -> Iterator[datetime]:
    """Freeze the clock at DEMO_NOW for one test.

    Not autouse: test_demo_reset needs the real clock. A module that wants it for
    every test sets `pytestmark = pytest.mark.usefixtures("frozen_clock")`.
    """
    clock.set_time(DEMO_NOW)
    yield DEMO_NOW
    clock.reset()


@pytest.fixture
def seeded(db: Session, frozen_clock: datetime) -> Session:
    """The rolled-back test session with base data and the Golden Case loaded."""
    load(db)
    return db


@pytest.fixture
def production_seeded(frozen_clock: datetime) -> Iterator[Session]:
    """A seeded session with the same options as SessionLocal (autoflush off).

    The `db` fixture autoflushes, which hides bugs that only appear with the
    production settings. Everything is rolled back at the end, like `db`.
    """
    options = {key: SessionLocal.kw[key] for key in ("autoflush", "expire_on_commit")}
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", **options)
    try:
        load(session)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
