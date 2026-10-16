"""Late arrival after a NO_SHOW was recorded (docs/workflow.md, section 6.24).

The Golden Case night shift (id 1) runs D 23:00 - D+1 07:00 with staff 101-105 REGULAR
ASSIGNED and a zero merge window: when the job finds someone missing, the NO_SHOW
event closes at once, the row is cancelled and a case opens. The handlers are stubs,
so the case waits at WAITING_RESPONSE; its candidates are written by hand. What is
real here is stage 2, the check-in, the restore and the trim of the surplus.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    Shift,
    StaffingCase,
    StructuredHandover,
)
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    CheckInSource,
    EventType,
    OutreachStatus,
    RosterStatus,
)
from app.main import app
from app.services import (
    actor_service,
    attendance_service,
    case_facts_service,
    event_service,
    no_show_service,
    roster_service,
    unavailability_service,
    working_time_service,
)
from tests.integration.case_rows import (
    approval,
    assign,
    make_case,
    make_plan,
    offer,
    record_gap,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.no_show_rows import (
    DEADLINE,
    END,
    NIGHT_SHIFT,
    START,
    absences,
    add_row,
    add_shift,
    at,
    audit_of,
    check_in_everyone,
    roster_row,
    rows_of,
)

pytestmark = pytest.mark.usefixtures("stub_handlers")

SECOND = timedelta(seconds=1)
ARRIVAL = START + timedelta(minutes=30)
OPEN_UNTIL = START + timedelta(hours=2)  # an offer still open when the person arrives


def open_no_show_case(db: Session, missing: tuple[int, ...] = (101,)) -> StaffingCase:
    """Everyone but `missing` checks in; the job finds the rest and a case opens."""
    check_in_everyone(db, except_staff=missing)
    at(DEADLINE + SECOND)
    assert len(no_show_service.detect_due_no_shows(db)) == len(missing)
    db.expire_all()
    case = db.scalars(select(StaffingCase)).one()
    assert case.status == CaseStatus.WAITING_RESPONSE
    # The stub ASSESSING step writes no gap: take it as the real one does, when the case opens
    record_gap(db, case)
    return case


def arrive(
    db: Session, staff_id: int, when: datetime = ARRIVAL, shift_id: int = NIGHT_SHIFT
) -> attendance_service.CheckInResult:
    at(when)
    return attendance_service.check_in(
        db,
        staff_id=staff_id,
        shift_id=shift_id,
        source=CheckInSource.SIMULATED,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
    )


def case_of(db: Session) -> StaffingCase:
    """The latest case, read again from the database."""
    db.expire_all()
    return db.scalars(select(StaffingCase).order_by(StaffingCase.id.desc()).limit(1)).one()


def candidate_offers(
    db: Session, case: StaffingCase, staff_ids: tuple[int, ...]
) -> dict[int, CandidateOutreach]:
    """One SENT offer of the case for each person, in rank order."""
    items = make_plan(db, case, staff_ids)
    offers = {staff_id: offer(db, case, items[staff_id]) for staff_id in staff_ids}
    for row in offers.values():
        row.expires_at = OPEN_UNTIL
    db.flush()
    return offers


def statuses(db: Session, offers: dict[int, CandidateOutreach]) -> dict[int, OutreachStatus]:
    db.expire_all()
    return {staff_id: row.status for staff_id, row in offers.items()}


def not_needed(db: Session) -> list[AuditLog]:
    return audit_of(db, AuditAction.OFFER_CANCELLED_NOT_NEEDED)


def requests_of(db: Session, case: StaffingCase) -> list[ApprovalRequest]:
    db.expire_all()
    return list(
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.case_id == case.id)
            .order_by(ApprovalRequest.id)
        )
    )


def pending_request(db: Session, case: StaffingCase, item: CandidateItem) -> ApprovalRequest:
    """A pending request still open when the person arrives (approval() expires at 21:15)."""
    request = approval(db, case, item)
    request.expires_at = OPEN_UNTIL
    db.flush()
    return request


def offer_status(db: Session, outreach_id: int) -> OutreachStatus:
    db.expire_all()
    return db.get_one(CandidateOutreach, outreach_id).status


# ---- the restore -------------------------------------------------------------------------------


def test_a_check_in_after_stage_two_restores_the_row_from_the_arrival_and_credits_the_case(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    [absence] = absences(db)
    assert absence.reason == AvailabilityReason.NO_SHOW and absence.end_at == END

    result = arrive(db, 101)

    assert (result.on_time, result.check_in_at) == (False, ARRIVAL)
    original, restored = rows_of(db, 101)
    assert original.status == RosterStatus.CANCELLED
    assert restored.status == RosterStatus.ASSIGNED
    assert (restored.actual_start_at, restored.actual_end_at) == (ARRIVAL, None)
    assert restored.assignment_type == original.assignment_type
    [absence] = absences(db)
    assert (absence.reason, absence.start_at, absence.end_at) == (
        AvailabilityReason.NO_SHOW,
        START,
        ARRIVAL,
    )
    [updated] = audit_of(db, AuditAction.UNAVAILABILITY_UPDATED)
    assert updated.actor_id == actor_service.component_id(db, ActorName.SYSTEM)
    assert updated.case_id == case.id and updated.entity_id == absence.id
    assert updated.payload == {
        "unavailability_id": absence.id,
        "staff_id": 101,
        "previous_end_at": END.isoformat(),
        "end_at": ARRIVAL.isoformat(),
        "roster_assignment_id": restored.id,
        "late_arrival": True,
    }
    # The attendance names the row that was cancelled, as the first check-in does
    [checked_in] = [
        row
        for row in audit_of(db, AuditAction.ATTENDANCE_CHECKED_IN)
        if row.payload["staff_id"] == 101
    ]
    assert checked_in.payload["roster_assignment_id"] == original.id
    assert checked_in.payload["on_time"] is False


def test_the_case_counts_the_late_person_and_the_read_model_does_not(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    assert not case_facts_service.load_case_facts(db, case).gap_closed_by_assigned

    arrive(db, 101)

    case = case_of(db)
    # 101 closes the gap alone, so the case finishes (the stub EXECUTING resolves it)
    assert case.status == CaseStatus.RESOLVED
    assert case_facts_service.load_case_facts(db, case).gap_closed_by_assigned
    assert [filler.staff_id for filler in case_facts_service.get_case_fillers(db, case.id)] == [101]
    assert case_facts_service.assigned_staff_ids(db, case.id) == set()


def test_hours_and_the_gap_use_the_actual_arrival_time(production_seeded: Session) -> None:
    db = production_seeded
    open_no_show_case(db)
    arrive(db, 101)

    captured = working_time_service.capture(db, [101, 102], captured_at=END)
    missed = captured[102].values.hours_this_week - captured[101].values.hours_this_week
    assert float(missed) == pytest.approx(0.5)


def test_a_regular_nurse_restored_row_has_no_handover(production_seeded: Session) -> None:
    db = production_seeded
    open_no_show_case(db)
    arrive(db, 101)

    restored = roster_row(db, 101)
    assert (
        db.scalars(
            select(StructuredHandover).where(StructuredHandover.roster_assignment_id == restored.id)
        ).all()
        == []
    )


def test_a_replacement_with_a_handover_gets_one_on_the_new_row_and_the_old_one_stays(
    production_seeded: Session,
) -> None:
    db = production_seeded
    first_case = make_case(db, CaseStatus.RESOLVED)
    shift = db.get_one(Shift, NIGHT_SHIFT)
    replacement = roster_service.create_assignment(
        db,
        shift=shift,
        staff_id=201,
        case=first_case,
        candidate_source=CandidateSource.SAME_WARD,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
    )
    replacement.created_at = DEMO_NOW  # before the shift, so the deadline is 23:15
    db.flush()
    check_in_everyone(db, except_staff=(201,))
    at(DEADLINE + SECOND)
    assert len(no_show_service.detect_due_no_shows(db)) == 1
    assert [row.status for row in rows_of(db, 201)] == [RosterStatus.CANCELLED]

    arrive(db, 201)

    old, new = rows_of(db, 201)
    assert (old.id, new.assignment_type) == (replacement.id, AssignmentType.REPLACEMENT)
    handovers = {
        row.roster_assignment_id: row
        for row in db.scalars(
            select(StructuredHandover).where(
                StructuredHandover.roster_assignment_id.in_([old.id, new.id])
            )
        )
    }
    assert set(handovers) == {old.id, new.id}
    assert handovers[new.id].case_id == first_case.id
    assert handovers[new.id].incoming_staff_id == 201


# ---- the surplus -------------------------------------------------------------------------------


def test_the_offers_a_late_arrival_made_surplus_are_cancelled_and_audited(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    offers = candidate_offers(db, case, (201, 202))

    arrive(db, 101)

    assert statuses(db, offers) == {201: OutreachStatus.CANCELLED, 202: OutreachStatus.CANCELLED}
    audits = not_needed(db)
    assert [row.entity_id for row in audits] == [offers[201].id, offers[202].id]
    first = audits[0]
    assert first.case_id == case.id
    assert first.actor_id == actor_service.component_id(db, ActorName.SYSTEM)
    assert first.payload == {
        "cancelled_outreach_id": offers[201].id,
        "approval_request_id": None,
        "staff_id": 201,
        "late_staff_id": 101,
        "reason": "NO_LONGER_NEEDED",
    }


def test_a_replacement_assigned_before_the_arrival_stays_and_only_the_surplus_is_cancelled(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db, missing=(101, 102))
    items = make_plan(db, case, (201, 202, 203))
    assign(db, case, items[201])
    request = pending_request(db, case, items[202])
    sent = offer(db, case, items[203])
    sent.expires_at = OPEN_UNTIL
    db.flush()
    approved_request = requests_of(db, case)[0]
    replacement_row = roster_row(db, 201)

    arrive(db, 101)

    # 201 (a replacement) and 101 (back) close the gap of two
    assert roster_row(db, 201).id == replacement_row.id
    assert offer_status(db, sent.id) == OutreachStatus.CANCELLED
    assert offer_status(db, request.outreach_id) == OutreachStatus.CANCELLED
    # The request stays as history, the approved replacement keeps its accepted offer
    assert [(row.id, row.is_pending) for row in requests_of(db, case)] == [
        (approved_request.id, False),
        (request.id, True),
    ]
    assert offer_status(db, approved_request.outreach_id) == OutreachStatus.ACCEPTED
    by_staff = {row.payload["staff_id"]: row.payload for row in not_needed(db)}
    assert set(by_staff) == {202, 203}
    assert by_staff[202]["approval_request_id"] == request.id
    assert by_staff[203]["approval_request_id"] is None
    assert case_of(db).status == CaseStatus.RESOLVED


def test_a_case_short_of_two_keeps_looking_for_the_other_when_one_person_arrives(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db, missing=(101, 102))
    offers = candidate_offers(db, case, (201, 202, 203))

    arrive(db, 101)

    # One person is still missing: the best ranked offer stays, the other two go
    assert statuses(db, offers) == {
        201: OutreachStatus.SENT,
        202: OutreachStatus.CANCELLED,
        203: OutreachStatus.CANCELLED,
    }
    assert {row.payload["staff_id"] for row in not_needed(db)} == {202, 203}
    assert case_of(db).status == CaseStatus.WAITING_RESPONSE
    assert not case_facts_service.load_case_facts(db, case_of(db)).gap_closed_by_assigned


def test_a_pending_request_wins_a_tie_over_an_unanswered_offer(production_seeded: Session) -> None:
    db = production_seeded
    case = open_no_show_case(db, missing=(101, 102))
    items = make_plan(db, case, (201, 203))
    # 201 has the better rank but only an unanswered offer; 203 waits for approval. Both
    # are RNs with ICU, so each one alone closes what the arrival left open
    sent = offer(db, case, items[201])
    sent.expires_at = OPEN_UNTIL
    pending_request(db, case, items[203])

    arrive(db, 101)

    assert offer_status(db, sent.id) == OutreachStatus.CANCELLED
    assert [row.payload["staff_id"] for row in not_needed(db)] == [201]
    assert case_of(db).status == CaseStatus.WAITING_APPROVAL


def test_an_expired_request_does_not_displace_a_valid_offer(production_seeded: Session) -> None:
    """The check-in comes after 203's request expired but before the timeout job ran."""
    db = production_seeded
    case = open_no_show_case(db, missing=(101, 102))
    items = make_plan(db, case, (201, 203))
    sent = offer(db, case, items[201])
    sent.expires_at = OPEN_UNTIL
    request = approval(db, case, items[203])
    request.expires_at = ARRIVAL - SECOND  # expired, the timeout job has not run yet
    db.flush()

    arrive(db, 101)

    # One person is still missing: the valid offer stays, the expired request waits
    # for the timeout job and trim writes nothing about it
    assert offer_status(db, sent.id) == OutreachStatus.SENT
    assert not_needed(db) == []
    assert offer_status(db, request.outreach_id) == OutreachStatus.ACCEPTED
    assert requests_of(db, case)[0].is_pending is True


