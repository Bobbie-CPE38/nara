"""GET /cases/{id} and GET /cases/{id}/audit (docs/workflow.md, sections 6.4 seam 9 and 9.3)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    RosterAssignment,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapRole,
    StaffingGapSkill,
    StaffingRequirement,
)
from app.domain.enums import (
    GOLDEN_PATH_AUDIT_ACTIONS,
    ActorName,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    RosterStatus,
    SolverStatus,
)
from app.main import app
from app.services import audit_service
from app.services.case_service import _OFFER_STAGES
from tests.integration import case_rows
from tests.integration.case_rows import approval
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1
LATER = DEMO_NOW + timedelta(hours=1)
RN, ICU = 1, 1


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def case(seeded: Session) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=105,
        status=EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
    )
    seeded.add(event)
    seeded.flush()
    row = StaffingCase(
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.WAITING_RESPONSE,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    seeded.add(row)
    seeded.flush()
    event.case_id = row.id
    seeded.flush()
    return row


def _actor(db: Session, name: ActorName) -> int:
    actor_id = db.scalar(select(Actor.id).where(Actor.name == name.value))
    assert actor_id is not None
    return actor_id


def _event_id(db: Session, case: StaffingCase) -> int:
    """The one event the `case` fixture linked to the case."""
    return db.scalars(select(StaffingEvent.id).where(StaffingEvent.case_id == case.id)).one()


def _log(db: Session, case: StaffingCase, action: AuditAction, actor: ActorName) -> None:
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=_actor(db, actor),
        action=action,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={"step": action.value},
    )


def _add_gap(
    db: Session, case: StaffingCase, *, headcount_gap: int, computed_at: datetime = DEMO_NOW
) -> StaffingGap:
    requirement_id = db.scalar(
        select(StaffingRequirement.id).where(StaffingRequirement.shift_id == NIGHT_SHIFT)
    )
    assert requirement_id is not None
    gap = StaffingGap(
        case_id=case.id,
        staffing_requirement_id=requirement_id,
        headcount_gap=headcount_gap,
        effective_minimum=5,
        computed_at=computed_at,
    )
    db.add(gap)
    db.flush()
    db.add_all(
        [
            StaffingGapRole(
                gap_id=gap.id,
                role_id=RN,
                required_count=5,
                current_count=5 - headcount_gap,
                gap_count=headcount_gap,
            ),
            StaffingGapSkill(
                gap_id=gap.id, skill_id=ICU, required_count=2, current_count=2, gap_count=0
            ),
        ]
    )
    db.flush()
    return gap


def _add_plan(
    db: Session, case: StaffingCase, ranked_staff: list[int], *, generated_at: datetime = DEMO_NOW
) -> list[CandidateItem]:
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.OPTIMAL,
        generated_at=generated_at,
        execution_time_ms=1,
        objective_score=Decimal(0),
        solver_version="stub",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    items = [
        CandidateItem(
            plan_id=plan.id,
            staff_id=staff_id,
            rank=rank,
            source=CandidateSource.SAME_WARD,
            proposed_shift_id=NIGHT_SHIFT,
        )
        for rank, staff_id in enumerate(ranked_staff, start=1)
    ]
    # Added in reverse so that insertion order differs from rank order
    db.add_all(reversed(items))
    db.flush()
    return items


def _add_outreach(
    db: Session,
    case: StaffingCase,
    item: CandidateItem,
    status: OutreachStatus,
    *,
    sent_at: datetime = DEMO_NOW,
) -> None:
    db.add(
        CandidateOutreach(
            case_id=case.id,
            candidate_item_id=item.id,
            channel=Channel.LINE,
            expires_at=sent_at + timedelta(seconds=300),
            sent_at=sent_at,
            status=status,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# GET /cases/{id}
# --------------------------------------------------------------------------- #
def test_case_detail_has_the_status_key_the_e2e_test_reads(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    response = client.get(f"/cases/{case.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_RESPONSE"
    assert "case_status" not in body
    assert set(body) == {
        "id",
        "status",
        "event_ids",
        "shift_id",
        "required_replacement_time",
        "created_at",
        "updated_at",
        "gap",
        "assigned_count",
        "candidates",
    }
    assert (body["id"], body["event_ids"], body["shift_id"]) == (
        case.id,
        [_event_id(seeded, case)],
        NIGHT_SHIFT,
    )


def test_case_before_assessment_has_no_gap_and_no_candidates(
    client: TestClient, case: StaffingCase
) -> None:
    body = client.get(f"/cases/{case.id}").json()

    assert body["gap"] is None
    assert body["candidates"] == []


def test_case_detail_needs_no_demo_user_header(client: TestClient, case: StaffingCase) -> None:
    assert client.get(f"/cases/{case.id}").status_code == 200


def test_case_detail_shows_the_gap_with_role_and_skill_names(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    gap = _add_gap(seeded, case, headcount_gap=1)

    body = client.get(f"/cases/{case.id}").json()

    assert body["gap"]["id"] == gap.id
    assert body["gap"]["effective_minimum"] == 5
    assert body["gap"]["headcount_gap"] == 1
    assert body["gap"]["roles"] == [
        {"id": RN, "name": "RN", "required_count": 5, "current_count": 4, "gap_count": 1}
    ]
    assert body["gap"]["skills"] == [
        {"id": ICU, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}
    ]


def test_case_detail_shows_the_latest_gap_by_id(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """The newer row has the older computed_at: sorting by time would pick the wrong gap."""
    _add_gap(seeded, case, headcount_gap=1, computed_at=LATER)
    newer = _add_gap(seeded, case, headcount_gap=2, computed_at=DEMO_NOW)

    body = client.get(f"/cases/{case.id}").json()

    assert body["gap"]["id"] == newer.id
    assert body["gap"]["headcount_gap"] == 2


def test_candidates_come_from_the_latest_plan_in_rank_order(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    # The newer plan has the older generated_at: sorting by time would pick the wrong plan
    _add_plan(seeded, case, [203, 202], generated_at=LATER)
    _add_plan(seeded, case, [201, 202, 203], generated_at=DEMO_NOW)

    body = client.get(f"/cases/{case.id}").json()

    assert [(c["rank"], c["staff_id"]) for c in body["candidates"]] == [
        (1, 201),
        (2, 202),
        (3, 203),
    ]
    first = body["candidates"][0]
    assert set(first) == {
        "candidate_item_id",
        "rank",
        "staff_id",
        "first_name",
        "last_name",
        "source",
        "outreach_status",
        "stage",
    }
    assert (first["first_name"], first["source"]) == ("Arunee", "SAME_WARD")


def test_assigned_count_is_the_approved_candidates_on_the_roster(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    _add_gap(seeded, case, headcount_gap=2)
    first, second, third = _add_plan(seeded, case, [201, 202, 203])
    assert client.get(f"/cases/{case.id}").json()["assigned_count"] == 0

    # Approved and on the roster: the only one that counts
    approval(seeded, case, first, approved=True)
    seeded.add(
        RosterAssignment(
            staff_id=201,
            shift_id=NIGHT_SHIFT,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            candidate_source=CandidateSource.SAME_WARD,
        )
    )
    # Still waiting for the head nurse, and rejected
    approval(seeded, case, second)
    approval(seeded, case, third, approved=False)
    seeded.flush()

    body = client.get(f"/cases/{case.id}").json()
    assert body["assigned_count"] == 1
    assert body["gap"]["headcount_gap"] == 2


def test_candidate_shows_its_newest_outreach_status(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, _ = _add_plan(seeded, case, [201, 202, 203])
    # The newer row has the older sent_at: sorting by time would show SENT
    _add_outreach(seeded, case, first, OutreachStatus.SENT, sent_at=LATER)
    _add_outreach(seeded, case, first, OutreachStatus.ACCEPTED, sent_at=DEMO_NOW)
    _add_outreach(seeded, case, second, OutreachStatus.SENT)

    body = client.get(f"/cases/{case.id}").json()

    assert [c["outreach_status"] for c in body["candidates"]] == ["ACCEPTED", "SENT", None]


def _stages(client: TestClient, case: StaffingCase) -> list[str]:
    body = client.get(f"/cases/{case.id}").json()
    return [c["stage"] for c in body["candidates"]]


def test_every_offer_status_but_accepted_has_a_stage() -> None:
    # A status without a stage would make GET /cases/{id} answer 500
    assert set(_OFFER_STAGES) == set(OutreachStatus) - {OutreachStatus.ACCEPTED}


def test_candidate_stage_follows_the_offer(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, _ = _add_plan(seeded, case, [201, 202, 203])
    case_rows.offer(seeded, case, first, OutreachStatus.SENT)
    case_rows.offer(seeded, case, second, OutreachStatus.REJECTED)

    assert _stages(client, case) == ["OFFER_SENT", "OFFER_REJECTED", "NOT_CONTACTED"]


def test_candidate_stage_of_closed_offers_and_a_reserve(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, third = _add_plan(seeded, case, [201, 202, 203])
    case_rows.offer(seeded, case, first, OutreachStatus.TIMEOUT)
    case_rows.offer(seeded, case, second, OutreachStatus.CANCELLED)
    case_rows.offer(seeded, case, third, OutreachStatus.ACCEPTED)

    assert _stages(client, case) == ["OFFER_TIMEOUT", "OFFER_CANCELLED", "ACCEPTED"]


def test_candidate_stage_after_acceptance(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, third = _add_plan(seeded, case, [201, 202, 203])
    case_rows.offer(seeded, case, first, OutreachStatus.ACCEPTED)
    case_rows.safety(seeded, case, first, passed=True)
    case_rows.approval(seeded, case, first)
    case_rows.offer(seeded, case, second, OutreachStatus.CANCELLED)
    case_rows.safety(seeded, case, second, passed=False)
    case_rows.approval(seeded, case, third, approved=False)

    assert _stages(client, case) == ["WAITING_APPROVAL", "SAFETY_FAILED", "APPROVAL_REJECTED"]


def test_candidate_stage_after_a_decision(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, third = _add_plan(seeded, case, [201, 202, 203])
    case_rows.assign(seeded, case, first)
    case_rows.approval(seeded, case, second, approved=True)
    case_rows.offer(seeded, case, third, OutreachStatus.CANCELLED)
    case_rows.approval(seeded, case, third)

    assert _stages(client, case) == ["ASSIGNED", "APPROVED", "OFFER_CANCELLED"]


# --------------------------------------------------------------------------- #
# GET /cases/{id}/audit
# --------------------------------------------------------------------------- #
def test_timeline_is_a_top_level_list_with_the_action_key(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    _log(seeded, case, AuditAction.CASE_OPENED, ActorName.WORKFLOW_ORCHESTRATOR)

    response = client.get(f"/cases/{case.id}/audit")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert set(body[0]) == {
        "id",
        "action",
        "actor_id",
        "actor_name",
        "actor_type",
        "entity_type",
        "entity_id",
        "payload",
        "created_at",
    }
    assert body[0]["action"] == "CASE_OPENED"
    assert (body[0]["actor_name"], body[0]["actor_type"]) == ("workflow_orchestrator", "component")
    assert body[0]["payload"] == {"step": "CASE_OPENED"}


def test_timeline_is_sorted_by_id_not_by_time_or_insertion_order(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """Seam 9. The rows go in with descending ids and ascending times, so only
    ORDER BY id returns them as 9001, 9002, 9003. Sorting by created_at, or not
    sorting at all, returns 9003 first."""
    actor_id = _actor(seeded, ActorName.WORKFLOW_ORCHESTRATOR)
    rows = [
        (9003, AuditAction.CASE_OPENED, DEMO_NOW),
        (9002, AuditAction.UNAVAILABILITY_CREATED, DEMO_NOW + timedelta(minutes=1)),
        (9001, AuditAction.EVENT_RECEIVED, DEMO_NOW + timedelta(minutes=2)),
    ]
    for row_id, action, created_at in rows:
        seeded.add(
            AuditLog(
                id=row_id,
                case_id=case.id,
                actor_id=actor_id,
                action=action,
                entity_type=EntityType.STAFFING_CASES,
                entity_id=case.id,
                payload={},
                created_at=created_at,
            )
        )
        seeded.flush()

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["id"] for entry in body] == [9001, 9002, 9003]
    assert [entry["action"] for entry in body] == [
        "EVENT_RECEIVED",
        "UNAVAILABILITY_CREATED",
        "CASE_OPENED",
    ]


def test_timeline_keeps_call_order_when_every_row_has_the_same_time(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """What a demo run looks like: the frozen clock gives every row one created_at."""
    for action in GOLDEN_PATH_AUDIT_ACTIONS:
        _log(seeded, case, action, ActorName.WORKFLOW_ORCHESTRATOR)
    assert len(set(seeded.scalars(select(AuditLog.created_at)))) == 1

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["action"] for entry in body] == [a.value for a in GOLDEN_PATH_AUDIT_ACTIONS]


def test_timeline_filters_like_the_e2e_test(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """The step 6 E2E test drops CASE_STATUS_CHANGED and compares the rest in order."""
    _log(seeded, case, AuditAction.EVENT_RECEIVED, ActorName.SYSTEM)
    _log(seeded, case, AuditAction.CASE_STATUS_CHANGED, ActorName.WORKFLOW_ORCHESTRATOR)
    _log(seeded, case, AuditAction.GAP_ASSESSED, ActorName.STAFFING_GAP_ASSESSMENT_AGENT)

    body = client.get(f"/cases/{case.id}/audit").json()

    actions = [a["action"] for a in body if a["action"] != "CASE_STATUS_CHANGED"]
    assert actions == ["EVENT_RECEIVED", "GAP_ASSESSED"]


def test_timeline_leaves_out_rows_of_other_cases_and_rows_without_a_case(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    other = StaffingCase(
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.OPEN,
        required_replacement_time=DEMO_NOW,
    )
    seeded.add(other)
    seeded.flush()
    _log(seeded, case, AuditAction.CASE_OPENED, ActorName.WORKFLOW_ORCHESTRATOR)
    _log(seeded, other, AuditAction.CASE_OPENED, ActorName.WORKFLOW_ORCHESTRATOR)
    audit_service.log(
        seeded,
        case_id=None,
        actor_id=_actor(seeded, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.EVENT_IGNORED,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=_event_id(seeded, case),
        payload={},
    )

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["entity_id"] for entry in body] == [case.id]


def _event(db: Session, *, case: StaffingCase | None, staff_id: int = 104) -> StaffingEvent:
    row = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=staff_id,
        status=EventStatus.IGNORED if case is None else EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
        case_id=None if case is None else case.id,
    )
    db.add(row)
    db.flush()
    return row


def _log_event(db: Session, event_id: int, action: AuditAction) -> None:
    audit_service.log(
        db,
        case_id=None,
        event_id=event_id,
        actor_id=_actor(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=action,
        entity_type=EntityType.STAFFING_EVENTS,
        entity_id=event_id,
        payload={},
    )


def test_case_lists_every_event_merged_into_it_by_id(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """One merge window can put several events into one case (Q36)."""
    first = _event_id(seeded, case)
    second = _event(seeded, case=case)
    _event(seeded, case=None, staff_id=103)

    body = client.get(f"/cases/{case.id}").json()

    assert body["event_ids"] == [first, second.id]
    assert "event_id" not in body


def test_timeline_includes_the_rows_of_the_events_of_the_case(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """Rows about an event have event_id and no case_id (section 3.7, Q33).

    They were written before the case existed, so by id they come before CASE_OPENED.
    """
    first = _event_id(seeded, case)
    second = _event(seeded, case=case)
    _log_event(seeded, first, AuditAction.EVENT_RECEIVED)
    _log_event(seeded, second.id, AuditAction.EVENT_RECEIVED)
    _log_event(seeded, first, AuditAction.UNAVAILABILITY_CREATED)
    _log_event(seeded, second.id, AuditAction.UNAVAILABILITY_CREATED)
    _log(seeded, case, AuditAction.CASE_OPENED, ActorName.WORKFLOW_ORCHESTRATOR)

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["action"] for entry in body] == [
        "EVENT_RECEIVED",
        "EVENT_RECEIVED",
        "UNAVAILABILITY_CREATED",
        "UNAVAILABILITY_CREATED",
        "CASE_OPENED",
    ]
    assert [entry["entity_id"] for entry in body[:4]] == [first, second.id, first, second.id]


def test_timeline_leaves_out_events_that_are_not_part_of_the_case(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """An IGNORED event of the same shift, and an event of another case."""
    other = StaffingCase(
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.OPEN,
        required_replacement_time=DEMO_NOW,
    )
    seeded.add(other)
    seeded.flush()
    ignored = _event(seeded, case=None, staff_id=103)
    of_other = _event(seeded, case=other)
    _log_event(seeded, ignored.id, AuditAction.EVENT_IGNORED)
    _log_event(seeded, of_other.id, AuditAction.EVENT_RECEIVED)
    _log_event(seeded, _event_id(seeded, case), AuditAction.EVENT_RECEIVED)

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["entity_id"] for entry in body] == [_event_id(seeded, case)]


def test_case_without_audit_rows_has_an_empty_timeline(
    client: TestClient, case: StaffingCase
) -> None:
    assert client.get(f"/cases/{case.id}/audit").json() == []


# --------------------------------------------------------------------------- #
# Times
# --------------------------------------------------------------------------- #
def test_times_are_sent_as_plus_seven_after_a_database_round_trip(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """PostgreSQL returns timestamptz in UTC. Without expire_all() the route would
    serialize the +07:00 objects this test created, and never see what the DB returns."""
    _add_gap(seeded, case, headcount_gap=1)
    _log(seeded, case, AuditAction.CASE_OPENED, ActorName.WORKFLOW_ORCHESTRATOR)
    seeded.expire_all()

    detail = client.get(f"/cases/{case.id}").json()
    timeline = client.get(f"/cases/{case.id}/audit").json()

    assert detail["created_at"] == "2026-10-09T21:00:00+07:00"
    assert detail["updated_at"] == "2026-10-09T21:00:00+07:00"
    assert detail["required_replacement_time"] == "2026-10-09T23:00:00+07:00"
    assert detail["gap"]["computed_at"] == "2026-10-09T21:00:00+07:00"
    assert timeline[0]["created_at"] == "2026-10-09T21:00:00+07:00"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/cases/999999", "/cases/999999/audit"])
def test_unknown_case_is_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "No case 999999"}


@pytest.mark.parametrize("case_id", ["abc", "0", "-1", str(2**63)])
@pytest.mark.parametrize("suffix", ["", "/audit"])
def test_case_id_outside_the_bigint_range_is_422(
    client: TestClient, case_id: str, suffix: str
) -> None:
    """Rejected by validation. 2**63 would otherwise fail inside PostgreSQL as a 500."""
    assert client.get(f"/cases/{case_id}{suffix}").status_code == 422


@pytest.mark.parametrize("suffix", ["", "/audit"])
def test_largest_bigint_case_id_reaches_the_lookup(client: TestClient, suffix: str) -> None:
    assert client.get(f"/cases/{2**63 - 1}{suffix}").status_code == 404


def test_read_routes_write_nothing(client: TestClient, seeded: Session, case: StaffingCase) -> None:
    """Looking at session.new afterwards is not enough: it is empty again after a flush."""
    pending: list[object] = []

    def record_pending(session: Session, flush_context: object, instances: object) -> None:
        pending.extend([*session.new, *session.dirty, *session.deleted])

    event.listen(seeded, "before_flush", record_pending)
    try:
        client.get(f"/cases/{case.id}")
        client.get(f"/cases/{case.id}/audit")
        seeded.flush()
    finally:
        event.remove(seeded, "before_flush", record_pending)

    assert pending == []
