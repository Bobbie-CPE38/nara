"""
Workflow orchestrator (docs/workflow.md, sections 5 and 6.2).

The only code that changes STAFFING_CASES.status (D3). Two entry points:

  * `advance(db, case_id)` runs handlers from the case's current status until
    it reaches a wait point or a status where automation stops.
  * `resume(db, case_id, next_status)` leaves a wait point after an outside
    decision (the candidate answered, the approver decided), then continues
    like `advance()`.

Rules:
  * Every status change is checked against ALLOWED_TRANSITIONS and writes one
    CASE_STATUS_CHANGED audit row with the workflow_orchestrator actor.
  * One round commits once, at the end (D4).
  * A round that raises is rolled back to its start with a savepoint. The
    caller's earlier work in the same transaction is kept (the event, the case,
    the recorded answer). The case then becomes FAILED with a WORKFLOW_FAILED
    audit row, and that is committed (D11). The exception is logged, not
    re-raised: the caller sees the result in the case status. The one exception:
    if writing the FAILED status itself fails (for example the orchestrator
    actor is missing), that error escapes and nothing is committed.
"""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StaffingCase
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    ActorName,
    AuditAction,
    CaseStatus,
    EntityType,
)
from app.domain.errors import CaseNotFoundError
from app.domain.workflow.transitions import InvalidTransitionError, assert_transition
from app.services import actor_service, audit_service
from app.workflow.handlers import (
    assess_staffing,
    contact_candidate,
    execute_assignment,
    intake_event,
    optimize,
    validate_safety,
)
from app.workflow.handlers.base import HandlerResult

logger = logging.getLogger(__name__)

Handler = Callable[[Session, StaffingCase], HandlerResult]

# The handler that runs while a case is in each status (docs/workflow.md 5.1).
# Wait points and stopped statuses have no handler.
HANDLERS: dict[CaseStatus, Handler] = {
    CaseStatus.OPEN: intake_event.handle,
    CaseStatus.ASSESSING: assess_staffing.handle,
    CaseStatus.OPTIMIZING: optimize.handle,
    CaseStatus.OUTREACH: contact_candidate.handle,
    CaseStatus.SAFETY_VALIDATION: validate_safety.handle,
    CaseStatus.EXECUTING: execute_assignment.handle,
}

# A correct workflow visits each status at most once per round
_MAX_STEPS = len(CaseStatus)


class WorkflowError(RuntimeError):
    """A handler broke the contract in docs/workflow.md section 6.1."""


def advance(db: Session, case_id: int) -> None:
    """Run the case forward until a wait point or a stopped status, then commit.

    Does nothing but commit when the case is already waiting or stopped.
    """
    case = _load_for_update(db, case_id)
    _run_round(db, case)


def resume(db: Session, case_id: int, next_status: CaseStatus) -> None:
    """Leave a wait point for `next_status`, then continue like `advance()`.

    Raises InvalidTransitionError, without touching the case, when it is not at
    a wait point or the transition is not allowed. A repeated request (a second
    ACCEPT, a double click on Approve) lands here, so it must not fail the case.
    The caller's own pending changes were flushed by then: after this error the
    caller must not commit. Answer 409 and let the session roll back.
    """
    case = _load_for_update(db, case_id)
    if case.status not in WAITING_CASE_STATUSES:
        raise InvalidTransitionError(
            f"Case {case.id} is {case.status.value}, not at a wait point: cannot resume"
        )
    # FAILED means the system broke (D11). Only _mark_failed sets it, together
    # with its WORKFLOW_FAILED row; an outside decision can never ask for it
    if next_status is CaseStatus.FAILED:
        raise InvalidTransitionError(f"Case {case.id} cannot be resumed to FAILED")
    assert_transition(case.status, next_status)
    _change_status(db, case, next_status)
    _run_round(db, case)


def _load_for_update(db: Session, case_id: int) -> StaffingCase:
    # SessionLocal has autoflush off: send the caller's pending changes first,
    # so the fresh read below cannot overwrite them
    db.flush()
    # Row lock: a second request for the same case waits for this round.
    # FOR NO KEY UPDATE, not FOR UPDATE: an audit row a caller already inserted
    # for this case holds KEY SHARE on it through the foreign key. Two such
    # callers asking for FOR UPDATE would deadlock
    case = db.scalar(
        select(StaffingCase)
        .where(StaffingCase.id == case_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if case is None:
        raise CaseNotFoundError(f"No case {case_id}")
    return case


def _run_round(db: Session, case: StaffingCase) -> None:
    failed_at = case.status
    try:
        # Savepoint: a failure undoes this round only, not the caller's work
        with db.begin_nested():
            for _ in range(_MAX_STEPS):
                failed_at = case.status
                if not _run_step(db, case):
                    break
            else:
                raise WorkflowError(f"Case {case.id} did not stop after {_MAX_STEPS} steps")
    except Exception as error:
        logger.exception("Workflow failed for case %s at %s", case.id, failed_at.value)
        _mark_failed(db, case, failed_at=failed_at, error=error)
    db.commit()


def _run_step(db: Session, case: StaffingCase) -> bool:
    """Run the handler for the current status. Return False when the round is over."""
    current = case.status
    if current in WAITING_CASE_STATUSES or current in AUTOMATION_STOPPED_STATUSES:
        return False
    handler = HANDLERS.get(current)
    if handler is None:
        raise WorkflowError(f"No handler for status {current.value}")

    result = handler(db, case)

    if case.status != current:
        raise WorkflowError(f"Handler for {current.value} changed case.status itself")
    # A handler reports a failure by raising, so that _mark_failed writes
    # WORKFLOW_FAILED. Returning FAILED would skip that row
    if result.next_status is CaseStatus.FAILED:
        raise WorkflowError(f"Handler for {current.value} returned FAILED instead of raising")
    waits = result.next_status in WAITING_CASE_STATUSES
    if result.wait != waits:
        raise WorkflowError(
            f"Handler for {current.value} returned wait={result.wait} "
            f"with next_status {result.next_status.value}"
        )
    assert_transition(current, result.next_status)
    _change_status(db, case, result.next_status)
    return not result.wait


def _change_status(db: Session, case: StaffingCase, next_status: CaseStatus) -> None:
    previous = case.status
    case.status = next_status
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.CASE_STATUS_CHANGED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        payload={"from": previous.value, "to": next_status.value},
    )


def _mark_failed(
    db: Session, case: StaffingCase, *, failed_at: CaseStatus, error: Exception
) -> None:
    # The savepoint rollback restored the status the round started from
    started_at = case.status
    assert_transition(started_at, CaseStatus.FAILED)
    _change_status(db, case, CaseStatus.FAILED)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.WORKFLOW_FAILED,
        entity_type=EntityType.STAFFING_CASES,
        entity_id=case.id,
        # The error text can carry SQL parameters (names, hashes), so only its
        # type is stored. The full traceback is in the server log
        payload={
            "from": started_at.value,
            "failed_at": failed_at.value,
            "error_type": type(error).__name__,
        },
    )
