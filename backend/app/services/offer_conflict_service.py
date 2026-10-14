"""Offers a new roster row makes unsafe (docs/workflow.md, sections 6.8 and 6.12).

When a person gets a shift, their offers on other cases may no longer pass the
scheduling rules. One function decides which offers that is and cancels them,
for both ways a person gets a shift: an approval and a manual assignment by a
head nurse.
"""

from collections.abc import Sequence
from typing import Literal

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidateOutreach, RosterAssignment, Shift, StaffingCase
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    AuditAction,
    EntityType,
    OutreachStatus,
)
from app.services import audit_service, hard_rule_service, outreach_service

# What put the person on the shift. Stored in the audit payload
AssignmentSource = Literal["APPROVAL", "MANUAL_ASSIGNMENT"]

_SCHEDULING_RULES = frozenset(
    {
        HardRuleCode.ALREADY_ON_SHIFT,
        HardRuleCode.SHIFT_CONFLICT,
        HardRuleCode.INSUFFICIENT_REST,
        HardRuleCode.DAILY_HOURS_EXCEEDED,
        HardRuleCode.WEEKLY_HOURS_EXCEEDED,
        HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,
    }
)


def conflicting_offers(
    db: Session, *, case_id: int, staff_id: int, offers: Sequence[CandidateOutreach]
) -> list[CandidateOutreach]:
    """The person's live offers on other running cases that the roster now forbids.

    Call after the new roster row is flushed: the offers are judged against it.
    `offers` are rows the caller already locked. Offers of other people, of this
    case and of stopped cases are ignored.

    A SENT offer past its deadline is left out on purpose. Only the timeout job
    may close it, so that it ends as TIMEOUT with its OFFER_TIMEOUT audit row
    and not as CANCELLED (the rule of execute_assignment, round 1 PR O).
    """
    now = clock.now()
    conflicting = []
    for row in offers:
        if row.case_id == case_id or row.status not in {
            OutreachStatus.SENT,
            OutreachStatus.ACCEPTED,
        }:
            continue
        if row.status is OutreachStatus.SENT and (row.expires_at is None or row.expires_at <= now):
            continue
        candidate = db.get(CandidateItem, row.candidate_item_id)
        if candidate is None or candidate.staff_id != staff_id:
            continue
        foreign_case = db.get(StaffingCase, row.case_id)
        if foreign_case is None or foreign_case.status in AUTOMATION_STOPPED_STATUSES:
            continue
        shift = db.get(Shift, candidate.proposed_shift_id)
        if shift is None:
            raise LookupError(f"No shift {candidate.proposed_shift_id}")
        check = hard_rule_service.check_items(db, shift=shift, items=[candidate])[candidate.id]
        if _SCHEDULING_RULES.intersection(check.result.failed_rules):
            conflicting.append(row)
    return conflicting


def cancel_conflicting_offers(
    db: Session,
    *,
    case: StaffingCase,
    assignment: RosterAssignment,
    offers: Sequence[CandidateOutreach],
    actor_id: int,
    source: AssignmentSource,
) -> list[CandidateOutreach]:
    """Cancel the offers `assignment` makes unsafe and say why in the case that lost each.

    This is not execution validation of the assigned person (Q38). The caller
    holds the offer locks and writes `cancelled_outreach_ids` in its own audit
    row of `case`. Each cancelled offer also gets OFFER_CANCELLED_BY_ASSIGNMENT
    in its own case (R2-Q56): without it, whoever opens that case sees a
    cancelled offer and no cause. Returns the cancelled rows; the caller
    recomputes their cases after commit.
    """
    cancelled = conflicting_offers(db, case_id=case.id, staff_id=assignment.staff_id, offers=offers)
    for row in cancelled:
        outreach_service.cancel_offer(db, row)
        audit_service.log(
            db,
            case_id=row.case_id,
            actor_id=actor_id,
            action=AuditAction.OFFER_CANCELLED_BY_ASSIGNMENT,
            entity_type=EntityType.CANDIDATE_OUTREACH,
            entity_id=row.id,
            # Singular on purpose. outreach_service._cancellation_reasons() looks
            # for `cancelled_outreach_ids` and `outreach_id`, and the latest row
            # wins: either name here would replace CONFLICTING_ASSIGNMENT
            payload={
                "cancelled_outreach_id": row.id,
                "staff_id": assignment.staff_id,
                "by_case_id": case.id,
                "assignment_id": assignment.id,
                "source": source,
            },
        )
    db.flush()
    return cancelled
