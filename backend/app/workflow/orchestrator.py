"""
Workflow orchestrator (docs/workflow.md, sections 5 and 6.2).

The only code that changes STAFFING_CASES.status (D3). Four entry points:

  * `advance(db, case_id)` runs handlers from the case's current status until
    it reaches a wait point or a status where automation stops.
  * `resume(db, case_id, next_status)` leaves a wait point after an outside
    decision (the candidate answered, the approver decided), then continues
    like `advance()`. The Skeleton callers use it; round 1 replaces them.
  * `recompute(db, case_id)` leaves a wait point for the status computed from
    the remaining gap and the open offers (section 5.3), then continues like
    `advance()`. The caller does not name the next status.
  * `leave_handoff(db, case_id, next_status)` takes T8 or T9 out of
    MANUAL_HANDOFF (section 6.12). No handler runs and it does not commit:
    the caller's transaction owns the change.

Rules:
  * Every status change is checked against ALLOWED_TRANSITIONS and writes one
    CASE_STATUS_CHANGED audit row with the workflow_orchestrator actor.
  * One round commits once, at the end (D4).
  * The walk from one handler to the next inside a round is a LangGraph graph
    (section 6.23): one node per status in HANDLERS, edges from
    ALLOWED_TRANSITIONS. The case row stays the only record of where a case is
    (D1): the graph has no checkpointer and keeps no state of its own. The
    savepoint, the commit, D11 and the LINE dispatch stay outside the graph.
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
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
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

# Re-exported on purpose (`X as X`): other modules still reach this error as
# orchestrator.CaseNotFoundError, and strict mypy rejects a plain import there.
# Import it from app.domain.errors in new code; drop this once nothing uses the old path
from app.domain.errors import CaseNotFoundError as CaseNotFoundError
from app.domain.workflow.case_status import decide_status
from app.domain.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    assert_transition,
)
from app.services import actor_service, audit_service, case_facts_service
from app.workflow.handlers import (
    assess_staffing,
    contact_candidate,
    execute_assignment,
    intake_event,
    optimize,
)
from app.workflow.handlers.base import HandlerResult

logger = logging.getLogger(__name__)

Handler = Callable[[Session, StaffingCase], HandlerResult]

# The handler that runs while a case is in each status (docs/workflow.md 5.1).
# Wait points and stopped statuses have no handler. Neither has SAFETY_VALIDATION:
# it stays in the enum, but Safety runs per candidate and no case enters it (Q31).
HANDLERS: dict[CaseStatus, Handler] = {
    CaseStatus.OPEN: intake_event.handle,
    CaseStatus.ASSESSING: assess_staffing.handle,
    CaseStatus.OPTIMIZING: optimize.handle,
    CaseStatus.OUTREACH: contact_candidate.handle,
    CaseStatus.EXECUTING: execute_assignment.handle,
}

# Upper bound on handler steps in one round. A round runs each handler at most
# once: the edges that re-enter OUTREACH (T1, T4) start at a wait point, and
# OUTREACH ends at a wait point or at MANUAL_HANDOFF, where the round stops.
# A wait point can still appear twice in the status changes of one round, as its
# start and its end (WAITING_APPROVAL -> OUTREACH -> WAITING_APPROVAL through T4
# and T7). The move recompute() makes before the first handler is not a step
_MAX_STEPS = len(CaseStatus)


class WorkflowError(RuntimeError):
    """A handler broke the contract in docs/workflow.md section 6.1."""


@dataclass
class _Round:
    """What one round's graph run works on. Lives for one call of _run_round()."""

    db: Session
    case: StaffingCase
    # The status of the step that is running, for the WORKFLOW_FAILED row
    failed_at: CaseStatus


class _GraphState(TypedDict):
    # The graph keeps nothing of the case (D1): the case row is the state.
    # LangGraph needs at least one channel; this one counts steps and nothing reads it
    steps: int


def _round_of(config: RunnableConfig) -> _Round:
    run: _Round = config["configurable"]["round"]
    return run


def _step_node(state: _GraphState, config: RunnableConfig) -> _GraphState:
    run = _round_of(config)
    run.failed_at = run.case.status
    _run_step(run.db, run.case)
    return {"steps": state["steps"] + 1}


def _next_node(state: _GraphState, config: RunnableConfig) -> str:
    """The node for the case's status now, or END when the round is over."""
    run = _round_of(config)
    current = run.case.status
    if current in WAITING_CASE_STATUSES or current in AUTOMATION_STOPPED_STATUSES:
        return END
    if current not in _GRAPH_NODES:
        # The same error _run_step() raises for a status without a handler
        run.failed_at = current
        raise WorkflowError(f"No handler for status {current.value}")
    return current.value


def _build_graph() -> CompiledStateGraph[_GraphState, None, _GraphState, _GraphState]:
    graph = StateGraph(_GraphState)
    for status in _GRAPH_NODES:
        graph.add_node(status.value, _step_node)
    graph.add_conditional_edges(START, _next_node, [s.value for s in _GRAPH_NODES] + [END])
    for status in _GRAPH_NODES:
        targets = [s.value for s in ALLOWED_TRANSITIONS[status] if s in _GRAPH_NODES]
        graph.add_conditional_edges(status.value, _next_node, [*sorted(targets), END])
    # No checkpointer: the case row is the only record of the round (D1)
    return graph.compile()


# Built once from the statuses that have a handler. A node looks the handler up
# in HANDLERS when it runs, so a test that swaps or removes one still works
_GRAPH_NODES: frozenset[CaseStatus] = frozenset(HANDLERS)
_GRAPH = _build_graph()


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


