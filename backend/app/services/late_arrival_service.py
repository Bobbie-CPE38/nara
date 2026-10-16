"""Late arrival of a nurse whose row a NO_SHOW cancelled (docs/workflow.md, section 6.24).

restore() is the one step all three timings share: a check-in before stage 1, a
check-in while the NO_SHOW event waits, and a check-in after stage 2. It gives
the person a new ASSIGNED row from check_in_at, made by the one writer of runtime
roster rows (roster_service). The caller holds the locks and owns the commit.

arrive_after_no_show() is the path of a check-in after stage 2, when a case may
already be running: it credits the person to that case and trims what the case
no longer needs.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffUnavailability,
)
from app.domain.enums import (
    TERMINAL_CASE_STATUSES,
    WAITING_CASE_STATUSES,
    ActorName,
    AuditAction,
    EntityType,
    OutreachStatus,
    RosterStatus,
)
from app.domain.workflow.case_status import GapFiller, choose_kept
from app.services import (
    actor_service,
    attendance_service,
    audit_service,
    case_facts_service,
    gap_service,
    merge_window_service,
    outreach_service,
    roster_service,
)

logger = logging.getLogger(__name__)

# The reason an offer view shows for an offer the late arrival made surplus
NO_LONGER_NEEDED = "NO_LONGER_NEEDED"


def restore(db: Session, *, original: RosterAssignment, check_in_at: datetime) -> RosterAssignment:
    """Create the row for the rest of the interval of `original`, from `check_in_at`.

    `original` must already be CANCELLED and `check_in_at` before its effective
    end (a check-in at or after the end is refused earlier, with a 422). Flushes,
    never commits. The new row gets a Handover only when `original` had one.
    """
    if original.status != RosterStatus.CANCELLED:
        raise ValueError("Late arrival requires a cancelled roster row")
    shift = db.get_one(Shift, original.shift_id)
    if check_in_at >= attendance_service.effective_end_at(original, shift):
        raise ValueError("Late arrival must be before the end of the roster row")
    return roster_service.restore_late_arrival(
        db,
        original=original,
        check_in_at=check_in_at,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
    )


def credited_case(db: Session, shift_id: int) -> StaffingCase | None:
    """The case a late arrival is credited to: the latest case of the shift still open.

    Not RESOLVED, UNRESOLVED or FAILED. MANUAL_HANDOFF counts, so a head nurse
    sees the person in its timeline. None when the shift has no such case.
    """
    return db.scalar(
        select(StaffingCase)
        .where(
            StaffingCase.shift_id == shift_id,
            StaffingCase.status.not_in(list(TERMINAL_CASE_STATUSES)),
        )
        .order_by(StaffingCase.id.desc())
        .limit(1)
    )


def arrive_after_no_show(
    db: Session,
    *,
    shift: Shift,
    original: RosterAssignment,
    unavailability: StaffUnavailability,
    check_in_at: datetime,
) -> RosterAssignment:
    """A check-in after stage 2: end the absence, restore the row, tell the case. Commits.

    The caller holds every lock of workflow.md 6.11 for this path (check_in()):
    shift, rows, requests, offers, case and Staff, then the absence. Steps: the
    absence now ends at the arrival, the row is restored from check_in_at, and
    UNAVAILABILITY_UPDATED names the new row under the credited case. That audit
    row is how the case counts the person (case_facts_service._returned_spans).
    A waiting case then recomputes with trim() as its prepare step; any other
    case, or none, only commits. People whose offers were cancelled are told after
    the commit, so their other cases can leave the pause.
    """
    previous_end_at = unavailability.end_at
    unavailability.end_at = check_in_at
    restored = restore(db, original=original, check_in_at=check_in_at)
    case = credited_case(db, shift.id)
    audit_service.log(
        db,
        case_id=None if case is None else case.id,
        actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        action=AuditAction.UNAVAILABILITY_UPDATED,
        entity_type=EntityType.STAFF_UNAVAILABILITY,
        entity_id=unavailability.id,
        payload={
            "unavailability_id": unavailability.id,
            "staff_id": unavailability.staff_id,
            "previous_end_at": None
            if previous_end_at is None
            else merge_window_service.iso(previous_end_at),
            "end_at": merge_window_service.iso(check_in_at),
            "roster_assignment_id": restored.id,
            "late_arrival": True,
        },
    )
    # Save the IDs: every commit and rollback below expires the ORM objects
    case_id = None if case is None else case.id
    late_staff_id = original.staff_id
    cancelled_staff: list[int] = []
    if case is not None and case.status in WAITING_CASE_STATUSES:
        # Imported here: the orchestrator reaches this module through the services
        from app.workflow import orchestrator

        def prepare(db: Session, case: StaffingCase) -> None:
            cancelled_staff.extend(trim(db, case, late_staff_id=late_staff_id))

        orchestrator.recompute(db, case.id, prepare=prepare)
    else:
        db.commit()
    if case_id is not None:
        for staff_id in sorted(set(cancelled_staff)):
            try:
                outreach_service.recompute_affected_cases(
                    db, staff_id=staff_id, own_case_id=case_id
                )
            except Exception:
                db.rollback()
                logger.exception("Staff %s needs a foreign-case recompute retry", staff_id)
    return restored


def trim(db: Session, case: StaffingCase, *, late_staff_id: int) -> list[int]:
    """Cancel the offers and requests the case no longer needs. No commit.

    Runs as the prepare step of orchestrator.recompute(), so every lock is held.
    The people already on the case (assigned plus late arrivals) are the base.
    choose_kept() decides which pending requests and unanswered offers still
    lower the open gap; coverage is chosen first, so a request that covers only
    the first half loses to an offer that covers the missing second half. Each
    one not kept has its offer cancelled (a request stays as history) and gets
    OFFER_CANCELLED_NOT_NEEDED. An expired SENT offer is left to the timeout job.
    Returns the staff IDs of the cancelled offers.
    """
    intervals = gap_service.get_case_gap(db, case.id).intervals
    base = case_facts_service.get_assigned_fillers(db, case)
    candidates = _trim_candidates(db, case)
    people = case_facts_service.load_fillers(db, {item.staff_id for _, _, item in candidates})
    kept = choose_kept(
        intervals,
        base,
        [
            (
                outreach.id,
                GapFiller(
                    staff_id=item.staff_id,
                    role_id=people[item.staff_id].role_id,
                    skill_ids=people[item.staff_id].skill_ids,
                    start_at=item.cover_start_at,
                    end_at=item.cover_end_at,
                ),
            )
            for outreach, _, item in candidates
        ],
    )
    system = actor_service.component_id(db, ActorName.SYSTEM)
    cancelled_staff: list[int] = []
    for outreach, request, item in candidates:
        if outreach.id in kept:
            continue
        outreach_service.cancel_offer(db, outreach)
        audit_service.log(
            db,
            case_id=case.id,
            actor_id=system,
            action=AuditAction.OFFER_CANCELLED_NOT_NEEDED,
            entity_type=EntityType.CANDIDATE_OUTREACH,
            entity_id=outreach.id,
            # Singular `cancelled_outreach_id`: _cancellation_reasons() reads it
            # only together with this action
            payload={
                "cancelled_outreach_id": outreach.id,
                "approval_request_id": None if request is None else request.id,
                "staff_id": item.staff_id,
                "late_staff_id": late_staff_id,
                "reason": NO_LONGER_NEEDED,
            },
        )
        cancelled_staff.append(item.staff_id)
    db.flush()
    return cancelled_staff


def _trim_candidates(
    db: Session, case: StaffingCase
) -> list[tuple[CandidateOutreach, ApprovalRequest | None, CandidateItem]]:
    """Pending requests with an ACCEPTED offer, then unexpired SENT offers (open or paused).

    That is the order choose_kept() prefers on a tie: a request before an offer,
    then the better rank, then the lower offer ID. An accepted reserve without a
    request is not a candidate here and stays as it is.
    """
    requested = db.execute(
        select(CandidateOutreach, ApprovalRequest, CandidateItem)
        .join(ApprovalRequest, ApprovalRequest.outreach_id == CandidateOutreach.id)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            ApprovalRequest.case_id == case.id,
            ApprovalRequest.is_pending.is_(True),
            # The same link as case_facts_service.accepted_offer_for_request()
            CandidateOutreach.case_id == ApprovalRequest.case_id,
            CandidateOutreach.candidate_item_id == ApprovalRequest.candidate_item_id,
            CandidateOutreach.status == OutreachStatus.ACCEPTED,
        )
        .order_by(CandidateItem.rank, CandidateOutreach.id)
        .execution_options(populate_existing=True)
    ).all()
    sent = db.execute(
        select(CandidateOutreach, CandidateItem)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            CandidateOutreach.case_id == case.id,
            CandidateOutreach.status == OutreachStatus.SENT,
            CandidateOutreach.expires_at > clock.now(),
        )
        .order_by(CandidateItem.rank, CandidateOutreach.id)
        .execution_options(populate_existing=True)
    ).all()
    return [
        *((outreach, request, item) for outreach, request, item in requested),
        *((outreach, None, item) for outreach, item in sent),
    ]
