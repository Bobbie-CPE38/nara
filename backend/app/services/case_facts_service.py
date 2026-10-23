"""
The facts behind a case status, read from the database (docs/workflow.md, section 5.3).

Loads what `domain.workflow.case_status` needs. `orchestrator.recompute()` is the
caller: it turns the facts into a status with `decide_status()`.

Everything here only reads. Nothing flushes, commits or locks, on any session
setting: the public functions switch autoflush off for their queries. The caller
holds the locks of workflow.md section 6.11 for authoritative decisions and has
flushed what it wants counted. Recovery may read unlocked as a hint, then lock
and recheck before writing.

Who counts, per candidate (workflow.md section 4.1):
  * assigned: the approval request of the case is approved AND the candidate
    holds a replacement roster row on the proposed shift that is ASSIGNED or
    COMPLETED. Or a head nurse assigned the person to this case by hand: a
    MANUAL_ASSIGNMENT row of the case whose roster row is ASSIGNED or COMPLETED
    (section 6.12). A cancelled manual assignment stops counting.
  * pending: the approval request is pending AND its specific offer is still an
    ACCEPTED offer. Cancelled offers cannot reserve gap coverage.
  * open offer: unexpired SENT; the candidate is not waiting on another case.
  * paused offer: unexpired SENT; the candidate is waiting on another case.

  * returned: a person who arrived late after a NO_SHOW. The audit row
    UNAVAILABILITY_UPDATED of the case names the new roster row, which is
    ASSIGNED or COMPLETED (workflow.md 6.24). No approval is involved.

Known limits:
  * ROSTER_ASSIGNMENT has no link to a case. A replacement row for the same
    person and shift that another flow created is credited to this case too, as
    long as this case approved that person.
  * Role and skills are the person's current ones, while the gap is the snapshot
    taken when the case opened (Q19). Editing a rostered person's role or skills
    mid-case can reopen the gap of the case; it then sends another wave.
"""

from collections.abc import Collection
from dataclasses import replace
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    ManualAssignment,
    RosterAssignment,
    SafetyValidation,
    Shift,
    Staff,
    StaffingCase,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AssignmentType,
    AuditAction,
    OutreachStatus,
    RosterStatus,
)
from app.domain.workflow.case_status import CaseFacts, GapFiller, intervals_closed
from app.services import gap_service, outreach_limit_service, roster_time_service
from app.services.outreach_attempt_service import contactable_item

# A replacement keeps counting after its shift ended and the row was closed
_ON_ROSTER_STATUSES = (RosterStatus.ASSIGNED, RosterStatus.COMPLETED)


def get_case_fillers(
    db: Session, case_id: int, *, include_reserves: bool = False
) -> list[GapFiller]:
    """People already credited to this case; Wave also counts accepted reserves.

    Timed like load_case_facts() (round 4 PR T4): each filler carries the time they
    cover. An assigned person has the roster interval, a pending or reserve one
    the cover window of their candidate item; None means the whole shift. A person
    with two intervals appears twice with the same staff_id, and the same
    person, start and end appear once.
    """
    with db.no_autoflush:
        case = db.get(StaffingCase, case_id)
        if case is None:
            return []
        assigned_ids = _assigned_staff_ids(db, case_id)
        returned = _returned_spans(db, case_id)
        returned_ids = {staff_id for staff_id, _, _ in returned}
        pending_ids = _pending_staff_ids(db, case_id)
        reserve_spans = _reserve_spans(db, case_id) if include_reserves else []
        reserve_ids = {staff_id for staff_id, _, _ in reserve_spans}
        fillers = _fillers(db, assigned_ids | returned_ids | pending_ids | reserve_ids)
        timed = [
            *_timed(
                fillers,
                assigned_ids | returned_ids,
                [*_assigned_spans(db, case, assigned_ids), *returned],
            ),
            *_timed(fillers, pending_ids, _pending_spans(db, case_id)),
            *_timed(fillers, reserve_ids, reserve_spans),
        ]
        unique: dict[tuple[int, datetime | None, datetime | None], GapFiller] = {}
        for filler in timed:
            unique.setdefault((filler.staff_id, filler.start_at, filler.end_at), filler)
        return list(unique.values())


