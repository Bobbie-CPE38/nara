"""GET /dashboard (docs/workflow.md 6.31, 9.8, round 6 PR F1).

The seed: ward 1 (ICU) has night shift 1 (D 23:00, inside the 24-hour window) and day
shift 2 (D+2 07:00, outside it); ward 2 (Medicine) mirrors them as shifts 21 and 22.
900 is the ICU head nurse, 902 the Medicine head nurse and 950 the Supervisor.
"""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import LlmCallLog, LlmDailyUsage, Shift, StaffingEvent, Ward
from app.domain.enums import (
    CaseStatus,
    EventStatus,
    EventType,
    LlmCallStatus,
    LlmWorkType,
    OutreachStatus,
    ShiftType,
)
from app.main import app
from app.services import llm_gateway
from tests.integration import case_rows
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT, DAY_SHIFT, MEDICINE_NIGHT = 1, 2, 21
HEAD_NURSE, MEDICINE_HEAD_NURSE, SUPERVISOR, NURSE = 900, 902, 950, 105


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _dashboard(client: TestClient, user: int = HEAD_NURSE) -> dict:
    response = client.get("/dashboard", headers={"X-Demo-User": str(user)})
    assert response.status_code == 200, response.text
    return response.json()


def _counts(body: dict) -> dict[str, int]:
    return {row["status"]: row["count"] for row in body["cases_by_status"]}


def test_a_demo_user_is_required(client: TestClient) -> None:
    assert client.get("/dashboard").status_code == 401


def test_the_clock_and_modes_say_what_is_real(client: TestClient) -> None:
    body = _dashboard(client)

    assert body["now"] == "2026-10-09T21:00:00+07:00"
    assert body["modes"] == {
        "line_mode": "simulation",
        "llm_provider": "fake",
        "llm_enabled": False,
    }
    assert body["llm_usage"] is None


@pytest.mark.parametrize(
    ("user", "wards"),
    [(HEAD_NURSE, [1]), (NURSE, [1]), (MEDICINE_HEAD_NURSE, [2]), (SUPERVISOR, [1, 2, 3])],
)
def test_each_user_sees_their_ward_and_a_supervisor_sees_all(
    client: TestClient, user: int, wards: list[int]
) -> None:
    assert _dashboard(client, user)["wards"] == wards


def test_the_ward_options_name_every_visible_ward(client: TestClient) -> None:
    """Round 6 PR EV6 (6.36.4): the filter lists the wards by name, not a joined string."""
    assert _dashboard(client, SUPERVISOR)["ward_options"] == [
        {"id": 1, "name": "ICU", "is_active": True},
        {"id": 2, "name": "Medicine", "is_active": True},
        {"id": 3, "name": "Float Pool", "is_active": True},
    ]
    assert _dashboard(client)["ward_options"] == [{"id": 1, "name": "ICU", "is_active": True}]


def test_a_ward_filter_narrows_every_number_to_that_ward(
    client: TestClient, seeded: Session
) -> None:
    case_rows.make_case(seeded, CaseStatus.FAILED)
    case_rows.make_case(seeded, CaseStatus.FAILED, shift_id=MEDICINE_NIGHT)

    medicine = client.get(
        "/dashboard", params={"ward_id": 2}, headers={"X-Demo-User": str(SUPERVISOR)}
    ).json()

    assert medicine["wards"] == [2]
    assert _counts(medicine)["FAILED"] == 1
    assert {row["ward_id"] for row in medicine["shortages"]} <= {2}
    # The options still list every ward, so the user can pick another
    assert len(medicine["ward_options"]) == 3


def test_a_ward_outside_the_users_wards_is_refused(client: TestClient) -> None:
    refused = client.get(
        "/dashboard", params={"ward_id": 2}, headers={"X-Demo-User": str(HEAD_NURSE)}
    )

    assert refused.status_code == 403


