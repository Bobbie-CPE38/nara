"""Round 1 PR 4: real HTTP decisions, reserves, foreign cases and PostgreSQL races."""

import threading
from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    HardConstraintPolicy,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingRequirement,
    StaffingRequirementRole,
)
from app.db.session import SessionLocal
from app.domain.enums import (
    AssignmentType,
    AuditAction,
    CaseStatus,
    OutreachStatus,
    ShiftType,
)
from app.main import app
from app.seed import load
from app.services import actor_service, approval_service, outreach_service, safety_service
from tests.integration.case_rows import (
    make_case,
    make_plan,
    offer,
    record_gap,
    short_case,
)
from tests.integration.conftest import DEMO_NOW

HEADERS = {"X-Demo-User": "900"}


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    def request_db():
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def accept(client: TestClient, row: CandidateOutreach, staff_id: int):
    response = client.post(
        "/demo/line-sim/respond",
        headers={"X-Demo-User": str(staff_id)},
        json={"outreach_id": row.id, "response": "ACCEPT"},
    )
    assert response.status_code == 200, response.text
    return response


def decide(client: TestClient, request: ApprovalRequest, approved=True, reason=None):
    response = client.post(
        f"/approvals/{request.id}/decision",
        headers=HEADERS,
        json={"approved": approved, "reason": reason},
    )
    assert response.status_code == 200, response.text
    return response


def request_for(db: Session, row: CandidateOutreach) -> ApprovalRequest:
    return db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.candidate_item_id == row.candidate_item_id)
    ).one()


def replacements(db: Session) -> list[RosterAssignment]:
    return list(
        db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.assignment_type == AssignmentType.REPLACEMENT)
            .order_by(RosterAssignment.id)
        )
    )


def two_offers(db: Session, *leaving: int):
    case, items = short_case(db, *leaving)
    rows = [offer(db, case, items[staff_id]) for staff_id in (201, 202, 203)]
    db.commit()
    return case, rows


def test_two_person_gap_executes_each_approval_and_cancels_reserve_only_at_completion(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    case, rows = two_offers(db, 104, 105)
    for staff_id, row in zip((201, 202, 203), rows, strict=True):
        accept(client, row, staff_id)
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 2
    first = decide(client, request_for(db, rows[0]))
    assert first.json()["case_status"] == "WAITING_APPROVAL"
    assert [r.staff_id for r in replacements(db)] == [201]
    assert outreach_service.list_offers(db, staff_id=201)[0].is_assigned
    assert not outreach_service.list_offers(db, staff_id=202)[0].is_assigned
    db.expire_all()
    assert rows[2].status == OutreachStatus.ACCEPTED
    second = decide(client, request_for(db, rows[1]))
    assert second.json()["case_status"] == "RESOLVED"
    assert [r.staff_id for r in replacements(db)] == [201, 202]
    db.expire_all()
    assert rows[0].status == rows[1].status == OutreachStatus.ACCEPTED
    assert rows[2].status == OutreachStatus.CANCELLED
    assert rows[2].response_at == DEMO_NOW
    resolved = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.CASE_RESOLVED)
    ).one()
    assert resolved.payload == {
        "assignment_ids": [r.id for r in replacements(db)],
        "cancelled_outreach_ids": [rows[2].id],
    }
    assert client.get("/approvals?pending=true", headers=HEADERS).json() == []
    assert (
        client.post(
            f"/approvals/{request_for(db, rows[1]).id}/decision",
            headers=HEADERS,
            json={"approved": True},
        ).status_code
        == 409
    )


def test_rejection_promotes_oldest_reserve_and_records_candidate_reason(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    accept(client, rows[0], 201)
    accept(client, rows[1], 202)
    first_request = request_for(db, rows[0])
    response = decide(client, first_request, False, "  Different skill mix  ")
    assert response.json()["is_approved"] is False
    assert response.json()["case_status"] == "WAITING_APPROVAL"
    db.expire_all()
    assert rows[0].status == OutreachStatus.CANCELLED
    assert rows[0].response_at == DEMO_NOW
    assert first_request.reason == "Different skill mix"
    rejected = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_REJECTED)
    ).one()
    assert rejected.payload == {
        "approval_id": first_request.id,
        "staff_id": 201,
        "outreach_id": rows[0].id,
        "reason": "Different skill mix",
    }
    assert request_for(db, rows[1]).is_pending
    assert replacements(db) == []
    assert decide(client, request_for(db, rows[1])).json()["case_status"] == "RESOLVED"
    assert [r.staff_id for r in replacements(db)] == [202]