def test_trim_keeps_coverage_first_a_request_for_the_first_half_loses_to_an_offer_for_the_rest(
    production_seeded: Session,
) -> None:
    db = production_seeded
    check_in_everyone(db)
    # One RN on 23:00-03:00 and nobody after: the person comes late, the rest stays open
    shift = add_shift(db, start_at=START, end_at=END, required_staff=1)
    row = add_row(db, 201, shift)
    row.actual_end_at = START + timedelta(hours=4)
    db.flush()
    at(DEADLINE + SECOND)
    assert len(no_show_service.detect_due_no_shows(db)) == 1
    db.expire_all()
    case = db.scalars(select(StaffingCase).where(StaffingCase.shift_id == shift.id)).one()
    record_gap(db, case)
    items = make_plan(db, case, (202, 203))
    items[202].cover_start_at = START
    items[202].cover_end_at = START + timedelta(hours=4)
    items[203].cover_start_at = START + timedelta(hours=4)
    items[203].cover_end_at = END
    request = pending_request(db, case, items[202])
    second_half = offer(db, case, items[203])
    second_half.expires_at = OPEN_UNTIL
    db.flush()

    arrive(db, 201, shift_id=shift.id)

    # 201 now covers 23:30-03:00 itself, so the pending request has nothing left to add
    assert offer_status(db, request.outreach_id) == OutreachStatus.CANCELLED
    assert offer_status(db, second_half.id) == OutreachStatus.SENT
    assert [row.payload["staff_id"] for row in not_needed(db)] == [202]
    assert case_of(db).status == CaseStatus.WAITING_RESPONSE


