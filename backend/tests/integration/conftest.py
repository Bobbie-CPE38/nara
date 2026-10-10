"""Fixtures shared by the integration tests: the demo clock, the Golden Case seed
and stand-in workflow handlers."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import StaffingCase
from app.db.session import SessionLocal, engine
from app.domain.enums import CaseStatus
from app.seed import load
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult

DEMO_NOW = datetime(2026, 10, 9, 21, 0, tzinfo=clock.APP_TIMEZONE)

# Each automatic status moves to its golden-path successor, writing nothing
STUB_STEPS: dict[CaseStatus, tuple[CaseStatus, bool]] = {
    CaseStatus.OPEN: (CaseStatus.ASSESSING, False),
    CaseStatus.ASSESSING: (CaseStatus.OPTIMIZING, False),
    CaseStatus.OPTIMIZING: (CaseStatus.OUTREACH, False),
    CaseStatus.OUTREACH: (CaseStatus.WAITING_RESPONSE, True),
    CaseStatus.SAFETY_VALIDATION: (CaseStatus.WAITING_APPROVAL, True),
    CaseStatus.EXECUTING: (CaseStatus.RESOLVED, False),
}


def returns(**result: Any) -> orchestrator.Handler:
    """A handler that writes nothing and returns HandlerResult(**result)."""

    def handler(db: Session, case: StaffingCase) -> HandlerResult:
        return HandlerResult(**result)

    return handler


@pytest.fixture
def stub_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every workflow handler with a stub that only moves the case on.

    For tests of code around the handlers (the orchestrator, event intake): a real
    handler needs the rows of the steps before it, and has its own tests.
    Not autouse: handler tests run the real code. A module opts in with
    `pytestmark = pytest.mark.usefixtures("stub_handlers")`.
    """
    # A new handler needs a stub here, or its real code would run in those tests
    assert set(STUB_STEPS) == set(orchestrator.HANDLERS)
    for status, (next_status, wait) in STUB_STEPS.items():
        monkeypatch.setitem(
            orchestrator.HANDLERS, status, returns(next_status=next_status, wait=wait)
        )


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
