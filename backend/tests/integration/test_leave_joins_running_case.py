"""Round 6 PR EV10 (docs/workflow.md 6.40): several people leave one shift while its case runs.

The Golden Case night shift has a merge window of 0 and 101-105 on it. Before EV10 the
second leave waited as RECEIVED until the first case stopped; now it joins that case.
"""

import threading
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.enums import (
    AuditAction,
    CandidateResponse,
    CaseStatus,
    EventStatus,
    OutreachStatus,
    RosterStatus,
)
from app.services import (
    actor_service,
    approval_service,
    gap_service,
    outreach_service,
    unavailability_service,
)
from tests.integration.case_rows import (
    DAY_SHIFT,
    NIGHT_SHIFT,
    approval,
    make_case,
    make_plan,
    record_gap,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_merge_window import report


def roster(db: Session, staff_id: int, shift_id: int = NIGHT_SHIFT) -> RosterStatus:
    db.expire_all()
    return db.scalars(
        select(RosterAssignment.status).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()


def latest_gap(db: Session, case_id: int) -> int:
    db.expire_all()
    return gap_service.get_case_gap(db, case_id).gap.headcount_gap


def offers(db: Session, case_id: int, status: OutreachStatus) -> list[CandidateOutreach]:
    db.expire_all()
    return list(
        db.scalars(
            select(CandidateOutreach)
            .where(CandidateOutreach.case_id == case_id, CandidateOutreach.status == status)
            .order_by(CandidateOutreach.id)
        )
    )


def accept(db: Session, row: CandidateOutreach) -> None:
    staff_id = db.scalar(
        select(CandidateItem.staff_id).where(CandidateItem.id == row.candidate_item_id)
    )
    assert staff_id is not None
    outreach_service.record_response(
        db,
        staff_id=staff_id,
        actor_id=actor_service.user_id(db, staff_id),
        outreach_id=row.id,
        response=CandidateResponse.ACCEPT,
    )


def test_two_leaves_in_a_row_both_count_without_answering_the_first_offers(seeded: Session):
    first = report(seeded, 101)
    assert first.case_id is not None and first.case_status is CaseStatus.WAITING_RESPONSE
    gap_before = latest_gap(seeded, first.case_id)
    sent_before = {row.id for row in offers(seeded, first.case_id, OutreachStatus.SENT)}

    second = report(seeded, 102)

    assert (second.event_status, second.case_id, second.joined_running_case) == (
        EventStatus.PROCESSED,
        first.case_id,
        True,
    )
    # Both are off the shift and away for its time
    assert roster(seeded, 101) is RosterStatus.CANCELLED
    assert roster(seeded, 102) is RosterStatus.CANCELLED
    away = set(seeded.scalars(select(StaffUnavailability.staff_id)))
    assert {101, 102} <= away
    # The gap of the case is measured again from the shift: one more person short
    assert latest_gap(seeded, first.case_id) == gap_before + 1
    # The offers already sent are kept, not started again
    assert sent_before <= {row.id for row in offers(seeded, first.case_id, OutreachStatus.SENT)}
    assert seeded.scalar(select(func.count()).select_from(StaffingCase)) == 1
    joined = seeded.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.CASE_EVENTS_JOINED)
    )
    assert joined.payload["event_ids"] == [second.event_id]


def test_the_same_person_reporting_again_adds_nothing(seeded: Session):
    first = report(seeded, 101)
    assert first.case_id is not None
    gap = latest_gap(seeded, first.case_id)
    with pytest.raises(unavailability_service.NoAssignedRosterError):
        report(seeded, 101)
    seeded.rollback()
    assert latest_gap(seeded, first.case_id) == gap
    assert seeded.scalar(select(func.count()).select_from(StaffUnavailability)) == 1


def test_a_leave_while_waiting_for_approval_keeps_the_accepted_candidate(seeded: Session):
    first = report(seeded, 105)
    assert first.case_id is not None
    (sent,) = offers(seeded, first.case_id, OutreachStatus.SENT)[:1]
    accept(seeded, sent)
    seeded.expire_all()
    case = seeded.get_one(StaffingCase, first.case_id)
    assert case.status is CaseStatus.WAITING_APPROVAL
    request = seeded.scalars(
        select(ApprovalRequest).where(ApprovalRequest.case_id == case.id)
    ).one()

    second = report(seeded, 104)

    assert second.case_id == case.id and second.joined_running_case
    seeded.expire_all()
    # The accepted candidate and the request stay: progress is not thrown away
    assert seeded.get_one(ApprovalRequest, request.id).is_pending
    assert seeded.get_one(CandidateOutreach, sent.id).status is OutreachStatus.ACCEPTED
    # One more is needed, so the case sent the next wave while the request waits
    case = seeded.get_one(StaffingCase, case.id)
    assert case.status is CaseStatus.WAITING_RESPONSE
    assert offers(seeded, case.id, OutreachStatus.SENT)


