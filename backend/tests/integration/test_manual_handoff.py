"""The manual exits of MANUAL_HANDOFF (docs/workflow.md, section 6.12): a head nurse
assigns people by hand (T8) or closes the case without a replacement (T9).

The seeded night shift has 101 to 105 on it. 201 (RN, ICU and BLS), 202 (RN, BLS)
and 203 (RN, ICU) are free. 900 is the head nurse of ward 1, the only ward.
"""

import threading
from collections.abc import Iterator
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    Actor,
    ApprovalRequest,
    AuditLog,
    CandidateOutreach,
    ManualAssignment,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingRequirement,
    StaffingRequirementRole,
    Ward,
)
from app.db.session import SessionLocal
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import (
    ActorType,
    AssignmentType,
    AuditAction,
    CaseStatus,
    EventType,
    OutreachStatus,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.domain.workflow.transitions import InvalidTransitionError
from app.main import app
from app.seed import load
from app.services import actor_service, approval_service, case_facts_service, handoff_service
from app.workflow import orchestrator
from tests.integration.case_rows import (
    approval,
    assign,
    make_case,
    make_plan,
    offer,
    record_gap,
    safety,
    short_case,
)
from tests.integration.conftest import DEMO_NOW

HEAD_NURSE = {"X-Demo-User": "900"}
FATIGUE_RULES = (
    HardRuleCode.INSUFFICIENT_REST,
    HardRuleCode.DAILY_HOURS_EXCEEDED,
    HardRuleCode.WEEKLY_HOURS_EXCEEDED,
    HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,
)


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    def request_db() -> Iterator[Session]:
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


def handoff_case(db: Session, *leaving: int) -> StaffingCase:
    """A night-shift case stopped at MANUAL_HANDOFF, short of what `leaving` left behind."""
    case, _ = short_case(db, *leaving, status=CaseStatus.MANUAL_HANDOFF)
    db.commit()
    return case


def assign_url(case_id: int) -> str:
    return f"/cases/{case_id}/handoff/assignments"


def post_assign(client: TestClient, case_id: int, staff_id: int, **body: object):
    return client.post(
        assign_url(case_id), headers=HEADERS_OF(body), json={"staff_id": staff_id, **body}
    )


def HEADERS_OF(body: dict[str, object]) -> dict[str, str]:
    return body.pop("headers", HEAD_NURSE)  # type: ignore[return-value]


def actions(db: Session, case_id: int) -> list[AuditAction]:
    return list(
        db.scalars(
            select(AuditLog.action)
            .where(AuditLog.action != AuditAction.CASE_OPENED)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.id)
        )
    )