def test_a_late_arrival_in_a_case_that_stopped_for_a_head_nurse_is_credited_to_it(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    case.status = CaseStatus.MANUAL_HANDOFF
    db.flush()

    arrive(db, 101)

    [updated] = audit_of(db, AuditAction.UNAVAILABILITY_UPDATED)
    assert updated.case_id == case.id
    assert not_needed(db) == []
    assert case_of(db).status == CaseStatus.MANUAL_HANDOFF
    assert roster_row(db, 101).actual_start_at == ARRIVAL


def test_a_late_arrival_with_no_open_case_restores_the_row_and_credits_nobody(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    case.status = CaseStatus.RESOLVED
    db.flush()

    arrive(db, 101)

    [updated] = audit_of(db, AuditAction.UNAVAILABILITY_UPDATED)
    assert updated.case_id is None
    assert roster_row(db, 101).actual_start_at == ARRIVAL


# ---- the check-in itself -----------------------------------------------------------------------


def test_a_repeated_check_in_after_the_restore_changes_nothing(production_seeded: Session) -> None:
    db = production_seeded
    open_no_show_case(db)
    first = arrive(db, 101)
    again = arrive(db, 101, ARRIVAL + timedelta(minutes=5))

    assert (again.attendance_id, again.check_in_at) == (first.attendance_id, ARRIVAL)
    assert len(rows_of(db, 101)) == 2
    assert len(audit_of(db, AuditAction.UNAVAILABILITY_UPDATED)) == 1


def test_a_check_in_at_the_end_of_the_row_is_refused_and_nothing_is_written(
    production_seeded: Session,
) -> None:
    db = production_seeded
    open_no_show_case(db)

    with pytest.raises(attendance_service.CheckInOutsideWindowError):
        arrive(db, 101, END)
    db.rollback()

    assert [row.status for row in rows_of(db, 101)] == [RosterStatus.CANCELLED]
    assert audit_of(db, AuditAction.UNAVAILABILITY_UPDATED) == []


def test_a_leave_after_the_no_show_is_refused_and_the_arrival_keeps_the_reason(
    production_seeded: Session,
) -> None:
    db = production_seeded
    open_no_show_case(db)
    with pytest.raises(unavailability_service.NoAssignedRosterError):
        event_service.receive_event(
            db,
            staff_id=101,
            actor_id=actor_service.user_id(db, 101),
            role_id=1,
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=NIGHT_SHIFT,
        )
    db.rollback()

    arrive(db, 101)

    [absence] = absences(db)
    assert (absence.reason, absence.end_at) == (AvailabilityReason.NO_SHOW, ARRIVAL)


# ---- what the person sees ----------------------------------------------------------------------


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


def test_a_surplus_offer_shows_no_longer_needed_in_the_offers_of_the_person(
    production_seeded: Session, client: TestClient
) -> None:
    db = production_seeded
    case = open_no_show_case(db)
    offers = candidate_offers(db, case, (201,))
    db.commit()

    at(ARRIVAL)
    response = client.post("/demo/attendance/check-in", json={"staff_id": 101, "shift_id": 1})
    assert response.status_code == 200 and response.json()["on_time"] is False

    listed = client.get("/me/offers", headers={"X-Demo-User": "201"}).json()
    [view] = [row for row in listed if row["id"] == offers[201].id]
    assert view["status"] == "CANCELLED"
    assert view["cancellation_reason"] == "NO_LONGER_NEEDED"
    assert view["can_accept"] is False
