"""Example cases of the hospital demo, played through the real workflow (round 6 PR EV7,
docs/workflow.md 6.37.1).

Right after a demo reset that loads the hospital demo, the Demo control plays a few leaves
on its wards so that every page has something to show: a case that ended with a
replacement, one waiting in MANUAL_HANDOFF, one closed without a replacement, one staffed by
hand from the handoff page, one waiting for its head nurse's approval and one with offers
still out. Each step goes through the same services as a person's click: the leave through
event_service, the answers through outreach_service, the approval through approval_service
and the handoff through handoff_service, in the people's names with payload.source
SIMULATED. Their audit rows and timelines are therefore the real ones.

The clock is the reset's frozen D 21:00, so no offer times out while it plays. An example
that cannot be played as written (a later change of the rules) is logged and skipped: the
reset itself has already committed.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
)
from app.domain.enums import (
    CandidateResponse,
    CaseStatus,
    CheckInSource,
    EventType,
    OutreachStatus,
    RosterStatus,
)
from app.seed import hospital_demo
from app.services import (
    actor_service,
    approval_service,
    event_service,
    handoff_service,
    outreach_service,
)

logger = logging.getLogger(__name__)
SIMULATED = CheckInSource.SIMULATED.value
# Waves are small and the hospital pool is large: a bound that ends a reject loop if a
# rule change ever keeps a case asking forever
MAX_ANSWERS = 60


@dataclass(frozen=True)
class Example:
    """One leave on a ward's shift, and what the people then do."""

    name: str
    ward_index: int
    # Days after D and the shift type's start hour: (0, 23) is the night shift of D
    day: int
    start_hour: int
    play: Callable[[Session, int, int], None]


def _head_nurse(ward_index: int) -> int:
    return hospital_demo.STAFF_BASE + ward_index * 100 + 1


def _shift(db: Session, ward_index: int, day: int, start_hour: int) -> int:
    start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    shift_id = db.scalar(
        select(Shift.id).where(
            Shift.ward_id == hospital_demo.WARD_BASE + ward_index + 1,
            Shift.start_at == start.replace(hour=start_hour) + timedelta(days=day),
        )
    )
    if shift_id is None:
        raise LookupError(f"No hospital shift for ward {ward_index}, day {day}, {start_hour}:00")
    return shift_id


def _report_leave(db: Session, shift_id: int) -> int:
    """The first person on the roster reports leave; returns the case."""
    staff_id = db.scalar(
        select(RosterAssignment.staff_id)
        .where(
            RosterAssignment.shift_id == shift_id,
            RosterAssignment.status == RosterStatus.ASSIGNED,
        )
        .order_by(RosterAssignment.staff_id)
        .limit(1)
    )
    assert staff_id is not None
    reporter = db.get(Staff, staff_id)
    assert reporter is not None
    outcome = event_service.receive_event(
        db,
        staff_id=reporter.id,
        actor_id=actor_service.user_id(db, reporter.id),
        role_id=reporter.role_id,
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=shift_id,
        source=SIMULATED,
    )
    if outcome.case_id is None:
        raise LookupError(f"The leave on shift {shift_id} opened no case")
    return outcome.case_id


def _open_offers(db: Session, case_id: int) -> list[tuple[int, int]]:
    db.expire_all()
    rows = db.execute(
        select(CandidateOutreach.id, CandidateItem.staff_id)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.status == OutreachStatus.SENT,
        )
        .order_by(CandidateOutreach.id)
    )
    return [(outreach_id, staff_id) for outreach_id, staff_id in rows]


def _answer(db: Session, outreach_id: int, staff_id: int, response: CandidateResponse) -> None:
    outreach_service.record_response(
        db,
        staff_id=staff_id,
        actor_id=actor_service.user_id(db, staff_id),
        outreach_id=outreach_id,
        response=response,
        audit_source=SIMULATED,
    )


def _status(db: Session, case_id: int) -> CaseStatus:
    db.expire_all()
    case = db.get(StaffingCase, case_id)
    assert case is not None
    return case.status


def _accept_first(db: Session, case_id: int) -> None:
    offers = _open_offers(db, case_id)
    if not offers:
        raise LookupError(f"Case {case_id} sent no offer")
    _answer(db, *offers[0], CandidateResponse.ACCEPT)


