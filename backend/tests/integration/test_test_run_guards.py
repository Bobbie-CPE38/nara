"""Who may run a test run, and whom the scripted people answer (round 6 PR EV5a, 6.35.6).

No route here gets past its guard, and the scripted answers run on the rolled-back
seed, so nothing in this module resets the database.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import AuditLog, CandidateOutreach, StaffingEvent
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType, OutreachStatus
from app.services import actor_service, audit_service, simulated_replies_service
from tests.integration.case_rows import make_case, offer, short_case
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_au2_review_points import (  # noqa: F401 (fixtures)
    client_of,
    scene,
    session_mode,
)

pytestmark = pytest.mark.usefixtures("stub_handlers")

ROUTES = (
    ("POST", "/demo/test-runs", {"tester_code": "T01", "scenario": "golden"}),
    ("POST", "/demo/test-runs/1/finish", None),
    ("POST", "/demo/test-runs/1/abort", None),
    ("GET", "/demo/test-runs", None),
    ("GET", "/demo/test-runs.csv", None),
)


@pytest.mark.usefixtures("scene")
@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_session_mode_wants_a_manager(method: str, path: str, body: dict[str, str] | None) -> None:
    anonymous = client_of(None).request(method, path, json=body)
    nurse = client_of(105).request(method, path, json=body)

    assert anonymous.status_code == 401
    assert nurse.status_code == 403
    assert nurse.json() == {"detail": "AUTH_FORBIDDEN"}


@pytest.mark.usefixtures("scene")
def test_a_manager_may_read_the_runs() -> None:
    head_nurse = client_of(900)

    assert head_nurse.get("/demo/test-runs").json() == []
    assert head_nurse.get("/demo/test-runs.csv").text.startswith("test_run_id,tester_code,")


# --------------------------------------------------------------------------- #
# Scripted people answer only the run's own case
# --------------------------------------------------------------------------- #
@pytest.fixture
def other_case_offer(production_seeded: Session) -> Iterator[tuple[Session, CandidateOutreach]]:
    """An offer to 202 (who declines after 45 s in the golden script) in a case of its own."""
    db = production_seeded
    case, items = short_case(db)
    sent = offer(db, case, items[202])
    db.commit()
    try:
        yield db, sent
    finally:
        clock.set_time(DEMO_NOW)


def _run_of(db: Session, event_id: int) -> int:
    """A golden run with simulated people whose case is the one of `event_id`."""
    audit_service.log(
        db,
        case_id=None,
        event_id=event_id,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        action=AuditAction.TEST_RUN_STARTED,
        entity_type=EntityType.TEST_RUN,
        entity_id=None,
        payload={"scenario": "golden", "auto_nurses": True, "event_id": event_id},
    )
    db.commit()
    return db.scalars(
        select(AuditLog.id).where(AuditLog.action == AuditAction.TEST_RUN_STARTED)
    ).one()


def _event_of(db: Session, case_id: int) -> int:
    return db.scalars(select(StaffingEvent.id).where(StaffingEvent.case_id == case_id)).one()


def test_outside_a_run_nobody_answers(
    other_case_offer: tuple[Session, CandidateOutreach],
) -> None:
    db, sent = other_case_offer
    clock.advance(timedelta(minutes=2))

    assert simulated_replies_service.answer_due(db) == []
    db.refresh(sent)
    assert sent.status == OutreachStatus.SENT


def test_a_run_answers_its_own_case_and_no_other(
    other_case_offer: tuple[Session, CandidateOutreach],
) -> None:
    db, sent = other_case_offer
    run_case = make_case(db, CaseStatus.WAITING_RESPONSE)
    run_id = _run_of(db, _event_of(db, run_case.id))
    clock.run_from(DEMO_NOW + timedelta(minutes=2), run_id)

    assert simulated_replies_service.answer_due(db) == []
    db.refresh(sent)
    assert sent.status == OutreachStatus.SENT


def test_a_run_answers_when_the_offer_is_in_its_case(
    other_case_offer: tuple[Session, CandidateOutreach],
) -> None:
    """The control of the test above: the same offer, now in the run's case, is answered."""
    db, sent = other_case_offer
    run_id = _run_of(db, _event_of(db, sent.case_id))
    clock.run_from(DEMO_NOW + timedelta(seconds=44), run_id)

    # Not yet due: 202 answers 45 s after the offer
    assert simulated_replies_service.answer_due(db) == []
    clock.advance(timedelta(seconds=1))
    assert simulated_replies_service.answer_due(db) == [sent.id]
    db.refresh(sent)
    assert sent.status == OutreachStatus.REJECTED