def get_assigned_fillers(db: Session, case: StaffingCase) -> list[GapFiller]:
    """The timed people who already staff the case: assigned plus late arrivals.

    The same group load_case_facts() counts as assigned, without the pending
    candidates and the reserves. The trim after a late arrival starts from it.
    """
    with db.no_autoflush:
        assigned_ids = _assigned_staff_ids(db, case.id)
        returned = _returned_spans(db, case.id)
        returned_ids = {staff_id for staff_id, _, _ in returned}
        fillers = _fillers(db, assigned_ids | returned_ids)
        return _timed(
            fillers,
            assigned_ids | returned_ids,
            [*_assigned_spans(db, case, assigned_ids), *returned],
        )


def load_fillers(db: Session, staff_ids: set[int]) -> dict[int, GapFiller]:
    """Each person with their role and full skill set, untimed. Reads only."""
    with db.no_autoflush:
        return _fillers(db, staff_ids)


def load_case_facts(db: Session, case: StaffingCase) -> CaseFacts:
    """Read the gap, the assigned and pending candidates and the offers of one case.

    The gap is the STAFFING_GAP row of the case itself, written when the case
    opened. It is not measured again against the shift (Q19). Raises
    gap_service.GapNotFoundError when the case has no gap row.

    The offers and the plan are read only while the gap is still open: a closed
    gap decides the status on its own.
    """
    with db.no_autoflush:
        case_gap = gap_service.get_case_gap(db, case.id)
        assigned_ids = _assigned_staff_ids(db, case.id)
        returned = _returned_spans(db, case.id)
        returned_ids = {staff_id for staff_id, _, _ in returned}
        pending_ids = _pending_staff_ids(db, case.id)
        fillers = _fillers(db, assigned_ids | returned_ids | pending_ids)
        # Each person counts only for the time they cover (round 4 PR T3)
        assigned = _timed(
            fillers,
            assigned_ids | returned_ids,
            [*_assigned_spans(db, case, assigned_ids), *returned],
        )
        pending = _timed(fillers, pending_ids, _pending_spans(db, case.id))

        def closed_by(group: list[GapFiller]) -> bool:
            return intervals_closed(case_gap.intervals, group)

        closed_with_pending = closed_by(assigned + pending)
        if closed_with_pending:
            return CaseFacts(
                gap_closed_by_assigned=closed_by(assigned),
                gap_closed_with_pending=True,
                has_open_offer=False,
                has_uncontacted_candidate=False,
                has_pending_approval=bool(pending_ids),
                has_paused_offer=False,
            )

        sent_ids = _sent_staff_ids(db, case.id)
        waiting_ids = _staff_waiting_on_another_case(db, case.id, sent_ids)
        return CaseFacts(
            gap_closed_by_assigned=False,
            gap_closed_with_pending=False,
            has_open_offer=bool(sent_ids - waiting_ids),
            has_uncontacted_candidate=_has_uncontacted_candidate(db, case.id),
            has_pending_approval=bool(pending_ids),
            has_paused_offer=bool(sent_ids & waiting_ids),
        )


def has_open_offer(db: Session, case_id: int) -> bool:
    """True when at least one candidate can accept an offer of the case right now.

    A SENT offer whose candidate is waiting on another case is paused, not open:
    the case may send its next wave without waiting for that candidate.
    """
    with db.no_autoflush:
        sent_ids = _sent_staff_ids(db, case_id)
        return bool(sent_ids - _staff_waiting_on_another_case(db, case_id, sent_ids))


def staff_waiting_on_another_case(db: Session, case_id: int, staff_ids: set[int]) -> set[int]:
    """Staff who accepted an offer of another running case and have no outcome yet.

    Their SENT offer on `case_id` is paused (workflow.md sections 5.1 and 6.8):
    they cannot accept it until the other case drops them, and it is not an open
    offer of this case.

    "No outcome yet" means the accepted offer is still ACCEPTED, its approval
    request is not decided, and Safety has not failed it. That covers the
    candidate in Safety, the one waiting for approval and the reserve.
      * Approved there: the outcome is known, so the offer stops pausing this
        one. An offer that clashes with the new shift is cancelled by the
        approval itself.
      * Rejected there, or failed Safety: the candidate is free again. The other
        case also sets that offer to CANCELLED, but this function does not
        depend on that write having happened.
    Offers on a stopped case never pause.
    """
    with db.no_autoflush:
        return _staff_waiting_on_another_case(db, case_id, staff_ids)


def _staff_waiting_on_another_case(db: Session, case_id: int, staff_ids: set[int]) -> set[int]:
    if not staff_ids:
        return set()
    return {
        staff_id
        for staff_id, waiting_case_id in _waiting_acceptances(db, staff_ids)
        if waiting_case_id != case_id
    }


