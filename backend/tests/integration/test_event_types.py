"""The three event types a head nurse reports (docs/workflow.md, section 3.4).

On the Golden Case shifts, whose window is 0 seconds: the event is applied in
the request that reports it. 900 is the head nurse.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffUnavailability,
)
from app.domain.enums import AuditAction, EntityType, RosterStatus
from app.main import app
from app.services import actor_service

NIGHT_SHIFT, DAY_SHIFT = 1, 2
RN, HEAD_NURSE_ROLE = 1, 2
ICU, BLS = 1, 2
AS_HEAD_NURSE = {"X-Demo-User": "900"}
AS_105 = {"X-Demo-User": "105"}
CANCEL_104 = {
    "event_type": "ASSIGNMENT_CANCELLED",
    "shift_id": NIGHT_SHIFT,
    "staff_id": 104,
    "reason": "Moved to another ward",
}
SURGE_TO_12 = {"event_type": "PATIENT_SURGE", "shift_id": NIGHT_SHIFT, "patient_count": 12}
THREE_ICU = {
    "event_type": "REQUIREMENT_CHANGED",
    "shift_id": NIGHT_SHIFT,
    "skills": [{"skill_id": ICU, "required_count": 3}],
}
WRITTEN_TABLES = (StaffingEvent, StaffUnavailability, StaffingCase, AuditLog)

pytestmark = pytest.mark.usefixtures("stub_handlers")


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _row_counts(db: Session) -> list[int | None]:
    return [db.scalar(select(func.count()).select_from(model)) for model in WRITTEN_TABLES]


def _audit(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action != AuditAction.CASE_STATUS_CHANGED)
            .order_by(AuditLog.id)
        )
    )


def _requirement(db: Session, shift_id: int = NIGHT_SHIFT) -> StaffingRequirement:
    db.expire_all()
    return db.scalars(
        select(StaffingRequirement).where(StaffingRequirement.shift_id == shift_id)
    ).one()


def _roster(db: Session, shift_id: int = NIGHT_SHIFT) -> dict[int, RosterStatus]:
    db.expire_all()
    rows = db.execute(
        select(RosterAssignment.staff_id, RosterAssignment.status).where(
            RosterAssignment.shift_id == shift_id
        )
    )
    return {staff_id: status for staff_id, status in rows}


# --------------------------------------------------------------------------- #
# ASSIGNMENT_CANCELLED
# --------------------------------------------------------------------------- #
def test_cancelling_an_assignment_cancels_the_roster_row_and_opens_a_case(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/events", headers=AS_HEAD_NURSE, json=CANCEL_104)

    assert response.status_code == 201
    body = response.json()
    assert (body["event_status"], body["case_status"]) == ("PROCESSED", "WAITING_RESPONSE")
    assert _roster(seeded)[104] is RosterStatus.CANCELLED
    # A cancelled assignment is not a leave
    assert seeded.scalar(select(func.count()).select_from(StaffUnavailability)) == 0
    event = seeded.get(StaffingEvent, body["event_id"])
    assert event is not None
    # staff_id is the person the event is about. The reporter is in the payload
    assert event.staff_id == 104
    assert event.payload == {"reason": "Moved to another ward", "reported_by": 900}


def test_cancelling_an_assignment_is_audited_as_the_head_nurse(
    client: TestClient, seeded: Session
) -> None:
    body = client.post("/events", headers=AS_HEAD_NURSE, json=CANCEL_104).json()

    received, cancelled, opened = _audit(seeded)
    head_nurse = actor_service.user_id(seeded, 900)
    assert (received.action, received.actor_id, received.event_id) == (
        AuditAction.EVENT_RECEIVED,
        head_nurse,
        body["event_id"],
    )
    assert received.payload == {
        "event_type": "ASSIGNMENT_CANCELLED",
        "shift_id": NIGHT_SHIFT,
        "staff_id": 104,
    }
    roster_id = seeded.scalars(
        select(RosterAssignment.id).where(
            RosterAssignment.staff_id == 104, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()
    assert (cancelled.action, cancelled.actor_id) == (AuditAction.ASSIGNMENT_CANCELLED, head_nurse)
    assert (cancelled.event_id, cancelled.case_id) == (body["event_id"], None)
    assert (cancelled.entity_type, cancelled.entity_id) == (EntityType.ROSTER_ASSIGNMENT, roster_id)
    assert cancelled.payload == {
        "assignment_id": roster_id,
        "staff_id": 104,
        "reason": "Moved to another ward",
    }
    assert opened.action is AuditAction.CASE_OPENED


def test_reason_is_stored_without_surrounding_spaces(client: TestClient, seeded: Session) -> None:
    body = client.post(
        "/events", headers=AS_HEAD_NURSE, json=CANCEL_104 | {"reason": "  Double booked  "}
    ).json()

    event = seeded.get(StaffingEvent, body["event_id"])
    assert event is not None
    assert event.payload["reason"] == "Double booked"


# --------------------------------------------------------------------------- #
# PATIENT_SURGE
# --------------------------------------------------------------------------- #
def test_patient_surge_updates_the_shift_and_the_workload_target(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/events", headers=AS_HEAD_NURSE, json=SURGE_TO_12)

    assert response.status_code == 201
    body = response.json()
    assert (body["event_status"], body["case_status"]) == ("PROCESSED", "WAITING_RESPONSE")
    seeded.expire_all()
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert shift.patient_count == 12
    # ceil(12 / 2), updated in the row the shift already had
    requirement = _requirement(seeded)
    assert (requirement.id, requirement.required_staff, requirement.minimum_staff) == (1, 6, 4)
    assert (
        seeded.scalar(
            select(func.count())
            .select_from(StaffingRequirement)
            .where(StaffingRequirement.shift_id == requirement.shift_id)
        )
        == 1
    )
    event = seeded.get(StaffingEvent, body["event_id"])
    assert event is not None
    assert (event.staff_id, event.payload) == (None, {"patient_count": 12, "reported_by": 900})
    # Nobody left: the whole roster is still there
    assert set(_roster(seeded).values()) == {RosterStatus.ASSIGNED}


def test_patient_surge_audit_has_the_old_and_the_new_count(
    client: TestClient, seeded: Session
) -> None:
    body = client.post("/events", headers=AS_HEAD_NURSE, json=SURGE_TO_12).json()

    received, updated, opened = _audit(seeded)
    assert received.payload == {
        "event_type": "PATIENT_SURGE",
        "shift_id": NIGHT_SHIFT,
        "staff_id": None,
    }
    assert (updated.action, updated.actor_id) == (
        AuditAction.PATIENT_COUNT_UPDATED,
        actor_service.user_id(seeded, 900),
    )
    assert (updated.event_id, updated.case_id) == (body["event_id"], None)
    assert (updated.entity_type, updated.entity_id) == (EntityType.SHIFT, NIGHT_SHIFT)
    assert updated.payload == {
        "shift_id": NIGHT_SHIFT,
        "old_patient_count": 10,
        "new_patient_count": 12,
    }
    # 6 needed, 5 on the roster
    assert opened.payload["headcount_gap"] == 1


def test_lower_patient_count_is_stored_but_opens_no_case(
    client: TestClient, seeded: Session
) -> None:
    """The count is a total, so it can go down. That never passes the threshold,
    and a window without a passing event leaves required_staff as it was (section 3.6)."""
    body = client.post(
        "/events", headers=AS_HEAD_NURSE, json=SURGE_TO_12 | {"patient_count": 8}
    ).json()

    assert (body["event_status"], body["case_id"]) == ("IGNORED", None)
    seeded.expire_all()
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert shift.patient_count == 8
    assert _requirement(seeded).required_staff == 5
    assert [row.action for row in _audit(seeded)] == [
        AuditAction.EVENT_RECEIVED,
        AuditAction.PATIENT_COUNT_UPDATED,
        AuditAction.EVENT_IGNORED,
    ]


def test_patient_count_of_zero_is_a_valid_total(client: TestClient, seeded: Session) -> None:
    response = client.post(
        "/events", headers=AS_HEAD_NURSE, json=SURGE_TO_12 | {"patient_count": 0}
    )

    assert response.status_code == 201
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert shift.patient_count == 0


# --------------------------------------------------------------------------- #
# REQUIREMENT_CHANGED
# --------------------------------------------------------------------------- #
def test_requirement_change_updates_the_row_in_place_and_opens_a_case(
    client: TestClient, seeded: Session
) -> None:
    """Only 101 and 102 hold ICU: asking for three leaves the shift one short."""
    before = seeded.scalar(select(func.count()).select_from(StaffingRequirementSkill))

    response = client.post("/events", headers=AS_HEAD_NURSE, json=THREE_ICU)

    assert response.status_code == 201
    body = response.json()
    assert (body["event_status"], body["case_status"]) == ("PROCESSED", "WAITING_RESPONSE")
    seeded.expire_all()
    row = seeded.get(StaffingRequirementSkill, (1, ICU))
    assert row is not None
    assert row.required_count == 3
    assert seeded.scalar(select(func.count()).select_from(StaffingRequirementSkill)) == before
    # The headcount target is not part of this event type
    requirement = _requirement(seeded)
    assert (requirement.required_staff, requirement.minimum_staff) == (5, 4)
    event = seeded.get(StaffingEvent, body["event_id"])
    assert event is not None
    assert event.payload == {
        "roles": [],
        "skills": [{"skill_id": ICU, "required_count": 3}],
        "reported_by": 900,
    }


def test_requirement_change_audit_has_the_old_and_the_new_counts(
    client: TestClient, seeded: Session
) -> None:
    body = client.post(
        "/events",
        headers=AS_HEAD_NURSE,
        json=THREE_ICU | {"roles": [{"role_id": RN, "required_count": 6}]},
    ).json()

    _, updated, opened = _audit(seeded)
    assert (updated.action, updated.actor_id) == (
        AuditAction.REQUIREMENT_UPDATED,
        actor_service.user_id(seeded, 900),
    )
    assert (updated.event_id, updated.case_id) == (body["event_id"], None)
    assert (updated.entity_type, updated.entity_id) == (EntityType.STAFFING_REQUIREMENTS, 1)
    assert updated.payload == {
        "requirement_id": 1,
        "roles": [{"role_id": RN, "old_required_count": 5, "new_required_count": 6}],
        "skills": [{"skill_id": ICU, "old_required_count": 2, "new_required_count": 3}],
    }
    role = seeded.get(StaffingRequirementRole, (1, RN))
    assert role is not None
    assert role.required_count == 6
    # Headcount is still 5 of 5: the case is about the role and the skill
    assert opened.payload["headcount_gap"] == 0


def test_requirement_change_that_asks_for_less_opens_no_case(
    client: TestClient, seeded: Session
) -> None:
    body = client.post(
        "/events",
        headers=AS_HEAD_NURSE,
        json={
            "event_type": "REQUIREMENT_CHANGED",
            "shift_id": NIGHT_SHIFT,
            "roles": [{"role_id": RN, "required_count": 4}],
        },
    ).json()

    assert (body["event_status"], body["case_id"]) == ("IGNORED", None)
    role = seeded.get(StaffingRequirementRole, (1, RN))
    assert role is not None
    assert role.required_count == 4


# --------------------------------------------------------------------------- #
# Requests that are rejected: nothing may be written
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("headers", "body", "status_code"),
    [
        # Only a head nurse reports these three types
        (AS_105, CANCEL_104, 403),
        (AS_105, SURGE_TO_12, 403),
        (AS_105, THREE_ICU, 403),
        # The shift is looked up before the role (section 3.5)
        (AS_105, SURGE_TO_12 | {"shift_id": 999}, 404),
        (AS_HEAD_NURSE, CANCEL_104 | {"shift_id": 999}, 404),
        ({}, SURGE_TO_12, 401),
        # 201 is not on the night shift, and 999 is nobody
        (AS_HEAD_NURSE, CANCEL_104 | {"staff_id": 201}, 409),
        (AS_HEAD_NURSE, CANCEL_104 | {"staff_id": 999}, 409),
        (AS_HEAD_NURSE, CANCEL_104 | {"reason": "   "}, 422),
        (AS_HEAD_NURSE, {k: v for k, v in CANCEL_104.items() if k != "reason"}, 422),
        (AS_HEAD_NURSE, {k: v for k, v in CANCEL_104.items() if k != "staff_id"}, 422),
        (AS_HEAD_NURSE, CANCEL_104 | {"staff_id": 0}, 422),
        (AS_HEAD_NURSE, CANCEL_104 | {"patient_count": 12}, 422),
        (AS_HEAD_NURSE, SURGE_TO_12 | {"patient_count": -1}, 422),
        (AS_HEAD_NURSE, SURGE_TO_12 | {"patient_count": 2**31}, 422),
        (AS_HEAD_NURSE, SURGE_TO_12 | {"patient_count": None}, 422),
        (AS_HEAD_NURSE, SURGE_TO_12 | {"end_at": "2026-10-10T03:00:00+07:00"}, 422),
        (AS_HEAD_NURSE, THREE_ICU | {"skills": []}, 422),
        (AS_HEAD_NURSE, {"event_type": "REQUIREMENT_CHANGED", "shift_id": NIGHT_SHIFT}, 422),
        (AS_HEAD_NURSE, THREE_ICU | {"skills": [{"skill_id": ICU, "required_count": -1}]}, 422),
        # BLS is not in the requirement of the night shift, and role 2 neither
        (AS_HEAD_NURSE, THREE_ICU | {"skills": [{"skill_id": BLS, "required_count": 1}]}, 422),
        (
            AS_HEAD_NURSE,
            THREE_ICU | {"roles": [{"role_id": HEAD_NURSE_ROLE, "required_count": 1}]},
            422,
        ),
        (
            AS_HEAD_NURSE,
            THREE_ICU
            | {
                "skills": [
                    {"skill_id": ICU, "required_count": 3},
                    {"skill_id": ICU, "required_count": 4},
                ]
            },
            422,
        ),
        (AS_HEAD_NURSE, THREE_ICU | {"reason": "because"}, 422),
    ],
    ids=[
        "cancel_by_a_nurse",
        "surge_by_a_nurse",
        "requirement_by_a_nurse",
        "unknown_shift_before_role",
        "unknown_shift",
        "no_header",
        "cancel_someone_not_on_the_shift",
        "cancel_unknown_staff",
        "cancel_blank_reason",
        "cancel_without_reason",
        "cancel_without_staff_id",
        "cancel_staff_id_zero",
        "cancel_with_patient_count",
        "surge_negative",
        "surge_above_integer",
        "surge_null",
        "surge_with_end_at",
        "requirement_empty_list",
        "requirement_without_items",
        "requirement_negative_count",
        "requirement_unknown_skill",
        "requirement_unknown_role",
        "requirement_duplicate_skill",
        "requirement_with_reason",
    ],
)
def test_rejected_request_writes_nothing(
    client: TestClient,
    seeded: Session,
    headers: dict[str, str],
    body: dict[str, Any],
    status_code: int,
) -> None:
    before = _row_counts(seeded)

    response = client.post("/events", headers=headers, json=body)

    assert response.status_code == status_code
    assert _row_counts(seeded) == before
    assert set(_roster(seeded).values()) == {RosterStatus.ASSIGNED}
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert shift.patient_count == 10


def test_unknown_requirement_item_names_what_is_missing(client: TestClient) -> None:
    response = client.post(
        "/events",
        headers=AS_HEAD_NURSE,
        json=THREE_ICU | {"skills": [{"skill_id": BLS, "required_count": 1}]},
    )

    assert response.json() == {"detail": "Not in the requirement of shift 1: roles [], skills [2]"}


def test_event_of_a_head_nurse_type_joins_the_running_case_like_any_other(
    client: TestClient, seeded: Session
) -> None:
    """Round 6 PR EV10 (6.40): every event type joins the case that waits on its shift."""
    first = client.post(
        "/events", headers=AS_105, json={"event_type": "STAFF_UNAVAILABLE", "shift_id": 1}
    ).json()

    body = client.post("/events", headers=AS_HEAD_NURSE, json=SURGE_TO_12).json()

    assert (body["event_status"], body["case_id"], body["joined_running_case"]) == (
        "PROCESSED",
        first["case_id"],
        True,
    )
    shift = seeded.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    assert shift.patient_count == 12