def test_cases_are_counted_by_status_within_the_visible_wards(
    client: TestClient, seeded: Session
) -> None:
    case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF)
    case_rows.make_case(seeded, CaseStatus.FAILED)
    case_rows.make_case(seeded, CaseStatus.FAILED, shift_id=MEDICINE_NIGHT)

    icu = _dashboard(client)
    supervisor = _counts(_dashboard(client, SUPERVISOR))

    assert [row["status"] for row in icu["cases_by_status"]] == [s.value for s in CaseStatus]
    assert _counts(icu) == {
        **{s.value: 0 for s in CaseStatus},
        "MANUAL_HANDOFF": 1,
        "FAILED": 1,
    }
    assert supervisor["FAILED"] == 2 and supervisor["MANUAL_HANDOFF"] == 1
    assert _counts(_dashboard(client, MEDICINE_HEAD_NURSE))["FAILED"] == 1


def test_short_shifts_inside_the_window_are_listed(client: TestClient, seeded: Session) -> None:
    """105 and 101 leave the night shift: one RN short and ICU skill short (101 had it).

    The day shift is emptied too, but it starts after the 24-hour window.
    """
    case_rows.leave(seeded, 105)
    case_rows.leave(seeded, 101)
    case_rows.cancel_roster(seeded, 202, DAY_SHIFT)
    case_rows.cancel_roster(seeded, 203, DAY_SHIFT)
    running = case_rows.make_case(seeded)

    body = _dashboard(client)

    assert body["shortages"] == [
        {
            "shift_id": NIGHT_SHIFT,
            "ward_id": 1,
            "start_at": "2026-10-09T23:00:00+07:00",
            "end_at": "2026-10-10T07:00:00+07:00",
            "headcount_gap": 2,
            "role_gaps": [{"name": "RN", "gap_count": 2}],
            "skill_gaps": [{"name": "ICU", "gap_count": 1}],
            "case_id": running.id,
            "in_progress": False,
        }
    ]


def test_a_shift_in_progress_is_still_listed(client: TestClient, seeded: Session) -> None:
    case_rows.leave(seeded, 105)
    clock.set_time(DEMO_NOW + timedelta(hours=9))  # D+1 06:00, the last hour of the shift

    assert [row["shift_id"] for row in _dashboard(client)["shortages"]] == [NIGHT_SHIFT]


def test_covered_shifts_and_other_wards_are_not_listed(client: TestClient, seeded: Session) -> None:
    case_rows.cancel_roster(seeded, 301, MEDICINE_NIGHT)

    assert _dashboard(client)["shortages"] == []
    assert [row["shift_id"] for row in _dashboard(client, SUPERVISOR)["shortages"]] == [
        MEDICINE_NIGHT
    ]


def test_pending_approvals_are_counted_per_ward(client: TestClient, seeded: Session) -> None:
    case, items = case_rows.short_case(seeded)
    case_rows.offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    case_rows.approval(seeded, case, items[201])
    case_rows.offer(seeded, case, items[202], OutreachStatus.ACCEPTED)
    case_rows.approval(seeded, case, items[202])
    case_rows.offer(seeded, case, items[203], OutreachStatus.ACCEPTED)
    case_rows.approval(seeded, case, items[203], approved=True)

    # Round 6 PR EV8: who the requests wait for, the ward's head nurse until the Supervisor
    # may decide them too
    waiting = [
        {
            "ward_id": 1,
            "count": 2,
            "head_nurses": [{"staff_id": HEAD_NURSE, "name": "Malai Demo"}],
            "supervisor": False,
        }
    ]
    assert _dashboard(client)["pending_approvals"] == waiting
    assert _dashboard(client, SUPERVISOR)["pending_approvals"] == waiting
    assert _dashboard(client, MEDICINE_HEAD_NURSE)["pending_approvals"] == []
    assert _dashboard(client)["summary"]["pending_approvals"] == 2

    clock.set_time(DEMO_NOW + timedelta(seconds=600))  # supervisor_after_seconds of the seed
    assert _dashboard(client)["pending_approvals"] == [waiting[0] | {"supervisor": True}]