def staff_waiting_case_ids(db: Session, staff_id: int) -> set[int]:
    """Batch offer reads: running cases holding this staff's unresolved acceptance."""
    with db.no_autoflush:
        return {case_id for _, case_id in _waiting_acceptances(db, {staff_id})}


def assigned_staff_ids(db: Session, case_id: int) -> set[int]:
    """Staff the case counts as assigned (module docstring). For read models."""
    with db.no_autoflush:
        return _assigned_staff_ids(db, case_id)


def pending_staff_ids(db: Session, case_id: int) -> set[int]:
    """Staff the case counts as waiting for approval (module docstring). For read models."""
    with db.no_autoflush:
        return _pending_staff_ids(db, case_id)


def _waiting_acceptances(db: Session, staff_ids: set[int]) -> set[tuple[int, int]]:
    decided = exists().where(
        ApprovalRequest.outreach_id == CandidateOutreach.id,
        ApprovalRequest.is_pending.is_(False),
    )
    failed_safety = exists().where(
        SafetyValidation.outreach_id == CandidateOutreach.id,
        SafetyValidation.is_passed.is_(False),
    )
    return set(
        db.execute(
            select(CandidateItem.staff_id, CandidateOutreach.case_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateItem.staff_id.in_(staff_ids),
                CandidateOutreach.status == OutreachStatus.ACCEPTED,
                StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
                ~decided,
                ~failed_safety,
            )
        )
    )


def _sent_staff_ids(db: Session, case_id: int) -> set[int]:
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(
                CandidateOutreach.case_id == case_id,
                CandidateOutreach.status == OutreachStatus.SENT,
                CandidateOutreach.expires_at > clock.now(),
            )
        )
    )


def _has_uncontacted_candidate(db: Session, case_id: int) -> bool:
    """True when the latest plan holds an uncontacted item or an unused timeout retry.

    "Latest" is the highest id (seam 1). A case without a plan has nobody to contact, and
    neither has a case past an outreach limit (round 6 PR EV6, 6.36.8): it only waits for
    the offers it already sent.
    """
    if outreach_limit_service.stop_reason(db, case_id) is not None:
        return False
    plan_id = db.scalar(
        select(CandidatePlan.id)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan_id is None:
        return False
    return (
        db.scalar(
            select(CandidateItem.id)
            .where(CandidateItem.plan_id == plan_id, contactable_item(case_id))
            .limit(1)
        )
        is not None
    )


def _assigned_staff_ids(db: Session, case_id: int) -> set[int]:
    return _assigned_staff_ids_by_case(db, [case_id])[case_id]


def assigned_staff_ids_by_case(db: Session, case_ids: Collection[int]) -> dict[int, set[int]]:
    """`assigned_staff_ids()` of several cases in two queries, for list reads."""
    with db.no_autoflush:
        return _assigned_staff_ids_by_case(db, case_ids)


def _assigned_staff_ids_by_case(db: Session, case_ids: Collection[int]) -> dict[int, set[int]]:
    """Approved and on the roster, or assigned by hand while the roster row stands."""
    result: dict[int, set[int]] = {case_id: set() for case_id in case_ids}
    if not result:
        return result
    on_roster = exists().where(
        RosterAssignment.staff_id == CandidateItem.staff_id,
        RosterAssignment.shift_id == CandidateItem.proposed_shift_id,
        RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
        RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
    )
    approved = db.execute(
        select(ApprovalRequest.case_id, CandidateItem.staff_id)
        .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
        .where(
            ApprovalRequest.case_id.in_(list(result)),
            ApprovalRequest.is_pending.is_(False),
            ApprovalRequest.is_approved.is_(True),
            on_roster,
        )
    )
    # A head nurse put the person on the shift for this case (section 6.12)
    manual = db.execute(
        select(ManualAssignment.case_id, RosterAssignment.staff_id)
        .join(ManualAssignment, ManualAssignment.roster_assignment_id == RosterAssignment.id)
        .where(
            ManualAssignment.case_id.in_(list(result)),
            RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
            RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
        )
    )
    for case_id, staff_id in (*approved, *manual):
        result[case_id].add(staff_id)
    return result


def accepted_offer_for_request() -> Exists:
    """Shared offer-link predicate for approval attempts and pending gap coverage.

    List/decision callers also check the deadline; the timeout job selects expired
    attempts. Coverage stays reserved until the job records the timeout.
    Cancellation preserves undecided request history. Its offer is the authority
    for whether that request can still be acted on; match its exact attempt, case and item.
    """
    return exists().where(
        CandidateOutreach.case_id == ApprovalRequest.case_id,
        CandidateOutreach.id == ApprovalRequest.outreach_id,
        CandidateOutreach.candidate_item_id == ApprovalRequest.candidate_item_id,
        CandidateOutreach.status == OutreachStatus.ACCEPTED,
    )


def _pending_staff_ids(db: Session, case_id: int) -> set[int]:
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
            .where(
                ApprovalRequest.case_id == case_id,
                ApprovalRequest.is_pending.is_(True),
                accepted_offer_for_request(),
            )
        )
    )


