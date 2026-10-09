"""GET /cases/{id} and GET /cases/{id}/audit (docs/workflow.md, sections 6.4 seam 9 and 9.3)."""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
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
    AuditAction,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.main import app
from app.services import audit_service
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1
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
    )
    seeded.add(event)
    seeded.flush()
    row = StaffingCase(
        event_id=event.id,
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.WAITING_RESPONSE,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    seeded.add(row)
    seeded.flush()
    return row


def _actor(db: Session, name: ActorName) -> int:
    actor_id = db.scalar(select(Actor.id).where(Actor.name == name.value))
    assert actor_id is not None
    return actor_id


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


def _add_gap(db: Session, case: StaffingCase, *, headcount_gap: int) -> StaffingGap:
    requirement_id = db.scalar(
        select(StaffingRequirement.id).where(StaffingRequirement.shift_id == NIGHT_SHIFT)
    )
    assert requirement_id is not None
    gap = StaffingGap(
        case_id=case.id,
        staffing_requirement_id=requirement_id,
        headcount_gap=headcount_gap,
        computed_at=DEMO_NOW,
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


def _add_plan(db: Session, case: StaffingCase, ranked_staff: list[int]) -> list[CandidateItem]:
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
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
    db: Session, case: StaffingCase, item: CandidateItem, status: OutreachStatus
) -> None:
    db.add(
        CandidateOutreach(
            case_id=case.id,
            candidate_item_id=item.id,
            channel=Channel.LINE,
            sent_at=DEMO_NOW,
            status=status,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# GET /cases/{id}
# --------------------------------------------------------------------------- #
def test_case_detail_has_the_status_key_the_e2e_test_reads(
    client: TestClient, case: StaffingCase
) -> None:
    response = client.get(f"/cases/{case.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_RESPONSE"
    assert "case_status" not in body
    assert set(body) == {
        "id",
        "status",
        "event_id",
        "shift_id",
        "required_replacement_time",
        "created_at",
        "updated_at",
        "gap",
        "candidates",
    }
    assert (body["id"], body["event_id"], body["shift_id"]) == (case.id, case.event_id, NIGHT_SHIFT)


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
    """Both gaps carry the same frozen computed_at, so only the id tells them apart."""
    _add_gap(seeded, case, headcount_gap=1)
    newer = _add_gap(seeded, case, headcount_gap=2)

    body = client.get(f"/cases/{case.id}").json()

    assert body["gap"]["id"] == newer.id
    assert body["gap"]["headcount_gap"] == 2


def test_candidates_come_from_the_latest_plan_in_rank_order(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    _add_plan(seeded, case, [203, 202])
    _add_plan(seeded, case, [201, 202, 203])

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
    }
    assert (first["first_name"], first["source"]) == ("Arunee", "SAME_WARD")


def test_candidate_shows_its_newest_outreach_status(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    first, second, _ = _add_plan(seeded, case, [201, 202, 203])
    _add_outreach(seeded, case, first, OutreachStatus.SENT)
    _add_outreach(seeded, case, first, OutreachStatus.ACCEPTED)
    _add_outreach(seeded, case, second, OutreachStatus.SENT)

    body = client.get(f"/cases/{case.id}").json()

    assert [c["outreach_status"] for c in body["candidates"]] == ["ACCEPTED", "SENT", None]


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


def test_timeline_is_sorted_by_id_when_every_row_has_the_same_time(
    client: TestClient, seeded: Session, case: StaffingCase
) -> None:
    """Seam 9: the frozen demo clock gives every row the same created_at."""
    for action in GOLDEN_PATH_AUDIT_ACTIONS:
        _log(seeded, case, action, ActorName.WORKFLOW_ORCHESTRATOR)
    assert len(set(seeded.scalars(select(AuditLog.created_at)))) == 1

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["action"] for entry in body] == [a.value for a in GOLDEN_PATH_AUDIT_ACTIONS]
    assert [entry["id"] for entry in body] == sorted(entry["id"] for entry in body)


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
        event_id=case.event_id,
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
        entity_id=case.event_id,
        payload={},
    )

    body = client.get(f"/cases/{case.id}/audit").json()

    assert [entry["entity_id"] for entry in body] == [case.id]


def test_case_without_audit_rows_has_an_empty_timeline(
    client: TestClient, case: StaffingCase
) -> None:
    assert client.get(f"/cases/{case.id}/audit").json() == []


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/cases/999999", "/cases/999999/audit"])
def test_unknown_case_is_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "No case 999999"}


@pytest.mark.parametrize("path", ["/cases/abc", "/cases/abc/audit"])
def test_case_id_that_is_not_a_number_is_422(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 422


def test_read_routes_write_nothing(client: TestClient, seeded: Session, case: StaffingCase) -> None:
    client.get(f"/cases/{case.id}")
    client.get(f"/cases/{case.id}/audit")

    assert not seeded.new
    assert not seeded.dirty