def test_the_cards_and_the_chart_count_every_short_shift_of_the_window(
    client: TestClient, seeded: Session
) -> None:
    """Round 6 PR EV8 (6.38.4): positions over shifts, not people; the busiest ward first."""
    case_rows.leave(seeded, 105)
    case_rows.leave(seeded, 101)
    case_rows.cancel_roster(seeded, 301, MEDICINE_NIGHT)
    case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF)

    body = _dashboard(client, SUPERVISOR)

    assert body["window_hours"] == 24
    assert body["summary"] == {
        "short_shifts": 2,
        "missing_positions": 3,
        "pending_approvals": 0,
        "handoff_cases": 1,
    }
    assert body["shortage_by_ward"] == [
        {"ward_id": 1, "missing_positions": 2, "short_shifts": 1},
        {"ward_id": 2, "missing_positions": 1, "short_shifts": 1},
    ]
    # The ward filter narrows the cards and the chart too
    narrowed = client.get(
        "/dashboard", params={"ward_id": 2}, headers={"X-Demo-User": str(SUPERVISOR)}
    ).json()
    assert narrowed["summary"]["short_shifts"] == 1
    assert narrowed["shortage_by_ward"] == [
        {"ward_id": 2, "missing_positions": 1, "short_shifts": 1}
    ]


def test_a_running_shift_says_so(client: TestClient, seeded: Session) -> None:
    case_rows.leave(seeded, 105)
    clock.set_time(DEMO_NOW + timedelta(hours=3))  # D+1 00:00, inside the night shift

    assert [row["in_progress"] for row in _dashboard(client)["shortages"]] == [True]


def test_the_demo_seed_is_marked_as_demo_data(client: TestClient, seeded: Session) -> None:
    assert _dashboard(client)["demo_data"] is True


def test_open_offers_count_only_sent_and_unexpired(client: TestClient, seeded: Session) -> None:
    case, items = case_rows.short_case(seeded)
    case_rows.offer(seeded, case, items[201])
    case_rows.offer(seeded, case, items[202], OutreachStatus.REJECTED)
    expired = case_rows.offer(seeded, case, items[203])
    expired.expires_at = DEMO_NOW
    seeded.flush()

    assert _dashboard(client)["open_offers"] == {"count": 1}
    assert _dashboard(client, MEDICINE_HEAD_NURSE)["open_offers"] == {"count": 0}


def test_offers_of_a_stopped_case_are_not_open(client: TestClient, seeded: Session) -> None:
    case, items = case_rows.short_case(seeded, status=CaseStatus.MANUAL_HANDOFF)
    case_rows.offer(seeded, case, items[201])

    assert _dashboard(client)["open_offers"] == {"count": 0}


def _event(db: Session, *, shift_id: int, staff_id: int, reason: str | None, minutes: int) -> int:
    row = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift_id,
        occurred_at=DEMO_NOW + timedelta(minutes=minutes),
        staff_id=staff_id,
        payload={} if reason is None else {"reason": reason, "roster_assignment_id": 1},
        status=EventStatus.RECEIVED,
    )
    db.add(row)
    db.flush()
    return row.id


def test_recent_no_shows_are_newest_first_and_only_no_shows(
    client: TestClient, seeded: Session
) -> None:
    older = _event(seeded, shift_id=NIGHT_SHIFT, staff_id=103, reason="NO_SHOW", minutes=1)
    newer = _event(seeded, shift_id=NIGHT_SHIFT, staff_id=104, reason="NO_SHOW", minutes=2)
    _event(seeded, shift_id=NIGHT_SHIFT, staff_id=105, reason=None, minutes=3)
    _event(seeded, shift_id=MEDICINE_NIGHT, staff_id=301, reason="NO_SHOW", minutes=4)

    body = _dashboard(client)

    assert body["recent_no_show"] == [
        {
            "event_id": newer,
            "shift_id": 1,
            "staff_id": 104,
            "created_at": "2026-10-09T21:02:00+07:00",
        },
        {
            "event_id": older,
            "shift_id": 1,
            "staff_id": 103,
            "created_at": "2026-10-09T21:01:00+07:00",
        },
    ]
    assert len(_dashboard(client, SUPERVISOR)["recent_no_show"]) == 3


def test_at_most_ten_no_shows(client: TestClient, seeded: Session) -> None:
    for minute in range(12):
        _event(seeded, shift_id=NIGHT_SHIFT, staff_id=103, reason="NO_SHOW", minutes=minute)

    assert len(_dashboard(client)["recent_no_show"]) == 10