_Span = tuple[int, datetime | None, datetime | None]


def _assigned_spans(db: Session, case: StaffingCase, staff_ids: set[int]) -> list[_Span]:
    """Effective interval of each replacement row on the case's shift (actual times, T2)."""
    if not staff_ids:
        return []
    return [
        (staff_id, start_at, end_at)
        for staff_id, start_at, end_at in db.execute(
            select(
                RosterAssignment.staff_id,
                roster_time_service.start_at(),
                roster_time_service.end_at(),
            )
            .join(Shift, Shift.id == RosterAssignment.shift_id)
            .where(
                RosterAssignment.shift_id == case.shift_id,
                RosterAssignment.staff_id.in_(staff_ids),
                RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
                RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
            )
        )
    ]


def _returned_spans(db: Session, case_id: int) -> list[_Span]:
    """Late arrivals the case gets credit for (workflow.md 6.24).

    A late check-in after a NO_SHOW writes UNAVAILABILITY_UPDATED with the new
    roster row in `roster_assignment_id` and the credited case in `case_id`. The
    row came back on the roster without an approval of this case, so the person
    counts here, for the effective interval of the row, while it is ASSIGNED or
    COMPLETED. Only the case-facts readers use this: assigned_staff_ids() does not.
    """
    returned_rows = select(AuditLog.payload["roster_assignment_id"].as_integer()).where(
        AuditLog.case_id == case_id,
        AuditLog.action == AuditAction.UNAVAILABILITY_UPDATED,
    )
    return [
        (staff_id, start_at, end_at)
        for staff_id, start_at, end_at in db.execute(
            select(
                RosterAssignment.staff_id,
                roster_time_service.start_at(),
                roster_time_service.end_at(),
            )
            .join(Shift, Shift.id == RosterAssignment.shift_id)
            .where(
                RosterAssignment.id.in_(returned_rows),
                RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
            )
        )
    ]


def _pending_spans(db: Session, case_id: int) -> list[_Span]:
    """Cover window of each pending candidate item; NULL means the whole shift (T1)."""
    return [
        (staff_id, start_at, end_at)
        for staff_id, start_at, end_at in db.execute(
            select(CandidateItem.staff_id, CandidateItem.cover_start_at, CandidateItem.cover_end_at)
            .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
            .where(
                ApprovalRequest.case_id == case_id,
                ApprovalRequest.is_pending.is_(True),
                accepted_offer_for_request(),
            )
        )
    ]


def _reserve_spans(db: Session, case_id: int) -> list[_Span]:
    """Cover window of each accepted offer of the case; NULL means the whole shift."""
    return [
        (staff_id, start_at, end_at)
        for staff_id, start_at, end_at in db.execute(
            select(CandidateItem.staff_id, CandidateItem.cover_start_at, CandidateItem.cover_end_at)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(
                CandidateOutreach.case_id == case_id,
                CandidateOutreach.status == OutreachStatus.ACCEPTED,
            )
        )
    ]


def _timed(
    fillers: dict[int, GapFiller], staff_ids: set[int], spans: list[_Span]
) -> list[GapFiller]:
    """One filler per span; someone in the group without a span covers the whole shift."""
    timed = [
        replace(fillers[staff_id], start_at=start_at, end_at=end_at)
        for staff_id, start_at, end_at in spans
        if staff_id in staff_ids
    ]
    spanned = {filler.staff_id for filler in timed}
    timed.extend(fillers[staff_id] for staff_id in staff_ids - spanned)
    return timed


def _fillers(db: Session, staff_ids: set[int]) -> dict[int, GapFiller]:
    """Each person with their role and full skill set, keyed by staff ID."""
    if not staff_ids:
        return {}
    skills = gap_service.load_skill_sets(db, staff_ids)
    return {
        staff_id: GapFiller(
            staff_id=staff_id, role_id=role_id, skill_ids=skills.get(staff_id, frozenset())
        )
        for staff_id, role_id in db.execute(
            select(Staff.id, Staff.role_id).where(Staff.id.in_(staff_ids))
        )
    }