def other_ward_head_nurse(db: Session) -> dict[str, str]:
    """A head nurse of a new ward, with the next free IDs."""
    ward_id = (db.scalar(select(func.max(Ward.id))) or 0) + 1
    staff_id = (db.scalar(select(func.max(Staff.id))) or 0) + 1
    db.add(Ward(id=ward_id, name="Other", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    db.add(
        Staff(
            id=staff_id,
            first_name="Other",
            last_name="Ward",
            email=f"{staff_id}@demo.local",
            password_hash="!",
            role_id=2,
            home_ward_id=ward_id,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
    db.commit()
    return {"X-Demo-User": str(staff_id)}


def foreign_offer(
    db: Session,
    staff_id: int = 201,
    *,
    delay: timedelta = timedelta(hours=1),
    expired: bool = False,
) -> tuple[StaffingCase, CandidateOutreach]:
    """A running case on another night shift that overlaps the seeded one by default,
    with a SENT offer to `staff_id`."""
    night = db.get(Shift, 1)
    assert night is not None
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
    items = make_plan(db, case, (staff_id,))
    row = offer(db, case, items[staff_id])
    if expired:
        # At the deadline exactly: only the timeout job may close it now
        row.expires_at = DEMO_NOW
    db.commit()
    return case, row


# --------------------------------------------------------------------------- #
# T8: assign by hand
# --------------------------------------------------------------------------- #
def test_assigning_a_plan_candidate_closes_a_one_person_gap(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)

    response = post_assign(client, case.id, 201, reason="  Called in by phone  ")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_status"] == "RESOLVED" and body["cancelled_outreach_ids"] == []
    db.expire_all()
    manual = db.scalars(select(ManualAssignment)).one()
    roster = db.get(RosterAssignment, manual.roster_assignment_id)
    assert roster is not None
    assert (roster.staff_id, roster.shift_id, roster.status, roster.assignment_type) == (
        201,
        case.shift_id,
        RosterStatus.ASSIGNED,
        AssignmentType.REPLACEMENT,
    )
    assert (manual.case_id, manual.assigned_by, manual.reason) == (
        case.id,
        900,
        "Called in by phone",
    )
    # Nobody answers and nobody approves (R2-Q15, R2-Q16)
    assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 0
    assert actions(db, case.id) == [
        AuditAction.HANDOVER_GENERATED,
        AuditAction.MANUAL_ASSIGNMENT_CREATED,
        AuditAction.CASE_RESOLVED,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    created = db.scalars(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.MANUAL_ASSIGNMENT_CREATED)
    ).one()
    assert created.actor_id == actor_service.user_id(db, 900)
    assert created.payload == {
        "assignment_id": roster.id,
        "manual_assignment_id": manual.id,
        "staff_id": 201,
        "assignment_type": "REPLACEMENT",
        "reason": "Called in by phone",
        "cancelled_outreach_ids": [],
    }
    changed = db.scalars(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.CASE_STATUS_CHANGED)
    ).one()
    assert changed.payload == {"from": "MANUAL_HANDOFF", "to": "RESOLVED"}


def test_a_person_outside_the_plan_counts_toward_the_gap(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = make_case(db, CaseStatus.MANUAL_HANDOFF)
    from tests.integration.case_rows import cancel_roster

    cancel_roster(db, 105)
    record_gap(db, case)
    make_plan(db, case, (201,))
    db.commit()

    response = post_assign(client, case.id, 203)

    assert response.json()["case_status"] == "RESOLVED"
    detail = client.get(f"/cases/{case.id}").json()
    assert detail["assigned_count"] == 1


def test_a_two_person_gap_stays_handed_off_until_the_second_assignment(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db, 104, 105)

    first = post_assign(client, case.id, 201)
    assert first.json()["case_status"] == "MANUAL_HANDOFF"
    assert client.get(f"/cases/{case.id}").json()["assigned_count"] == 1

    second = post_assign(client, case.id, 202)
    assert second.json()["case_status"] == "RESOLVED"


def test_an_approved_replacement_and_a_manual_one_close_the_gap_together(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case, items = short_case(db, 104, 105, status=CaseStatus.MANUAL_HANDOFF)
    assign(db, case, items[201])
    db.commit()

    response = post_assign(client, case.id, 202)

    assert response.json()["case_status"] == "RESOLVED"
    resolved = db.scalars(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.CASE_RESOLVED)
    ).one()
    assert len(resolved.payload["assignment_ids"]) == 2


def test_a_full_headcount_with_a_skill_still_short_does_not_resolve(
    client: TestClient, production_seeded: Session
) -> None:
    """102 leaves: one RN short, and ICU is short too. 202 has no ICU."""
    db = production_seeded
    case = handoff_case(db, 102)

    covered_headcount = post_assign(client, case.id, 202)
    assert covered_headcount.json()["case_status"] == "MANUAL_HANDOFF"

    covered_skill = post_assign(client, case.id, 203)
    assert covered_skill.json()["case_status"] == "RESOLVED"


def test_a_cancelled_manual_assignment_stops_counting(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db, 104, 105)
    assert post_assign(client, case.id, 201).status_code == 200
    db.expire_all()
    roster = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
        )
    ).one()
    roster.status = RosterStatus.CANCELLED
    db.commit()

    assert case_facts_service.assigned_staff_ids(db, case.id) == set()
    assert client.get(f"/cases/{case.id}").json()["assigned_count"] == 0


def test_a_failed_notification_does_not_turn_the_committed_assignment_into_an_error(
    client: TestClient, production_seeded: Session
) -> None:
    """The other cases are told after the commit. If that breaks, the head nurse
    still gets the result of what was committed (the rule of PR T)."""
    db = production_seeded
    case = handoff_case(db)

    with patch.object(
        handoff_service.outreach_service,
        "recompute_affected_cases",
        side_effect=RuntimeError("notification down"),
    ):
        response = post_assign(client, case.id, 201)

    assert response.status_code == 200, response.text
    assert response.json()["case_status"] == "RESOLVED"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ManualAssignment)) == 1
    assert actions(db, case.id) == [
        AuditAction.HANDOVER_GENERATED,
        AuditAction.MANUAL_ASSIGNMENT_CREATED,
        AuditAction.CASE_RESOLVED,
        AuditAction.CASE_STATUS_CHANGED,
    ]