def test_rejected_without_reserve_returns_to_waiting_response(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    accept(client, rows[0], 201)
    assert (
        decide(client, request_for(db, rows[0]), False, "Choose 202").json()["case_status"]
        == "WAITING_RESPONSE"
    )
    assert replacements(db) == []
    accept(client, rows[1], 202)
    assert decide(client, request_for(db, rows[1])).json()["case_status"] == "RESOLVED"


def test_partial_assignment_survives_candidate_exhaustion(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    case, rows = two_offers(db, 104, 105)
    accept(client, rows[0], 201)
    assert decide(client, request_for(db, rows[0])).json()["case_status"] == "WAITING_RESPONSE"
    for staff_id, row in zip((202, 203), rows[1:], strict=True):
        response = client.post(
            "/demo/line-sim/respond",
            headers={"X-Demo-User": str(staff_id)},
            json={"outreach_id": row.id, "response": "REJECT"},
        )
        assert response.status_code == 200
    db.expire_all()
    assert case.status == CaseStatus.MANUAL_HANDOFF
    assert [r.staff_id for r in replacements(db)] == [201]


def foreign_case(db: Session, *, delay: timedelta):
    night = db.get(Shift, 1)
    shift = Shift(
        ward_id=1,
        patient_count=2,
        start_at=night.start_at + delay,
        end_at=night.end_at + delay,
        shift_type=ShiftType.NIGHT,
        is_active=True,
    )
    db.add(shift)
    db.flush()
    requirement = StaffingRequirement(
        shift_id=shift.id, required_staff=1, minimum_staff=1, created_at=DEMO_NOW
    )
    db.add(requirement)
    db.flush()
    db.add(
        StaffingRequirementRole(staffing_requirement_id=requirement.id, role_id=1, required_count=1)
    )
    db.flush()
    case = make_case(db, shift_id=shift.id)
    record_gap(db, case)
    items = make_plan(db, case, (201,))
    return case, offer(db, case, items[201])


@pytest.mark.parametrize(
    "delay,cancelled",
    [
        (timedelta(hours=1), True),  # overlapping
        (timedelta(hours=9), True),  # no overlap but only 1 hour rest
        (timedelta(hours=24), False),  # 16 hours rest, 8h on each calendar day
    ],
)
def test_assignment_cancels_only_unsafe_foreign_offers_and_notifies_their_cases(
    client: TestClient,
    production_seeded: Session,
    delay: timedelta,
    cancelled: bool,
) -> None:
    db = production_seeded
    own, rows = two_offers(db)
    other, other_offer = foreign_case(db, delay=delay)
    db.commit()
    accept(client, rows[0], 201)
    response = decide(client, request_for(db, rows[0]))
    assert response.json()["case_status"] == "RESOLVED"
    db.expire_all()
    assert other_offer.status == (OutreachStatus.CANCELLED if cancelled else OutreachStatus.SENT)
    assert other.status == (CaseStatus.MANUAL_HANDOFF if cancelled else CaseStatus.WAITING_RESPONSE)
    audit = db.scalars(
        select(AuditLog).where(
            AuditLog.case_id == own.id, AuditLog.action == AuditAction.ASSIGNMENT_CREATED
        )
    ).one()
    assert audit.payload["cancelled_outreach_ids"] == ([other_offer.id] if cancelled else [])
    assert other_offer.response_at is None


def test_rejection_unpauses_original_foreign_offer_without_resending(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    other, other_offer = foreign_case(db, delay=timedelta(hours=1))
    db.commit()
    accept(client, rows[0], 201)
    paused = outreach_service.list_offers(db, staff_id=201)[-1]
    assert not paused.can_accept and paused.can_reject
    decide(client, request_for(db, rows[0]), False, "Not selected")
    ready = outreach_service.list_offers(db, staff_id=201)[-1]
    assert ready.id == other_offer.id and ready.can_accept
    accept(client, other_offer, 201)
    assert request_for(db, other_offer).is_pending


def test_assignment_failure_preserves_decision_but_rolls_back_assignment(
    client: TestClient,
    production_seeded: Session,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    accept(client, rows[0], 201)
    with patch(
        "app.services.roster_service.create_replacement", side_effect=RuntimeError("storage failed")
    ):
        response = decide(client, request_for(db, rows[0]))
    assert response.json()["case_status"] == "FAILED"
    assert replacements(db) == []
    assert request_for(db, rows[0]).is_approved
    assert (
        db.scalar(select(AuditLog.id).where(AuditLog.action == AuditAction.ASSIGNMENT_CREATED))
        is None
    )


def test_head_nurse_reject_scenario_over_http(
    client: TestClient, production_seeded: Session
) -> None:
    from app.seed.scenarios import head_nurse_reject as scenario

    db = production_seeded
    scenario.seed(db)
    db.commit()
    event = client.post(
        "/events",
        headers={"X-Demo-User": str(scenario.EVENT_STAFF_ID)},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert event.status_code == 201
    rows = list(db.scalars(select(CandidateOutreach).order_by(CandidateOutreach.id)))
    accept(client, rows[0], scenario.REJECTED_STAFF_ID)
    decide(client, request_for(db, rows[0]), False, scenario.REJECTION_REASON)
    accept(client, rows[1], scenario.REPLACEMENT_STAFF_ID)
    assert decide(client, request_for(db, rows[1])).json()["case_status"] == "RESOLVED"
    actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions.index(AuditAction.APPROVAL_REJECTED) < actions.index(
        AuditAction.APPROVAL_APPROVED
    )
    assert [r.staff_id for r in replacements(db)] == [202]


@pytest.fixture
def committed_case(frozen_clock, restore_empty_database):
    with SessionLocal.begin() as db:
        load(db)
        case, items = short_case(db)
        first = offer(db, case, items[201], OutreachStatus.ACCEPTED)
        second = offer(db, case, items[202])
        safety_service.validate_accepted_candidate(db, case, outreach_id=first.id)
        case.status = CaseStatus.WAITING_APPROVAL
        request_id = request_for(db, first).id
        return_ids = (case.id, request_id, second.id)
    yield return_ids


@pytest.mark.parametrize("accept_first", [True, False, None])
def test_accept_racing_last_approval_never_overassigns_or_deadlocks(
    committed_case, accept_first
) -> None:
    case_id, request_id, offer_id = committed_case
    barrier = threading.Barrier(2, timeout=10)
    results = {}
    errors = []

    def run(kind):
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                # Delaying one request also exercises each serial outcome.
                if accept_first is not None and (kind == "accept") != accept_first:
                    threading.Event().wait(0.05)
                if kind == "approve":
                    approval_service.decide(
                        db,
                        approval_id=request_id,
                        staff_id=900,
                        role_id=2,
                        actor_id=actor_service.user_id(db, 900),
                        approved=True,
                    )
                    results[kind] = 200
                else:
                    from app.domain.enums import CandidateResponse

                    try:
                        outreach_service.record_response(
                            db,
                            staff_id=202,
                            actor_id=actor_service.user_id(db, 202),
                            outreach_id=offer_id,
                            response=CandidateResponse.ACCEPT,
                        )
                        results[kind] = 200
                    except outreach_service.OpenOfferConflictError:
                        db.rollback()
                        results[kind] = 409
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(kind,), daemon=True) for kind in ("approve", "accept")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    assert results["approve"] == 200 and results["accept"] in {200, 409}
    with SessionLocal() as db:
        assert db.get(StaffingCase, case_id).status == CaseStatus.RESOLVED
        assert [r.staff_id for r in replacements(db)] == [201]
        row = db.get(CandidateOutreach, offer_id)
        assert row.status == OutreachStatus.CANCELLED
        assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 1


@pytest.mark.parametrize("rule", ["daily", "weekly"])
def test_foreign_cancellation_checks_hour_limits_even_without_overlap_or_rest_failure(
    client: TestClient,
    production_seeded: Session,
    rule: str,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    policy = db.get(HardConstraintPolicy, 1)
    if rule == "daily":
        policy.minimum_rest_hours = 0
        delay = timedelta(hours=-14)  # Same start date, 09–17 then 23–07.
    else:
        policy.maximum_weekly_hours = 12
        delay = timedelta(hours=24)  # 16 hours rest but 16 weekly work hours.
    other, foreign = foreign_case(db, delay=delay)
    db.commit()
    accept(client, rows[0], 201)
    decide(client, request_for(db, rows[0]))
    db.expire_all()
    assert foreign.status == OutreachStatus.CANCELLED
    assert other.status == CaseStatus.MANUAL_HANDOFF


def test_rejection_skips_failed_reserve_and_promotes_next_one(
    client: TestClient,
    production_seeded: Session,
) -> None:
    from app.db.models import Staff
    from app.domain.enums import StaffStatus

    db = production_seeded
    _, rows = two_offers(db)
    for staff_id, row in zip((201, 202, 203), rows, strict=True):
        accept(client, row, staff_id)
    db.get(Staff, 202).status = StaffStatus.INACTIVE
    db.commit()
    decide(client, request_for(db, rows[0]), False, "Use a reserve")
    db.expire_all()
    assert rows[1].status == OutreachStatus.CANCELLED
    assert request_for(db, rows[2]).is_pending
    assert (
        db.scalar(
            select(ApprovalRequest.id).where(
                ApprovalRequest.candidate_item_id == rows[1].candidate_item_id
            )
        )
        is None
    )
    assert replacements(db) == []


@pytest.fixture
def committed_two_approvals(frozen_clock, restore_empty_database):
    with SessionLocal.begin() as db:
        load(db)
        case, items = short_case(db, 104, 105, status=CaseStatus.WAITING_APPROVAL)
        requests = []
        for staff_id in (201, 202):
            accepted = offer(db, case, items[staff_id], OutreachStatus.ACCEPTED)
            result = safety_service.validate_accepted_candidate(db, case, outreach_id=accepted.id)
            requests.append(result.approval.id)
        case_id = case.id
    yield case_id, requests


def test_simultaneous_per_candidate_approvals_create_two_assignments_once(committed_two_approvals):
    case_id, request_ids = committed_two_approvals
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def run(request_id):
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                approval_service.decide(
                    db,
                    approval_id=request_id,
                    staff_id=900,
                    role_id=2,
                    actor_id=actor_service.user_id(db, 900),
                    approved=True,
                )
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(request_id,), daemon=True) for request_id in request_ids
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    with SessionLocal() as db:
        assert db.get(StaffingCase, case_id).status == CaseStatus.RESOLVED
        assert [r.staff_id for r in replacements(db)] == [201, 202]
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.CASE_RESOLVED)
            )
            == 1
        )


def test_approval_restarts_lock_order_if_a_foreign_wave_commits_while_it_waits(
    committed_case,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services import hard_rule_service
    from app.workflow.handlers import contact_candidate

    case_id, request_id, _ = committed_case
    with SessionLocal.begin() as db:
        other, _ = foreign_case(db, delay=timedelta(hours=1))
        # Remove the helper's offer: this case has not sent its first wave yet.
        db.delete(
            db.scalars(select(CandidateOutreach).where(CandidateOutreach.case_id == other.id)).one()
        )
        other.status = CaseStatus.OUTREACH
        other_id = other.id
    ready = threading.Event()
    sent = threading.Event()
    real_lock = hard_rule_service.lock_staff
    approval_locks = []
    errors = []

    def lock(db, ids):
        if threading.current_thread().name == "approve-new-wave":
            approval_locks.append(1)
            if len(approval_locks) == 1:
                ready.set()
                assert sent.wait(5)
        real_lock(db, ids)

    monkeypatch.setattr(hard_rule_service, "lock_staff", lock)

    def approve():
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                approval_service.decide(
                    db,
                    approval_id=request_id,
                    staff_id=900,
                    role_id=2,
                    actor_id=actor_service.user_id(db, 900),
                    approved=True,
                )
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=approve, name="approve-new-wave", daemon=True)
    thread.start()
    try:
        assert ready.wait(5)
        with SessionLocal.begin() as db:
            other = db.get(StaffingCase, other_id)
            contact_candidate.handle(db, other)
            other.status = CaseStatus.WAITING_RESPONSE
    finally:
        sent.set()
        thread.join(15)
    assert not thread.is_alive()
    assert not errors, errors
    assert len(approval_locks) >= 2  # Released locks and reacquired in the correct order.
    with SessionLocal() as db:
        assert db.get(StaffingCase, case_id).status == CaseStatus.RESOLVED
        foreign = db.scalars(
            select(CandidateOutreach).where(CandidateOutreach.case_id == other_id)
        ).one()
        assert foreign.status == OutreachStatus.CANCELLED
        assert db.get(StaffingCase, other_id).status == CaseStatus.MANUAL_HANDOFF
        assert [r.staff_id for r in replacements(db)] == [201]


def test_skill_covering_approval_resolves_without_leaving_other_request_in_pending_list(
    client: TestClient,
    production_seeded: Session,
) -> None:
    from sqlalchemy import delete

    from app.db.models import StaffSkill

    db = production_seeded
    db.execute(delete(StaffSkill).where(StaffSkill.staff_id == 203, StaffSkill.skill_id == 1))
    db.commit()
    event = client.post(
        "/events",
        headers={"X-Demo-User": "102"},
        json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1},
    )
    assert event.status_code == 201, event.text
    case_id = event.json()["case_id"]
    by_staff = dict(
        db.execute(
            select(CandidateItem.staff_id, CandidateOutreach)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(CandidateOutreach.case_id == case_id)
        ).all()
    )
    assert set(by_staff) == {201, 202}
    accept(client, by_staff[202], 202)
    request_202 = request_for(db, by_staff[202])
    accept(client, by_staff[201], 201)
    assert len(client.get("/approvals?pending=true", headers=HEADERS).json()) == 2
    assert decide(client, request_for(db, by_staff[201])).json()["case_status"] == "RESOLVED"
    db.expire_all()
    assert by_staff[202].status == OutreachStatus.CANCELLED
    assert request_202.is_pending and request_202.is_approved is None
    assert [row.staff_id for row in replacements(db)] == [201]
    assert client.get("/approvals?pending=true", headers=HEADERS).json() == []
    assert (
        client.post(
            f"/approvals/{request_202.id}/decision", headers=HEADERS, json={"approved": True}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("approved", [True, False])
def test_approval_reason_accepts_500_characters_and_rejects_501_without_writes(
    client: TestClient,
    production_seeded: Session,
    approved: bool,
) -> None:
    db = production_seeded
    _, rows = two_offers(db)
    accept(client, rows[0], 201)
    request = request_for(db, rows[0])
    count = db.scalar(select(func.count()).select_from(AuditLog))
    response = client.post(
        f"/approvals/{request.id}/decision",
        headers=HEADERS,
        json={"approved": approved, "reason": "ก" * 501},
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count
    db.expire_all()
    assert request.is_pending and request.is_approved is None
    assert replacements(db) == []
    decide(client, request, approved, "ก" * 500)
    db.expire_all()
    assert request.reason == "ก" * 500


def test_direct_service_also_bounds_approval_reason(production_seeded: Session) -> None:
    db = production_seeded
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    row = offer(db, case, items[201], OutreachStatus.ACCEPTED)
    result = safety_service.validate_accepted_candidate(db, case, outreach_id=row.id)
    count = db.scalar(select(func.count()).select_from(AuditLog))
    with pytest.raises(approval_service.InvalidApprovalReasonError, match="at most 500"):
        approval_service.decide(
            db,
            approval_id=result.approval.id,
            staff_id=900,
            role_id=2,
            actor_id=actor_service.user_id(db, 900),
            approved=False,
            reason="x" * 501,
        )
    assert result.approval.is_pending
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count