def _reject_until_handoff(db: Session, case_id: int) -> None:
    for _ in range(MAX_ANSWERS):
        if _status(db, case_id) == CaseStatus.MANUAL_HANDOFF:
            return
        offers = _open_offers(db, case_id)
        if not offers:
            break
        _answer(db, *offers[0], CandidateResponse.REJECT)
    if _status(db, case_id) != CaseStatus.MANUAL_HANDOFF:
        raise LookupError(f"Case {case_id} did not reach MANUAL_HANDOFF")


@dataclass(frozen=True)
class _HeadNurse:
    staff_id: int
    role_id: int
    home_ward_id: int
    actor_id: int


def _as_head_nurse(db: Session, ward_index: int) -> _HeadNurse:
    head = db.get(Staff, _head_nurse(ward_index))
    assert head is not None
    return _HeadNurse(head.id, head.role_id, head.home_ward_id, actor_service.user_id(db, head.id))


def _approve(db: Session, case_id: int, ward_index: int) -> None:
    approval_id = db.scalar(
        select(ApprovalRequest.id)
        .where(ApprovalRequest.case_id == case_id, ApprovalRequest.is_pending.is_(True))
        .order_by(ApprovalRequest.id)
        .limit(1)
    )
    if approval_id is None:
        raise LookupError(f"Case {case_id} has no approval request")
    head = _as_head_nurse(db, ward_index)
    approval_service.decide(
        db,
        approval_id=approval_id,
        staff_id=head.staff_id,
        role_id=head.role_id,
        home_ward_id=head.home_ward_id,
        actor_id=head.actor_id,
        approved=True,
        audit_source=SIMULATED,
    )


def _resolved(db: Session, case_id: int, ward_index: int) -> None:
    _accept_first(db, case_id)
    _approve(db, case_id, ward_index)


def _waiting_approval(db: Session, case_id: int, ward_index: int) -> None:
    _accept_first(db, case_id)


def _offers_out(db: Session, case_id: int, ward_index: int) -> None:
    """Nothing more: the offers wait for the Demo control's accept and reject buttons."""


def _in_handoff(db: Session, case_id: int, ward_index: int) -> None:
    _reject_until_handoff(db, case_id)


def _closed(db: Session, case_id: int, ward_index: int) -> None:
    _reject_until_handoff(db, case_id)
    head = _as_head_nurse(db, ward_index)
    handoff_service.close(
        db,
        case_id=case_id,
        role_id=head.role_id,
        home_ward_id=head.home_ward_id,
        actor_id=head.actor_id,
        reason="Nobody could come; the ward runs with one nurse less tonight",
    )


def _staffed_by_hand(db: Session, case_id: int, ward_index: int) -> None:
    _reject_until_handoff(db, case_id)
    head = _as_head_nurse(db, ward_index)
    free = next(
        row
        for row in handoff_service.list_candidates(
            db, case_id=case_id, role_id=head.role_id, home_ward_id=head.home_ward_id
        )
        if not row.blocking_rules and not row.other_case_ids
    )
    handoff_service.assign(
        db,
        case_id=case_id,
        staff_id=free.staff_id,
        assigned_by=head.staff_id,
        role_id=head.role_id,
        home_ward_id=head.home_ward_id,
        actor_id=head.actor_id,
        reason="Called in by the head nurse",
    )


EXAMPLES = (
    Example("resolved", 0, 0, 23, _resolved),
    Example("manual handoff", 1, 0, 23, _in_handoff),
    Example("closed unresolved", 2, 0, 23, _closed),
    Example("staffed by hand", 3, 0, 23, _staffed_by_hand),
    Example("waiting approval", 4, 0, 23, _waiting_approval),
    Example("offers out", 0, 1, 7, _offers_out),
)


def play(db: Session) -> list[int]:
    """Play every example; return the cases that were made. Commits through the services."""
    cases: list[int] = []
    for example in EXAMPLES:
        try:
            shift_id = _shift(db, example.ward_index, example.day, example.start_hour)
            case_id = _report_leave(db, shift_id)
            example.play(db, case_id, example.ward_index)
            cases.append(case_id)
        except Exception:
            db.rollback()
            logger.exception("Demo example %r could not be played; skipped", example.name)
    return cases
