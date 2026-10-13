"""Concurrent offer limits against the migrated PostgreSQL schema (round 1 PR 1c)."""

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    OutreachPolicy,
    Role,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    CandidateSource,
    CaseStatus,
    Channel,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.services import availability_service, policy_service
from tests.integration.conftest import DEMO_NOW


def _offer(
    db: Session,
    *,
    staff_id: int = 201,
    status: OutreachStatus = OutreachStatus.SENT,
    case_status: CaseStatus = CaseStatus.WAITING_RESPONSE,
    shift_id: int = 1,
) -> CandidateOutreach:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift_id,
        staff_id=105,
        occurred_at=DEMO_NOW,
        status=EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        shift_id=shift_id,
        status=case_status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    event.case_id = case.id
    db.flush()
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="test",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=staff_id,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=shift_id,
    )
    db.add(item)
    db.flush()
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        expires_at=DEMO_NOW + timedelta(seconds=300),
        sent_at=DEMO_NOW,
        status=status,
    )
    db.add(outreach)
    db.flush()
    return outreach


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_seeded_limit_counts_across_cases_and_shifts(seeded: Session, count: int) -> None:
    for index in range(count):
        _offer(
            seeded,
            status=OutreachStatus.SENT if index % 2 == 0 else OutreachStatus.ACCEPTED,
            shift_id=1 if index % 2 == 0 else 2,
        )
    assert availability_service.staff_at_offer_limit(seeded, [201]) == (
        {201} if count >= 3 else set()
    )


@pytest.mark.parametrize("status", list(OutreachStatus))
def test_only_sent_and_accepted_count(seeded: Session, status: OutreachStatus) -> None:
    policy = policy_service.get_outreach_policy(seeded)
    policy.maximum_concurrent_offers_per_staff = 1
    seeded.flush()
    _offer(seeded, status=status)
    expected = {201} if status in {OutreachStatus.SENT, OutreachStatus.ACCEPTED} else set()
    assert availability_service.staff_at_offer_limit(seeded, [201]) == expected


@pytest.mark.parametrize("case_status", list(CaseStatus))
@pytest.mark.parametrize("status", [OutreachStatus.SENT, OutreachStatus.ACCEPTED])
def test_only_running_cases_count(
    seeded: Session, case_status: CaseStatus, status: OutreachStatus
) -> None:
    policy_service.get_outreach_policy(seeded).maximum_concurrent_offers_per_staff = 1
    seeded.flush()
    _offer(seeded, status=status, case_status=case_status)
    expected = set() if case_status in AUTOMATION_STOPPED_STATUSES else {201}
    assert availability_service.staff_at_offer_limit(seeded, [201]) == expected


def test_count_is_per_staff_and_limited_to_requested_ids(seeded: Session) -> None:
    for _ in range(3):
        _offer(seeded, staff_id=201)
        _offer(seeded, staff_id=203)
    for _ in range(2):
        _offer(seeded, staff_id=202)
    assert availability_service.staff_at_offer_limit(seeded, [202, 201, 201, 999]) == {201}


def test_reads_policy_limit_instead_of_hardcoding_seed(seeded: Session) -> None:
    for _ in range(2):
        _offer(seeded)
    policy_service.get_outreach_policy(seeded).maximum_concurrent_offers_per_staff = 2
    seeded.flush()
    assert availability_service.staff_at_offer_limit(seeded, [201]) == {201}
    policy_service.get_outreach_policy(seeded).maximum_concurrent_offers_per_staff = 4
    seeded.flush()
    assert availability_service.staff_at_offer_limit(seeded, [201]) == set()


def test_cancellation_releases_capacity_after_flush(production_seeded: Session) -> None:
    offers = [_offer(production_seeded) for _ in range(3)]
    assert availability_service.staff_at_offer_limit(production_seeded, [201]) == {201}
    offers[0].status = OutreachStatus.CANCELLED
    production_seeded.flush()
    assert availability_service.staff_at_offer_limit(production_seeded, [201]) == set()


def test_helper_does_not_flush_or_commit(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    for _ in range(3):
        _offer(seeded)
    # This invalid pending row would fail if the read implicitly autoflushed.
    pending = Role()
    seeded.add(pending)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Offer-limit reads must not flush or commit")

    monkeypatch.setattr(seeded, "flush", forbidden)
    monkeypatch.setattr(seeded, "commit", forbidden)
    assert availability_service.staff_at_offer_limit(seeded, [201]) == {201}
    assert pending in seeded.new


def test_empty_input_does_not_query(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("An empty staff list must not access the database")

    monkeypatch.setattr(db, "get", forbidden)
    monkeypatch.setattr(db, "scalars", forbidden)
    assert availability_service.staff_at_offer_limit(db, []) == set()


def test_missing_policy_is_an_error_even_when_no_offers_exist(seeded: Session) -> None:
    seeded.delete(policy_service.get_outreach_policy(seeded))
    # A newer policy does not silently replace the agreed demo policy id=1.
    seeded.add(
        OutreachPolicy(
            id=2,
            maximum_concurrent_offers_per_staff=5,
            version="newer",
            effective_from=DEMO_NOW + timedelta(days=1),
            offer_timeout_seconds=300,
        )
    )
    seeded.flush()
    with pytest.raises(LookupError, match="Outreach policy id=1 is missing"):
        availability_service.staff_at_offer_limit(seeded, [201])


@pytest.mark.parametrize("limit", [0, -1])
def test_database_rejects_nonpositive_limit(db: Session, limit: int) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_outreach_policy_offer_limit_positive"),
        db.begin_nested(),
    ):
        db.add(
            OutreachPolicy(
                maximum_concurrent_offers_per_staff=limit,
                version="test",
                effective_from=DEMO_NOW,
                offer_timeout_seconds=300,
            )
        )
        db.flush()
