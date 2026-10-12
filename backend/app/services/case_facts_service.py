"""
The facts behind a case status, read from the database (docs/workflow.md, section 5.3).

Loads what `domain.workflow.case_status` needs. `orchestrator.recompute()` is the
caller: it turns the facts into a status with `decide_status()`.

Everything here only reads. Nothing flushes, commits or locks, on any session
setting: the public functions switch autoflush off for their queries. The caller
holds the locks of workflow.md section 6.11 and has flushed what it wants counted.

Who counts, per candidate (workflow.md section 4.1):
  * assigned: the approval request of the case is approved AND the candidate
    holds a replacement roster row on the proposed shift that is ASSIGNED or
    COMPLETED.
  * pending: the approval request of the case is still pending.
  * open offer: the offer of the case is SENT and its candidate is not waiting
    on another case.
  * paused offer: the offer of the case is SENT and its candidate is waiting on
    another case.

Known limits:
  * ROSTER_ASSIGNMENT has no link to a case. A replacement row for the same
    person and shift that another flow created is credited to this case too, as
    long as this case approved that person.
  * Role and skills are the person's current ones, while the gap is the snapshot
    taken when the case opened (Q19). Editing a rostered person's role or skills
    mid-case can reopen the gap of the case; it then sends another wave.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    RosterAssignment,
    SafetyValidation,
    Staff,
    StaffingCase,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AssignmentType,
    OutreachStatus,
    RosterStatus,
)
from app.domain.workflow.case_status import CaseFacts, GapFiller, gap_closed
from app.services import gap_service

# A replacement keeps counting after its shift ended and the row was closed
_ON_ROSTER_STATUSES = (RosterStatus.ASSIGNED, RosterStatus.COMPLETED)


def get_case_fillers(
    db: Session, case_id: int, *, include_reserves: bool = False
) -> list[GapFiller]:
    """People already credited to this case; Wave also counts accepted reserves."""
    with db.no_autoflush:
        staff_ids = _assigned_staff_ids(db, case_id) | _pending_staff_ids(db, case_id)
        if include_reserves:
            staff_ids.update(
                db.scalars(
                    select(CandidateItem.staff_id)
                    .join(
                        CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id
                    )
                    .where(
                        CandidateOutreach.case_id == case_id,
                        CandidateOutreach.status == OutreachStatus.ACCEPTED,
                    )
                )
            )
        return list(_fillers(db, staff_ids).values())


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
        pending_ids = _pending_staff_ids(db, case.id)
        fillers = _fillers(db, assigned_ids | pending_ids)

        def closed_by(staff_ids: set[int]) -> bool:
            return gap_closed(
                headcount_gap=case_gap.headcount_gap,
                role_gaps=case_gap.role_gaps,
                skill_gaps=case_gap.skill_gaps,
                fillers=(fillers[staff_id] for staff_id in staff_ids),
            )

        closed_with_pending = closed_by(assigned_ids | pending_ids)
        if closed_with_pending:
            return CaseFacts(
                gap_closed_by_assigned=closed_by(assigned_ids),
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
    decided = exists().where(
        ApprovalRequest.candidate_item_id == CandidateOutreach.candidate_item_id,
        ApprovalRequest.is_pending.is_(False),
    )
    failed_safety = exists().where(
        SafetyValidation.candidate_item_id == CandidateOutreach.candidate_item_id,
        SafetyValidation.is_passed.is_(False),
    )
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateItem.staff_id.in_(staff_ids),
                CandidateOutreach.case_id != case_id,
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
            )
        )
    )


def _has_uncontacted_candidate(db: Session, case_id: int) -> bool:
    """True when the latest plan of the case holds an item without an offer of the case.

    "Latest" is the highest id (seam 1). A case without a plan has nobody to contact.
    """
    plan_id = db.scalar(
        select(CandidatePlan.id)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan_id is None:
        return False
    contacted = exists().where(
        CandidateOutreach.candidate_item_id == CandidateItem.id,
        CandidateOutreach.case_id == case_id,
    )
    return (
        db.scalar(
            select(CandidateItem.id).where(CandidateItem.plan_id == plan_id, ~contacted).limit(1)
        )
        is not None
    )


def _assigned_staff_ids(db: Session, case_id: int) -> set[int]:
    on_roster = exists().where(
        RosterAssignment.staff_id == CandidateItem.staff_id,
        RosterAssignment.shift_id == CandidateItem.proposed_shift_id,
        RosterAssignment.status.in_(_ON_ROSTER_STATUSES),
        RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
    )
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
            .where(
                ApprovalRequest.case_id == case_id,
                ApprovalRequest.is_pending.is_(False),
                ApprovalRequest.is_approved.is_(True),
                on_roster,
            )
        )
    )


def _pending_staff_ids(db: Session, case_id: int) -> set[int]:
    return set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
            .where(ApprovalRequest.case_id == case_id, ApprovalRequest.is_pending.is_(True))
        )
    )


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