def test_a_leave_after_one_approval_counts_the_replacement_once(seeded: Session):
    """A gap of two: one replacement is approved and on the shift, then another person leaves.

    The new gap leaves out the replacement's own row (credited_assignment_ids), so the case
    still counts that person once and needs exactly one more than before.
    """
    first = report(seeded, 105)
    assert first.case_id is not None
    second = report(seeded, 104)
    assert second.case_id == first.case_id
    gap_two = latest_gap(seeded, first.case_id)
    row = offers(seeded, first.case_id, OutreachStatus.SENT)[0]
    accept(seeded, row)
    request = seeded.scalars(
        select(ApprovalRequest).where(ApprovalRequest.case_id == first.case_id)
    ).one()
    head = seeded.get_one(Staff, 900)
    approval_service.decide(
        seeded,
        approval_id=request.id,
        staff_id=900,
        role_id=head.role_id,
        home_ward_id=head.home_ward_id,
        actor_id=actor_service.user_id(seeded, 900),
        approved=True,
    )
    seeded.expire_all()
    assert seeded.get_one(StaffingCase, first.case_id).status is not CaseStatus.RESOLVED

    third = report(seeded, 103)

    assert third.case_id == first.case_id
    assert latest_gap(seeded, first.case_id) == gap_two + 1
    seeded.expire_all()
    # Still open: the replacement counts once against a gap one larger
    assert seeded.get_one(StaffingCase, first.case_id).status not in {
        CaseStatus.RESOLVED,
        CaseStatus.FAILED,
    }


def test_a_person_on_leave_loses_live_offers_for_that_time(seeded: Session):
    """103 has accepted an offer of a day-shift case and waits for approval, then reports
    leave on the night shift until the middle of the day shift: that offer must end."""
    day = make_case(seeded, CaseStatus.WAITING_APPROVAL, shift_id=DAY_SHIFT)
    record_gap(seeded, day)
    item = make_plan(seeded, day, (103,))[103]
    request = approval(seeded, day, item)
    seeded.commit()
    day_shift = seeded.get_one(Shift, DAY_SHIFT)
    outcome = report(seeded, 103, end_at=day_shift.start_at + timedelta(hours=3))

    assert outcome.event_status is EventStatus.PROCESSED
    seeded.expire_all()
    offer = seeded.get_one(CandidateOutreach, request.outreach_id)
    assert offer.status is OutreachStatus.CANCELLED
    audit = seeded.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.OFFER_CANCELLED_STAFF_UNAVAILABLE)
    )
    assert audit.payload["cancelled_outreach_id"] == offer.id
    assert audit.payload["event_id"] == outcome.event_id
    head = seeded.get_one(Staff, 900)
    # The offer is gone (or the case then had nobody left and stopped): no approval
    with pytest.raises(
        (approval_service.ApprovalOfferConflictError, approval_service.ApprovalNotPendingError)
    ):
        approval_service.decide(
            seeded,
            approval_id=request.id,
            staff_id=900,
            role_id=head.role_id,
            home_ward_id=head.home_ward_id,
            actor_id=actor_service.user_id(seeded, 900),
            approved=True,
        )
    seeded.rollback()
    assert (
        seeded.scalar(
            select(func.count())
            .select_from(RosterAssignment)
            .where(RosterAssignment.staff_id == 103, RosterAssignment.shift_id == DAY_SHIFT)
        )
        == 0
    )


def test_an_offer_outside_the_leave_is_kept(seeded: Session):
    day = make_case(seeded, CaseStatus.WAITING_APPROVAL, shift_id=DAY_SHIFT)
    record_gap(seeded, day)
    item = make_plan(seeded, day, (103,))[103]
    request = approval(seeded, day, item)
    seeded.commit()
    report(seeded, 103)
    seeded.expire_all()
    assert seeded.get_one(CandidateOutreach, request.outreach_id).status is OutreachStatus.ACCEPTED


@pytest.fixture
def committed_seed(frozen_clock: Any):
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.seed import load

    with SessionLocal.begin() as db:
        load(db)
    try:
        yield
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_leaves_sent_at_once_lose_nothing_and_open_one_case(committed_seed: None):
    from app.db.session import SessionLocal

    start = threading.Barrier(3, timeout=10)
    results: dict[int, Any] = {}

    def leave(staff_id: int) -> None:
        with SessionLocal() as db:
            start.wait()
            results[staff_id] = report(db, staff_id)

    threads = [threading.Thread(target=leave, args=(staff_id,)) for staff_id in (101, 102, 103)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert set(results) == {101, 102, 103}
    with SessionLocal() as db:
        events = list(db.scalars(select(StaffingEvent).order_by(StaffingEvent.id)))
        assert [event.status for event in events] == [EventStatus.PROCESSED] * 3
        cases = list(db.scalars(select(StaffingCase)))
        assert len(cases) == 1
        assert {event.case_id for event in events} == {cases[0].id}
        assert cases[0].status is not CaseStatus.FAILED
        for staff_id in (101, 102, 103):
            assert roster(db, staff_id) is RosterStatus.CANCELLED
        shift = db.get_one(Shift, NIGHT_SHIFT)
        assert (
            latest_gap(db, cases[0].id) == gap_service.assess_shift(db, shift).result.headcount_gap
        )


def test_reported_while_its_window_is_open_tells_when_it_closes(seeded: Session):
    seeded.get_one(Shift, NIGHT_SHIFT).merge_window_seconds = 600
    seeded.commit()
    outcome = report(seeded, 101)
    assert outcome.event_status is EventStatus.RECEIVED
    assert outcome.window_closes_at == DEMO_NOW + timedelta(seconds=600)
