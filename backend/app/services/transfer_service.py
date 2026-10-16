"""The checks at the real move of a transfer, whole-shift or mid-shift (docs/workflow.md 6.19).

The move happens at transfer_at = max(destination start, source row start, the time of
the final approval). The source row stays ASSIGNED and ends there, unless the move is
at its start, which cancels it (roster_service.create_transfer).

Runs inside the final approval's decision transaction, after lock_approval_attempt
took its locks. A check that fails never raises: a raise inside the orchestrator's
prepare callback would mark the case FAILED (D11). The failure is returned and
audited, and the caller cancels the offer so the case goes on.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest, CandidateItem, RosterAssignment, Shift, StaffingCase
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import AuditAction, EntityType, RosterStatus, TransferFailureReason
from app.services import audit_service, hard_rule_service, roster_service, roster_time_service

# Rules that depend on the roster as it is now. The others are not rechecked at
# execution (Q38): the person already passed them in Safety.
TIME_RULES = (
    HardRuleCode.SHIFT_CONFLICT,
    HardRuleCode.INSUFFICIENT_REST,
    HardRuleCode.DAILY_HOURS_EXCEEDED,
    HardRuleCode.WEEKLY_HOURS_EXCEEDED,
    HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,
)


@dataclass(frozen=True)
class TransferResult:
    """The moved rows, or the reason the move was refused."""

    assignment: RosterAssignment | None
    source: RosterAssignment | None
    transfer_at: datetime | None = None
    reason: TransferFailureReason | None = None
    failed_rules: tuple[str, ...] = ()


def execute(
    db: Session,
    case: StaffingCase,
    *,
    approval: ApprovalRequest,
    item: CandidateItem,
    actor_id: int,
) -> TransferResult:
    """Check the move at its real time and write it, or audit why it was refused.

    Caller holds Ward, both Shifts, Request, Offer, case and Staff locks. On
    success the caller writes ASSIGNMENT_TRANSFERRED; on failure this function
    writes TRANSFER_CHECK_FAILED and nothing is moved.
    """
    assert item.source_assignment_id is not None
    assert approval.decided_at is not None
    source = db.get(RosterAssignment, item.source_assignment_id, populate_existing=True)
    dest = db.get(Shift, item.proposed_shift_id)
    if source is None or dest is None:
        raise LookupError("Transfer source or destination is missing")
    source_shift = db.get(Shift, source.shift_id)
    if source_shift is None:
        raise LookupError(f"No shift {source.shift_id}")

    # The row's own times (actual times fall back to the shift's), as in the Pool
    source_start, source_end = roster_time_service.effective_interval(
        shift_start_at=source_shift.start_at,
        shift_end_at=source_shift.end_at,
        actual_start_at=source.actual_start_at,
        actual_end_at=source.actual_end_at,
    )
    transfer_at = max(dest.start_at, source_start, approval.decided_at)
    reason: TransferFailureReason | None = None
    failed_rules: tuple[str, ...] = ()
    if transfer_at >= min(source_end, dest.end_at):
        reason = TransferFailureReason.DESTINATION_WINDOW_PASSED
    elif source.status != RosterStatus.ASSIGNED:
        reason = TransferFailureReason.SOURCE_COVERAGE_LOST
    else:
        db.flush()
        # The cover starts at the real move time, not at the planned one
        failed = set(
            hard_rule_service.check_items(
                db, shift=dest, items=[item], move_at={item.id: transfer_at}
            )[item.id].result.failed_rules
        )
        if HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in failed:
            reason = TransferFailureReason.SOURCE_COVERAGE_LOST
        elif failed.intersection(TIME_RULES):
            reason = TransferFailureReason.HARD_RULE_FAILED
            failed_rules = tuple(
                code.value for code in HardRuleCode if code in failed & set(TIME_RULES)
            )

    if reason is not None:
        assert approval.outreach_id is not None
        audit_service.log(
            db,
            case_id=case.id,
            actor_id=actor_id,
            action=AuditAction.TRANSFER_CHECK_FAILED,
            entity_type=EntityType.APPROVAL_REQUEST,
            entity_id=approval.id,
            payload={
                "approval_id": approval.id,
                "outreach_id": approval.outreach_id,
                "staff_id": item.staff_id,
                "reason": reason.value,
                "failed_rules": list(failed_rules),
            },
        )
        return TransferResult(None, None, transfer_at, reason, failed_rules)

    assignment, moved_source = roster_service.create_transfer(
        db, case, approval=approval, transfer_at=transfer_at
    )
    return TransferResult(assignment, moved_source, transfer_at)