def test_the_case_list_reads_coverage_in_a_fixed_number_of_queries(
    client: TestClient, production_seeded: Session
) -> None:
    """The page polls this list: the queries must not grow with the number of cases."""
    from sqlalchemy import event

    db = production_seeded
    for _ in range(3):
        handoff_case(db)

    def count_queries() -> int:
        statements: list[str] = []

        def record(*args: object) -> None:
            statements.append(str(args[2]))

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            assert client.get("/cases?status=MANUAL_HANDOFF", headers=HEAD_NURSE).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    three = count_queries()
    handoff_case(db)
    handoff_case(db)
    assert count_queries() == three


# --------------------------------------------------------------------------- #
# Hard Rules: no override (R2-Q14)
# --------------------------------------------------------------------------- #
def _assert_nothing_written(db: Session, case: StaffingCase) -> None:
    db.expire_all()
    assert db.get(StaffingCase, case.id).status == CaseStatus.MANUAL_HANDOFF  # type: ignore[union-attr]
    assert db.scalar(select(func.count()).select_from(ManualAssignment)) == 0
    assert actions(db, case.id) == []


def test_a_person_already_on_the_shift_is_refused_whatever_the_reason(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    rows_before = db.scalar(select(func.count()).select_from(RosterAssignment))

    response = post_assign(client, case.id, 101, reason="Urgent, I accept the risk")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "HARD_RULES_FAILED"
    assert "ALREADY_ON_SHIFT" in detail["failed_rules"]
    _assert_nothing_written(db, case)
    assert db.scalar(select(func.count()).select_from(RosterAssignment)) == rows_before


@pytest.mark.parametrize("rule", FATIGUE_RULES)
def test_each_fatigue_rule_refuses_the_assignment(
    client: TestClient, production_seeded: Session, rule: HardRuleCode
) -> None:
    """The four fatigue rules have no override either. The rule itself is tested in
    test_hard_rules; here the result of the shared checker is forced."""
    db = production_seeded
    case = handoff_case(db)
    forced = {201: SimpleNamespace(result=SimpleNamespace(failed_rules=(rule,)))}

    with patch.object(handoff_service.hard_rule_service, "check_staff", return_value=forced):
        response = post_assign(client, case.id, 201, reason="Short of staff tonight")

    assert response.status_code == 409
    assert response.json()["detail"]["failed_rules"] == [rule.value]
    _assert_nothing_written(db, case)


@pytest.mark.parametrize(
    "who,expected",
    [("105", 403), ("other_ward", 403)],
)
def test_only_a_head_nurse_of_the_shifts_ward_may_assign(
    client: TestClient, production_seeded: Session, who: str, expected: int
) -> None:
    db = production_seeded
    case = handoff_case(db)
    headers = other_ward_head_nurse(db) if who == "other_ward" else {"X-Demo-User": who}

    response = post_assign(client, case.id, 201, headers=headers)

    assert response.status_code == expected
    _assert_nothing_written(db, case)


def test_refusals_and_their_order(client: TestClient, production_seeded: Session) -> None:
    db = production_seeded
    running = handoff_case(db)
    running.status = CaseStatus.WAITING_RESPONSE
    db.commit()
    assert post_assign(client, 9_000_000, 201).status_code == 404
    assert post_assign(client, running.id, 201).status_code == 409

    running.status = CaseStatus.MANUAL_HANDOFF
    inactive = db.get(Staff, 203)
    assert inactive is not None
    inactive.status = StaffStatus.INACTIVE
    db.commit()
    # Not selectable: inactive, unknown, or of another ward
    assert post_assign(client, running.id, 203).status_code == 422
    assert post_assign(client, running.id, 9_000_000).status_code == 422
    assert post_assign(client, running.id, 201, reason="x" * 501).status_code == 422
    _assert_nothing_written(db, running)


# --------------------------------------------------------------------------- #
# Offers of the person on other cases (R2-Q46, R2-Q56)
# --------------------------------------------------------------------------- #
def test_a_clashing_offer_elsewhere_needs_confirmation_first(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    other, row = foreign_offer(db)

    response = post_assign(client, case.id, 201)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONFLICTING_OFFERS"
    assert response.json()["detail"]["case_ids"] == [other.id]
    _assert_nothing_written(db, case)
    db.refresh(row)
    assert row.status is OutreachStatus.SENT


def test_confirming_cancels_the_clashing_offer_and_says_why_in_its_case(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    other, row = foreign_offer(db)

    response = post_assign(client, case.id, 201, confirm_conflicts=True)

    assert response.status_code == 200, response.text
    assert response.json()["cancelled_outreach_ids"] == [row.id]
    db.expire_all()
    assert db.get(CandidateOutreach, row.id).status is OutreachStatus.CANCELLED  # type: ignore[union-attr]
    lost = db.scalars(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(
            AuditLog.case_id == other.id,
            AuditLog.action == AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT,
        )
    ).one()
    roster_id = response.json()["assignment_id"]
    assert lost.payload == {
        "cancelled_outreach_id": row.id,
        "staff_id": 201,
        "by_case_id": case.id,
        "assignment_id": roster_id,
        "source": "MANUAL_ASSIGNMENT",
    }
    assert lost.actor_id == actor_service.user_id(db, 900)
    offers = client.get("/demo/line-sim/offers?staff_id=201", headers={"X-Demo-User": "201"})
    cancelled = [item for item in offers.json() if item["id"] == row.id]
    assert cancelled[0]["cancellation_reason"] == "CONFLICTING_ASSIGNMENT"


def test_an_overdue_offer_is_left_for_the_timeout_job(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    other, row = foreign_offer(db, expired=True)

    # No confirmation needed: the overdue offer is not counted as a clash
    response = post_assign(client, case.id, 201)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(CandidateOutreach, row.id).status is OutreachStatus.SENT  # type: ignore[union-attr]
    assert AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT not in actions(db, other.id)


def _pending_request(db: Session) -> ApprovalRequest:
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    offer(db, case, items[201], OutreachStatus.ACCEPTED)
    safety(db, case, items[201], passed=True)
    return approval(db, case, items[201])


@pytest.mark.parametrize("expired", [False, True])
def test_an_approval_uses_the_same_rules_for_offers_elsewhere(
    client: TestClient, production_seeded: Session, expired: bool
) -> None:
    db = production_seeded
    request = _pending_request(db)
    other, row = foreign_offer(db, expired=expired)

    response = client.post(
        f"/approvals/{request.id}/decision", headers=HEAD_NURSE, json={"approved": True}
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    status = db.get(CandidateOutreach, row.id).status  # type: ignore[union-attr]
    lost = actions(db, other.id).count(AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT)
    if expired:
        assert status is OutreachStatus.SENT and lost == 0
    else:
        assert status is OutreachStatus.CANCELLED and lost == 1
        audit = db.scalars(
            select(AuditLog)
            .where(AuditLog.action != AuditAction.CASE_OPENED)
            .where(AuditLog.action == AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT)
        ).one()
        assert audit.payload["source"] == "APPROVAL"
        offers = client.get("/demo/line-sim/offers?staff_id=201", headers={"X-Demo-User": "201"})
        reason = [item for item in offers.json() if item["id"] == row.id][0]
        assert reason["cancellation_reason"] == "CONFLICTING_ASSIGNMENT"


# --------------------------------------------------------------------------- #
# T9: close without a replacement
# --------------------------------------------------------------------------- #
def test_closing_needs_a_reason_then_ends_the_case(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    url = f"/cases/{case.id}/handoff/close"

    for reason in (None, "   ", "x" * 501):
        refused = client.post(url, headers=HEAD_NURSE, json={"reason": reason})
        assert refused.status_code == 422
    _assert_nothing_written(db, case)

    closed = client.post(url, headers=HEAD_NURSE, json={"reason": "  Nobody can come in  "})

    assert closed.json() == {"case_id": case.id, "case_status": "UNRESOLVED"}
    audit = db.scalars(
        select(AuditLog)
        .where(AuditLog.action != AuditAction.CASE_OPENED)
        .where(AuditLog.action == AuditAction.CASE_CLOSED_UNRESOLVED)
    ).one()
    assert audit.payload == {"reason": "Nobody can come in", "closed_by": "HEAD_NURSE"}
    assert audit.actor_id == actor_service.user_id(db, 900)
    # A closed case has no exit left
    assert client.post(url, headers=HEAD_NURSE, json={"reason": "again"}).status_code == 409
    assert post_assign(client, case.id, 201).status_code == 409


def test_closing_keeps_roster_rows_already_assigned_by_hand(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db, 104, 105)
    assert post_assign(client, case.id, 201).status_code == 200

    client.post(f"/cases/{case.id}/handoff/close", headers=HEAD_NURSE, json={"reason": "Enough"})

    db.expire_all()
    assert db.get(StaffingCase, case.id).status is CaseStatus.UNRESOLVED  # type: ignore[union-attr]
    roster = db.scalars(select(RosterAssignment).where(RosterAssignment.staff_id == 201)).one()
    assert roster.status is RosterStatus.ASSIGNED


# --------------------------------------------------------------------------- #
# Lists
# --------------------------------------------------------------------------- #
def test_the_case_list_shows_the_callers_ward_only(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    stopped = handoff_case(db)
    failed = make_case(db, CaseStatus.FAILED)
    make_case(db, CaseStatus.WAITING_RESPONSE)
    db.commit()

    rows = client.get("/cases?status=MANUAL_HANDOFF,FAILED", headers=HEAD_NURSE).json()

    assert [(row["id"], row["status"], row["can_manage"]) for row in rows] == [
        (stopped.id, "MANUAL_HANDOFF", True),
        (failed.id, "FAILED", False),
    ]
    assert rows[0]["headcount_gap"] == 1 and rows[1]["headcount_gap"] is None
    assert (
        client.get("/cases?status=MANUAL_HANDOFF", headers=other_ward_head_nurse(db)).json() == []
    )
    assert (
        client.get("/cases?status=MANUAL_HANDOFF", headers={"X-Demo-User": "105"}).status_code
        == 403
    )
    assert client.get("/cases", headers=HEAD_NURSE).status_code == 422
    assert client.get("/cases?status=NOPE", headers=HEAD_NURSE).status_code == 422


def test_the_candidate_list_shows_what_blocks_each_person(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    case = handoff_case(db)
    other, _ = foreign_offer(db)

    rows = {
        row["staff_id"]: row
        for row in client.get(f"/cases/{case.id}/handoff/candidates", headers=HEAD_NURSE).json()
    }

    # 105 left the shift, so it is free again; 101 is still on it
    assert "ALREADY_ON_SHIFT" in rows[101]["blocking_rules"]
    assert rows[201]["blocking_rules"] == []
    assert rows[201]["other_case_ids"] == [other.id]
    assert rows[202]["other_case_ids"] == []
    assert (
        client.get(
            f"/cases/{case.id}/handoff/candidates", headers={"X-Demo-User": "105"}
        ).status_code
        == 403
    )


# --------------------------------------------------------------------------- #
# Orchestrator entry
# --------------------------------------------------------------------------- #
def test_leave_handoff_takes_only_the_two_exits(production_seeded: Session) -> None:
    db = production_seeded
    running = make_case(db, CaseStatus.WAITING_RESPONSE)
    stopped = make_case(db, CaseStatus.MANUAL_HANDOFF)
    with pytest.raises(InvalidTransitionError):
        orchestrator.leave_handoff(db, running.id, CaseStatus.RESOLVED)
    with pytest.raises(InvalidTransitionError):
        orchestrator.leave_handoff(db, stopped.id, CaseStatus.FAILED)
    with pytest.raises(InvalidTransitionError):
        orchestrator.leave_handoff(db, stopped.id, CaseStatus.OUTREACH)
    assert orchestrator.leave_handoff(db, stopped.id, CaseStatus.UNRESOLVED).status is (
        CaseStatus.UNRESOLVED
    )


# --------------------------------------------------------------------------- #
# Two connections
# --------------------------------------------------------------------------- #
@pytest.fixture
def committed_race(frozen_clock, restore_empty_database):
    """A MANUAL_HANDOFF case, and another case whose approval of 201 is pending.

    Both are for the seeded night shift, so only one of them can give it to 201.
    """
    with SessionLocal.begin() as db:
        load(db)
        handoff, _ = short_case(db, 105, status=CaseStatus.MANUAL_HANDOFF)
        other = make_case(db, CaseStatus.WAITING_APPROVAL)
        record_gap(db, other)
        items = make_plan(db, other, (201,))
        offer(db, other, items[201], OutreachStatus.ACCEPTED)
        safety(db, other, items[201], passed=True)
        request = approval(db, other, items[201])
        ids = (handoff.id, other.id, request.id)
    yield ids


@pytest.mark.parametrize("assign_first", [True, False, None])
def test_manual_assignment_racing_an_approval_never_gives_two_shifts(
    committed_race, assign_first
) -> None:
    handoff_id, other_id, request_id = committed_race
    barrier = threading.Barrier(2, timeout=10)
    results: dict[str, int] = {}
    errors: list[Exception] = []

    def run(kind: str) -> None:
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                if assign_first is not None and (kind == "assign") != assign_first:
                    threading.Event().wait(0.05)
                if kind == "assign":
                    try:
                        handoff_service.assign(
                            db,
                            case_id=handoff_id,
                            staff_id=201,
                            assigned_by=900,
                            role_id=2,
                            home_ward_id=1,
                            actor_id=actor_service.user_id(db, 900),
                            confirm_conflicts=True,
                        )
                        results[kind] = 200
                    except handoff_service.HardRulesFailedError:
                        db.rollback()
                        results[kind] = 409
                else:
                    try:
                        approval_service.decide(
                            db,
                            approval_id=request_id,
                            staff_id=900,
                            role_id=2,
                            home_ward_id=1,
                            actor_id=actor_service.user_id(db, 900),
                            approved=True,
                        )
                        results[kind] = 200
                    # Assignment first: the offer is cancelled, and with nobody left
                    # the other case stops, so the decision is refused either way
                    except (
                        approval_service.ApprovalOfferConflictError,
                        approval_service.ApprovalNotPendingError,
                    ):
                        db.rollback()
                        results[kind] = 409
        except Exception as error:  # noqa: BLE001 - reported below
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(kind,), daemon=True) for kind in ("assign", "approve")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    with SessionLocal() as db:
        on_shift = db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.staff_id == 201,
                RosterAssignment.shift_id == 1,
                RosterAssignment.status == RosterStatus.ASSIGNED,
            )
        ).all()
        assert len(on_shift) == 1
        handoff = db.get(StaffingCase, handoff_id)
        assert handoff is not None
        if results.get("assign") == 200:
            assert handoff.status is CaseStatus.RESOLVED
        else:
            assert handoff.status is CaseStatus.MANUAL_HANDOFF


@pytest.fixture
def committed_handoff(frozen_clock, restore_empty_database):
    with SessionLocal.begin() as db:
        load(db)
        shift = db.get(Shift, 1)
        assert shift is not None
        # The successor window closes at once
        shift.merge_window_seconds = 0
        handoff, _ = short_case(db, 105, status=CaseStatus.MANUAL_HANDOFF)
        handoff_id = handoff.id
    yield handoff_id


def test_manual_assignment_racing_a_successor_case_ends_in_one_consistent_state(
    committed_handoff,
) -> None:
    """Either the head nurse staffs the old case first, or the new case closes it first."""
    from app.services import event_service

    handoff_id = committed_handoff
    barrier = threading.Barrier(2, timeout=10)
    results: dict[str, object] = {}
    errors: list[Exception] = []

    def run(kind: str) -> None:
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait()
                if kind == "assign":
                    try:
                        handoff_service.assign(
                            db,
                            case_id=handoff_id,
                            staff_id=201,
                            assigned_by=900,
                            role_id=2,
                            home_ward_id=1,
                            actor_id=actor_service.user_id(db, 900),
                        )
                        results[kind] = "assigned"
                    except handoff_service.HandoffCaseStateError:
                        db.rollback()
                        results[kind] = "closed first"
                else:
                    event_service.receive_event(
                        db,
                        event_type=EventType.STAFF_UNAVAILABLE,
                        shift_id=1,
                        staff_id=104,
                        actor_id=actor_service.user_id(db, 104),
                        role_id=1,
                    )
                    results[kind] = "event"
        except Exception as error:  # noqa: BLE001 - reported below
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(kind,), daemon=True) for kind in ("assign", "event")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    with SessionLocal() as db:
        handoff = db.get(StaffingCase, handoff_id)
        assert handoff is not None
        assert handoff.status in {CaseStatus.RESOLVED, CaseStatus.UNRESOLVED}
        manual = db.scalar(select(func.count()).select_from(ManualAssignment))
        if results["assign"] == "assigned":
            assert manual == 1
        else:
            assert handoff.status is CaseStatus.UNRESOLVED and manual == 0