def _trial_log(db: Session, key: str, cost: str | None, started_at=DEMO_NOW) -> None:
    db.add(
        LlmCallLog(
            work_type=LlmWorkType.MODEL_TRIAL,
            trial_run_id="dashboard-test",
            trial_case_key=key,
            provider="fake",
            prompt_version="test",
            attempt=1,
            status=LlmCallStatus.SUCCEEDED if cost is not None else LlmCallStatus.IN_FLIGHT,
            estimated_cost_usd=None if cost is None else Decimal(cost),
            started_at=started_at,
        )
    )
    db.flush()


def test_llm_usage_shows_today_and_the_month_when_enabled(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    seeded.add(LlmDailyUsage(usage_date=llm_gateway.quota_day(seeded), used=37))
    _trial_log(seeded, "a", "0.25")
    _trial_log(seeded, "b", "0.50", started_at=DEMO_NOW.replace(day=1, hour=0))
    _trial_log(seeded, "c", None)
    # The month before and the month after are not this month's bill
    _trial_log(seeded, "d", "9", started_at=DEMO_NOW.replace(day=1, hour=0) - timedelta(seconds=1))
    _trial_log(seeded, "e", "9", started_at=DEMO_NOW.replace(month=11, day=1, hour=0))

    usage = _dashboard(client)["llm_usage"]

    assert usage == {
        "date": llm_gateway.quota_day(seeded).isoformat(),
        "used": 37,
        "cap": settings.llm_daily_call_cap,
        "month_cost_usd": "0.75000000",
        "month_calls_without_cost": 1,
        "budget_usd": "20",
    }


def test_llm_usage_is_zero_on_a_day_without_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)

    usage = _dashboard(client)["llm_usage"]

    assert usage["used"] == 0 and usage["month_calls_without_cost"] == 0
    assert Decimal(usage["month_cost_usd"]) == 0


def test_the_dashboard_writes_nothing(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No INSERT, UPDATE or DELETE and no row lock, with every section filled."""
    monkeypatch.setattr(settings, "llm_enabled", True)
    case, items = case_rows.short_case(seeded)
    case_rows.offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    case_rows.approval(seeded, case, items[201])
    case_rows.offer(seeded, case, items[202])
    _event(seeded, shift_id=NIGHT_SHIFT, staff_id=103, reason="NO_SHOW", minutes=1)
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    bind = seeded.connection()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        body = _dashboard(client, SUPERVISOR)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert body["shortages"] and body["pending_approvals"] and body["recent_no_show"]
    writes = [
        sql
        for sql in statements
        if sql.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        or "FOR UPDATE" in sql.upper()
        or "FOR NO KEY UPDATE" in sql.upper()
    ]
    assert statements and writes == []


def test_a_shift_without_a_requirement_does_not_break_the_dashboard(
    client: TestClient, seeded: Session
) -> None:
    """Review finding: one active shift with no STAFFING_REQUIREMENTS row used to be a 500.

    It cannot be measured, so it is skipped; the shifts that can be measured still show.
    """
    case_rows.leave(seeded, 105)
    seeded.add(
        Shift(
            id=9001,
            ward_id=1,
            patient_count=2,
            start_at=DEMO_NOW + timedelta(hours=1),
            end_at=DEMO_NOW + timedelta(hours=9),
            shift_type=ShiftType.DAY,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    seeded.flush()

    body = _dashboard(client)

    assert [row["shift_id"] for row in body["shortages"]] == [NIGHT_SHIFT]


def test_a_supervisor_may_pick_a_paused_ward(client: TestClient, seeded: Session) -> None:
    """Review of #145: a test run pauses the hospital wards, and their links gave 403."""
    medicine = seeded.get(Ward, 2)
    assert medicine is not None
    medicine.is_active = False
    seeded.flush()

    every = _dashboard(client, SUPERVISOR)
    paused = client.get(
        "/dashboard", params={"ward_id": 2}, headers={"X-Demo-User": str(SUPERVISOR)}
    )

    # The numbers still cover the active wards; the paused one is offered after them
    assert every["wards"] == [1, 3]
    assert every["ward_options"][-1] == {"id": 2, "name": "Medicine", "is_active": False}
    assert paused.status_code == 200 and paused.json()["wards"] == [2]
    assert (
        client.get("/dashboard", params={"ward_id": 2}, headers={"X-Demo-User": "900"}).status_code
        == 403
    )