def recompute(
    db: Session,
    case_id: int,
    *,
    prepare: Callable[[Session, StaffingCase], None] | None = None,
) -> CaseStatus:
    """Move a waiting case to the status its gap and offers call for, then commit.

    Called after anything that can change the answer: a candidate accepted,
    rejected or timed out, an approver decided, or another case took or released
    a shared candidate. Returns the status the case ends the round with.

      * A case where automation stopped (RESOLVED, UNRESOLVED, FAILED,
        MANUAL_HANDOFF) is left alone: it has no way out. The caller's own
        pending work is still committed.
      * The same status as before writes nothing.
      * A different status is checked against ALLOWED_TRANSITIONS, written with
        one CASE_STATUS_CHANGED row, and the round continues like `advance()`
        when it is not a wait point (OUTREACH sends the next wave, EXECUTING
        closes the case).

    Optional prepare runs inside the D11 savepoint before computing the status.
    It is not called for a stopped case. It must not commit or change case.status;
    its workflow writes roll back on failure while the caller's answer is kept.

    Raises InvalidTransitionError, without touching the case, when it is neither
    waiting nor stopped: a round always ends at one of those, so anything else
    is a caller that is not on the workflow. The caller must then not commit.

    Unlike `resume()` there is no requested status that can lose a race: the
    status is computed under the case lock. So a failure while computing it is
    a system fault and fails the case through D11 like a failing handler.

    One computed move has no edge of its own: a case at WAITING_RESPONSE whose
    assigned staff already close the gap. It is staffed, so it must not fail. It
    passes through WAITING_APPROVAL (T2) to EXECUTING, both written as status
    changes. This needs the gap to close without a recompute in between, for
    example an approval decided in the same transaction as the answer.
    """
    case = _load_for_update(db, case_id)
    if case.status in AUTOMATION_STOPPED_STATUSES:
        _run_round(db, case)
        return case.status
    if case.status not in WAITING_CASE_STATUSES:
        raise InvalidTransitionError(
            f"Case {case.id} is {case.status.value}, not at a wait point: cannot recompute"
        )

    def before(db: Session, case: StaffingCase) -> None:
        if prepare is not None:
            previous = case.status
            prepare(db, case)
            if case.status != previous:
                raise WorkflowError("Preparation callback changed case.status itself")
        db.flush()
        _apply_computed_status(db, case)

    _run_round(db, case, before=before)
    return case.status


def leave_handoff(db: Session, case_id: int, next_status: CaseStatus) -> StaffingCase:
    """Take a MANUAL_HANDOFF case to RESOLVED (T8) or UNRESOLVED (T9); no commit.

    Callers: the manual assignment route once the gap is closed (T8), the route
    that closes a case without a replacement (T9), and the window-close step
    when a successor case opens for the shift (T9). Handlers and `recompute()`
    never take these edges.

    Unlike the other entry points this neither runs a round nor commits: both
    targets are terminal, so nothing follows, and the caller writes its own rows
    in the same transaction. A failure propagates to the caller, which rolls
    back; the case does not become FAILED (D11 is for workflow rounds).

    Raises InvalidTransitionError, without touching the case, when it is not at
    MANUAL_HANDOFF or the target is not one of the two exits.
    """
    case = _load_for_update(db, case_id)
    if case.status is not CaseStatus.MANUAL_HANDOFF:
        raise InvalidTransitionError(
            f"Case {case.id} is {case.status.value}, not MANUAL_HANDOFF: cannot leave handoff"
        )
    if next_status not in {CaseStatus.RESOLVED, CaseStatus.UNRESOLVED}:
        raise InvalidTransitionError(
            f"Case {case.id} cannot leave MANUAL_HANDOFF for {next_status.value}"
        )
    assert_transition(case.status, next_status)
    _change_status(db, case, next_status)
    return case


def _apply_computed_status(db: Session, case: StaffingCase) -> None:
    target = decide_status(case_facts_service.load_case_facts(db, case))
    if target is case.status:
        return
    if case.status is CaseStatus.WAITING_RESPONSE and target is CaseStatus.EXECUTING:
        # No WAITING_RESPONSE -> EXECUTING edge: go by way of WAITING_APPROVAL
        assert_transition(case.status, CaseStatus.WAITING_APPROVAL)
        _change_status(db, case, CaseStatus.WAITING_APPROVAL)
    assert_transition(case.status, target)
    _change_status(db, case, target)


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


def _run_round(
    db: Session,
    case: StaffingCase,
    *,
    before: Callable[[Session, StaffingCase], None] | None = None,
) -> None:
    """Run handlers until the case waits or stops, then commit.

    `before` runs first, inside the same savepoint, so a failure there is
    recorded through D11 exactly like a failing handler.
    """
    failed_at = case.status
    try:
        # Savepoint: a failure undoes this round only, not the caller's work
        with db.begin_nested():
            if before is not None:
                before(db, case)
            run = _Round(db=db, case=case, failed_at=case.status)
            try:
                _GRAPH.invoke(
                    {"steps": 0},
                    {"configurable": {"round": run}, "recursion_limit": _MAX_STEPS},
                )
            except GraphRecursionError as error:
                raise WorkflowError(
                    f"Case {case.id} did not stop after {_MAX_STEPS} steps"
                ) from error
            finally:
                failed_at = run.failed_at
    except Exception as error:
        logger.exception("Workflow failed for case %s at %s", case.id, failed_at.value)
        _mark_failed(db, case, failed_at=failed_at, error=error)
    db.commit()
    # Network delivery is strictly post-commit and best effort. The offer row
    # retains its intent when dispatch fails; the job recovers it next tick.
    from app.services import line_delivery_service

    line_delivery_service.dispatch_pending(db, case_id=case.id)


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
