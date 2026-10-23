"""The outreach limits of a case (round 6 PR EV6, docs/workflow.md 6.36.8).

At most OUTREACH_POLICY.maximum_waves_per_case waves, and no new wave after
case_outreach_deadline_seconds from the opening of the case. A limit never cuts a wave
short: the case waits for the offers it sent, then goes to MANUAL_HANDOFF with the limit as
the reason. The Golden Case: 105 reports leave, wave 1 is 201 and 202, and 203 is left for
wave 2.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import AuditLog, CandidateItem, CandidateOutreach, OutreachPolicy
from app.domain.enums import AuditAction, CaseStatus
from app.main import app
from app.services import outreach_limit_service
from tests.integration import case_rows
from tests.integration.test_orchestrator_graph_parity import Driver


@pytest.fixture
def run(production_seeded: Session) -> Iterator[Driver]:
    db = production_seeded

    def request_db() -> Iterator[Session]:
        with Session(
            bind=db.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as request_session:
            yield request_session

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app) as client:
            yield Driver(client, db)
    finally:
        app.dependency_overrides.clear()


def _policy(db: Session, **values: int) -> None:
    policy = db.get(OutreachPolicy, 1)
    assert policy is not None
    for name, value in values.items():
        setattr(policy, name, value)
    db.commit()


def _contacted(run: Driver) -> list[int]:
    run.db.expire_all()
    return sorted(
        run.db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(CandidateOutreach.case_id == run.case_id)
        )
    )


def _handoff_reason(run: Driver) -> str | None:
    run.db.expire_all()
    row = run.db.scalar(
        select(AuditLog).where(
            AuditLog.case_id == run.case_id, AuditLog.action == AuditAction.MANUAL_HANDOFF
        )
    )
    return None if row is None else str(row.payload["reason"])


def test_without_a_limit_the_next_wave_goes_to_203(run: Driver) -> None:
    assert run.report_leave()["case_status"] == "WAITING_RESPONSE"
    assert run.answer(201, "REJECT") == "WAITING_RESPONSE"
    assert run.answer(202, "REJECT") == "WAITING_RESPONSE"

    assert _contacted(run) == [201, 202, 203]
    assert outreach_limit_service.waves_sent(run.db, run.case_id) == 2


def test_the_last_allowed_wave_ends_in_a_handoff_not_a_new_wave(run: Driver) -> None:
    _policy(run.db, maximum_waves_per_case=1)
    assert run.report_leave()["case_status"] == "WAITING_RESPONSE"

    # One offer of the wave is still out: the case waits for it
    assert run.answer(201, "REJECT") == "WAITING_RESPONSE"
    assert _handoff_reason(run) is None
    assert run.answer(202, "REJECT") == "MANUAL_HANDOFF"

    assert _contacted(run) == [201, 202]
    assert _handoff_reason(run) == "WAVE_LIMIT_REACHED"


def test_after_the_deadline_the_case_waits_for_its_wave_then_hands_off(run: Driver) -> None:
    # Shorter than the 300 seconds of an offer, so the deadline passes while wave 1 is out
    _policy(run.db, case_outreach_deadline_seconds=120)
    assert run.report_leave()["case_status"] == "WAITING_RESPONSE"
    assert outreach_limit_service.stop_reason(run.db, run.case_id) is None

    # The deadline passes with both offers of wave 1 still out
    clock.advance(timedelta(seconds=120))
    assert outreach_limit_service.stop_reason(run.db, run.case_id) == "OUTREACH_DEADLINE_REACHED"
    assert run.answer(201, "REJECT") == "WAITING_RESPONSE"
    assert run.answer(202, "REJECT") == "MANUAL_HANDOFF"

    assert _contacted(run) == [201, 202]
    assert _handoff_reason(run) == "OUTREACH_DEADLINE_REACHED"


def test_an_accept_before_the_deadline_still_counts_after_it(run: Driver) -> None:
    """The deadline stops new waves only: an answer to the wave already sent still staffs."""
    _policy(run.db, case_outreach_deadline_seconds=60)
    assert run.report_leave()["case_status"] == "WAITING_RESPONSE"
    clock.advance(timedelta(seconds=61))

    assert run.answer(201, "ACCEPT") == "WAITING_APPROVAL"
    assert run.decide(201, approved=True) == "RESOLVED"
    assert _handoff_reason(run) is None


@pytest.mark.parametrize(
    ("column", "constraint"),
    [
        ("maximum_waves_per_case", "ck_outreach_policy_wave_limit_positive"),
        ("case_outreach_deadline_seconds", "ck_outreach_policy_case_deadline_positive"),
    ],
)
def test_the_policy_limits_must_be_positive(seeded: Session, column: str, constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint), seeded.begin_nested():
        policy = seeded.get(OutreachPolicy, 1)
        assert policy is not None
        setattr(policy, column, 0)
        seeded.flush()


def test_the_first_wave_is_never_stopped(seeded: Session) -> None:
    """Review of #145: a clock moved past the deadline before wave 1 handed the case off
    with nobody asked. Before its first wave a case has no limit."""
    case = case_rows.make_case(seeded, CaseStatus.OPTIMIZING)
    clock.advance(timedelta(days=1))

    assert outreach_limit_service.stop_reason(seeded, case.id) is None
