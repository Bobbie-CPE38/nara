"""User-requested case summaries; stored facts only, no workflow mutation or LINE.

The input is built from persisted, anonymous facts, never the current clock, API
projections that depend on expiry, audit prose, staff identity or LINE messages.
A request freezes it; the worker always uses that exact snapshot even if the case
changes while the model runs. E1 owns the shared request error codes and lease policy.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import (
    ApprovalRequest,
    ApprovalWardDecision,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    CaseSummary,
    Role,
    RosterAssignment,
    Shift,
    Skill,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapInterval,
    StaffingGapRole,
    StaffingGapSkill,
)
from app.db.session import SessionLocal
from app.domain.enums import (
    ExplanationBlock,
    ExplanationStatus,
    ExplanationViewStatus,
    LlmCallStatus,
    LlmRefusal,
)
from app.domain.errors import CaseNotFoundError
from app.integrations.llm import LlmAttempt, LlmRequest
from app.schemas.case_summary import CaseSummaryView, SummaryCurrent, SummaryHistory
from app.services import explanation_service, llm_gateway, llm_service

logger = logging.getLogger(__name__)
PROMPT_VERSION = "case-summary-v1"
MAX_PER_SWEEP = 3
SYSTEM_PROMPT = (
    "Summarize the recorded staffing case in concise Thai for the head nurse. "
    "Use only facts and numbers in the JSON. Never invent identities, clinical facts or "
    "recommendations, and never claim staffing has succeeded unless case_status is RESOLVED. "
    "assessed_gap is the saved assessment, not the remaining shortage: do not subtract "
    "assigned people from it or infer coverage. Counts of stored offers include history. "
    "Describe the current workflow status, saved shortage and recorded response/approval progress. "
    "Return plain text only, no more than 2000 characters."
)
_RETRY_REASONS = frozenset(
    {
        "TIMEOUT",
        "THROTTLED",
        "SERVICE_ERROR",
        "CONFIG_ERROR",
        "ATTEMPTS_EXHAUSTED",
        "QUOTA_EXHAUSTED",
    }
)


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).isoformat()


def build_payload(db: Session, case: StaffingCase) -> dict[str, Any]:
    """Canonical DB-only facts. Same persisted facts yield the same hash as time passes."""

    def counts(statement: Any) -> dict[str, int]:
        return {str(key): count for key, count in db.execute(statement)}

    with db.no_autoflush:
        shift = db.get(Shift, case.shift_id)
        assert shift is not None
        gap = db.scalar(
            select(StaffingGap)
            .where(StaffingGap.case_id == case.id)
            .order_by(StaffingGap.id.desc())
            .limit(1)
        )
        intervals = (
            []
            if gap is None
            else [
                {
                    "start_at": _stamp(row.start_at),
                    "end_at": _stamp(row.end_at),
                    "required": row.required_count,
                    "present": row.current_count,
                    "gap": row.gap_count,
                }
                for row in db.scalars(
                    select(StaffingGapInterval)
                    .where(StaffingGapInterval.gap_id == gap.id)
                    .order_by(StaffingGapInterval.start_at)
                )
            ]
        )
        plan = db.scalar(
            select(CandidatePlan)
            .where(CandidatePlan.case_id == case.id)
            .order_by(CandidatePlan.id.desc())
            .limit(1)
        )
        candidates = (
            0
            if plan is None
            else db.scalar(
                select(func.count())
                .select_from(CandidateItem)
                .where(CandidateItem.plan_id == plan.id)
            )
        )
        offers = counts(
            select(CandidateOutreach.status, func.count())
            .where(CandidateOutreach.case_id == case.id)
            .group_by(CandidateOutreach.status)
        )
        requests = list(
            db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == case.id))
        )
        approvals = {"pending": 0, "approved": 0, "rejected": 0, "timed_out": 0}
        for request in requests:
            key = (
                "pending"
                if request.is_pending
                else "timed_out"
                if request.is_timed_out
                else "approved"
                if request.is_approved
                else "rejected"
            )
            approvals[key] += 1
        wards = counts(
            select(ApprovalWardDecision.side, func.count())
            .join(ApprovalRequest, ApprovalRequest.id == ApprovalWardDecision.approval_request_id)
            .where(ApprovalRequest.case_id == case.id, ApprovalWardDecision.is_approved.is_(True))
            .group_by(ApprovalWardDecision.side)
        )
        events = counts(
            select(StaffingEvent.event_type, func.count())
            .where(StaffingEvent.case_id == case.id)
            .group_by(StaffingEvent.event_type)
        )
        roster = [
            {
                "status": str(row.status),
                "assignment_type": str(row.assignment_type),
                "start_at": _stamp(row.actual_start_at or shift.start_at),
                "end_at": _stamp(row.actual_end_at or shift.end_at),
            }
            for row in db.scalars(
                select(RosterAssignment).where(RosterAssignment.shift_id == shift.id)
            )
        ]

    def named_gaps(model: Any, catalog: Any, key: Any) -> list[dict[str, Any]]:
        if gap is None:
            return []
        return [
            {"kind": name, "required": required, "present": present, "gap": missing}
            for name, required, present, missing in db.execute(
                select(catalog.name, model.required_count, model.current_count, model.gap_count)
                .join(catalog, catalog.id == key)
                .where(model.gap_id == gap.id)
                .order_by(key)
            )
        ]

    role_gaps = named_gaps(StaffingGapRole, Role, StaffingGapRole.role_id)
    skill_gaps = named_gaps(StaffingGapSkill, Skill, StaffingGapSkill.skill_id)
    return {
        "work_type": "CASE_SUMMARY",
        "case_status": str(case.status),
        "shift": {
            "start_at": _stamp(shift.start_at),
            "end_at": _stamp(shift.end_at),
            "patient_count": shift.patient_count,
        },
        "assessed_gap": None
        if gap is None
        else {
            "headcount_gap": gap.headcount_gap,
            "effective_minimum": gap.effective_minimum,
            "intervals": intervals,
            "roles": role_gaps,
            "skills": skill_gaps,
        },
        "latest_plan": None
        if plan is None
        else {"solver_status": str(plan.solver_status), "candidate_count": candidates},
        "offers": offers,
        "offer_count": sum(offers.values()),
        "approvals": approvals,
        "approved_ward_sides": wards,
        "events": events,
        "roster": sorted(roster, key=explanation_service.canonical_json),
    }


def llm_request(payload: dict[str, Any]) -> LlmRequest:
    return LlmRequest(
        system=SYSTEM_PROMPT,
        prompt="Summarize this staffing case.\nData (JSON):\n"
        + explanation_service.canonical_json(payload),
        payload=payload,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )


def _blocked(
    db: Session, payload: dict[str, Any], row: CaseSummary | None
) -> ExplanationBlock | None:
    if row is not None:
        if row.status == ExplanationStatus.READY:
            return ExplanationBlock.ALREADY_READY
        if row.status == ExplanationStatus.PENDING:
            return ExplanationBlock.PENDING
    if not settings.llm_ready:
        return ExplanationBlock.NOT_CONFIGURED
    if row is not None and row.failure_reason not in _RETRY_REASONS:
        return ExplanationBlock.INVALID_INPUT
    if llm_gateway.estimate_input_tokens(llm_request(payload)) > settings.llm_max_input_tokens:
        return ExplanationBlock.INVALID_INPUT
    if row is not None and row.attempts >= settings.llm_max_attempts_per_row:
        return ExplanationBlock.ATTEMPTS_EXHAUSTED
    if llm_gateway.demo_quota_left(db) <= 0:
        return ExplanationBlock.QUOTA_EXHAUSTED
    return None


def _row(db: Session, case_id: int, digest: str, *, lock: bool = False) -> CaseSummary | None:
    query = select(CaseSummary).where(
        CaseSummary.case_id == case_id, CaseSummary.input_hash == digest
    )
    # Keep a successfully cached answer across future prompt upgrades.
    query = query.order_by(
        (CaseSummary.status == ExplanationStatus.READY).desc(), CaseSummary.id.desc()
    ).limit(1)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def _view(db: Session, case: StaffingCase, payload: dict[str, Any]) -> CaseSummaryView:
    digest = explanation_service.input_hash(payload)
    exact = _row(db, case.id, digest)
    ready = list(
        db.scalars(
            select(CaseSummary)
            .where(CaseSummary.case_id == case.id, CaseSummary.status == ExplanationStatus.READY)
            .order_by(CaseSummary.id.desc())
        )
    )
    displayed = exact or (ready[0] if ready else None)
    blocked = _blocked(db, payload, exact)
    status = ExplanationViewStatus.NOT_REQUESTED
    if displayed is not None:
        status = (
            ExplanationViewStatus.READY
            if displayed.status == ExplanationStatus.READY
            else ExplanationViewStatus.PENDING
            if displayed.status == ExplanationStatus.PENDING
            else ExplanationViewStatus.QUOTA_EXHAUSTED
            if displayed.failure_reason == "QUOTA_EXHAUSTED"
            else ExplanationViewStatus.UNAVAILABLE
        )
    return CaseSummaryView(
        current=SummaryCurrent(
            summary_id=displayed.id if displayed else None,
            status=status,
            text=displayed.text
            if displayed and displayed.status == ExplanationStatus.READY
            else None,
            generated_at=displayed.ready_at if displayed else None,
            stale=displayed is not None and displayed.input_hash != digest,
            can_request=blocked is None,
            request_blocked_reason=blocked,
        ),
        history=[
            SummaryHistory(summary_id=row.id, text=row.text, generated_at=row.ready_at)
            for row in ready
            if row is not displayed and row.text is not None and row.ready_at is not None
        ],
    )


def view(db: Session, case: StaffingCase) -> CaseSummaryView:
    return _view(db, case, build_payload(db, case))


def request(db: Session, case_id: int) -> CaseSummaryView:
    # Serialize same-case requests; the worker never locks a case or workflow row.
    case = db.scalar(
        select(StaffingCase)
        .where(StaffingCase.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if case is None:
        raise CaseNotFoundError(f"Case {case_id} not found")
    payload = build_payload(db, case)
    digest = explanation_service.input_hash(payload)
    row = _row(db, case.id, digest, lock=True)
    blocked = _blocked(db, payload, row)
    if blocked in (ExplanationBlock.PENDING, ExplanationBlock.ALREADY_READY):
        result = _view(db, case, payload)
        db.rollback()
        return result
    if blocked is not None:
        db.rollback()
        raise explanation_service.ExplanationRequestError(blocked)
    if row is None:
        db.execute(
            insert(CaseSummary)
            .values(
                case_id=case.id,
                input_hash=digest,
                input_payload=payload,
                prompt_version=PROMPT_VERSION,
                status=ExplanationStatus.PENDING,
                attempt_limit=explanation_service.max_attempts(),
                created_at=clock.now(),
            )
            .on_conflict_do_nothing(index_elements=["case_id", "input_hash", "prompt_version"])
        )
    else:
        row.status = ExplanationStatus.PENDING
        row.failure_reason = None
        row.claim = row.lease_until = None
        row.attempt_limit = min(
            row.attempts + explanation_service.max_attempts(), settings.llm_max_attempts_per_row
        )
    db.flush()
    result = _view(db, case, payload)
    db.commit()
    return result


@dataclass(frozen=True)
class Claim:
    summary_id: int
    case_id: int
    token: uuid.UUID


def _limit(row: CaseSummary) -> int:
    return min(row.attempt_limit, settings.llm_max_attempts_per_row)


def _db_now() -> Any:
    return func.clock_timestamp()


def _fail(row: CaseSummary, reason: str, status: ExplanationStatus) -> None:
    row.status = status
    row.failure_reason = reason
    row.claim = None
    row.lease_until = None


def _claim(db: Session) -> Claim | None:
    """Claim the oldest due PENDING row, or None. Rows with no attempts left end FAILED here."""
    for _ in range(20):
        row = db.scalar(
            select(CaseSummary)
            .where(
                CaseSummary.status == ExplanationStatus.PENDING,
                # Only rows a user asked for (round 6 PR E1)
                CaseSummary.attempt_limit.is_not(None),
                or_(CaseSummary.lease_until.is_(None), CaseSummary.lease_until <= _db_now()),
            )
            .order_by(CaseSummary.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            db.rollback()
            return None
        if row.attempts >= _limit(row):
            # An earlier lease expired after a crash. Leftover IN_FLIGHT log rows stay as
            # they are: they mean "usage unknown".
            _fail(row, "ATTEMPTS_EXHAUSTED", ExplanationStatus.FAILED)
            db.commit()
            continue
        token = uuid.uuid4()
        row.claim = token
        row.lease_until = _db_now() + explanation_service.lease_duration()
        claim = Claim(row.id, row.case_id, token)
        db.commit()
        return claim
    return None


def _lock(db: Session, claim: Claim) -> CaseSummary | None:
    row = db.scalar(
        select(CaseSummary)
        .where(CaseSummary.id == claim.summary_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.claim != claim.token or row.status != ExplanationStatus.PENDING:
        db.rollback()
        return None
    return row


def _start_attempt(
    db: Session, claim: Claim, payload: dict[str, Any], digest: str, request: LlmRequest
) -> llm_gateway.Ticket | None:
    """Count the attempt durably, reserve quota and log it IN_FLIGHT, then commit."""
    row = _lock(db, claim)
    if row is None:
        return None
    if row.attempts >= _limit(row):
        _fail(row, "ATTEMPTS_EXHAUSTED", ExplanationStatus.FAILED)
        db.commit()
        return None
    subject = llm_gateway.case_summary(
        summary_id=row.id,
        case_id=row.case_id,
        prompt_version=row.prompt_version,
        attempt=row.attempts + 1,
        input_hash=digest,
    )
    ticket = llm_gateway.start(db, request, subject)
    if isinstance(ticket, LlmRefusal):
        if ticket in (LlmRefusal.QUOTA_EXHAUSTED, LlmRefusal.INPUT_TOO_LARGE):
            _fail(row, ticket.value, ExplanationStatus.SKIPPED)
            db.commit()
        else:
            # Switched off or misconfigured mid-sweep: the lease runs out, a later sweep
            # takes the row again
            db.rollback()
        return None
    row.attempts += 1
    db.commit()
    return ticket


def _record(db: Session, claim: Claim, result: LlmAttempt) -> bool:
    """Apply one attempt to the row. llm_gateway.send() already logged it. True asks the
    caller to try again."""
    row = _lock(db, claim)
    if row is None:
        return False
    retry = False
    if result.status == LlmCallStatus.SUCCEEDED and result.text:
        row.status = ExplanationStatus.READY
        row.text = result.text
        row.ready_at = clock.now()
        row.failure_reason = None
        row.claim = None
        row.lease_until = None
    elif llm_service.is_retryable(result.status) and row.attempts < _limit(row):
        retry = True
    else:
        _fail(row, result.status.value, ExplanationStatus.FAILED)
    db.commit()
    return retry


def _process_one(db: Session) -> bool:
    """Handle one due row end to end. False when no row is due."""
    claim = _claim(db)
    if claim is None:
        return False
    row = _lock(db, claim)
    if row is None:
        return True
    # The worker never rebuilds a live snapshot or locks a workflow row.
    payload, digest = row.input_payload, row.input_hash
    prepared = llm_request(payload)
    db.rollback()
    while True:
        ticket = _start_attempt(db, claim, payload, digest, prepared)
        if ticket is None:
            return True
        # _start_attempt committed: no transaction or lock is open during the call
        result = llm_gateway.send(db, ticket)
        if not _record(db, claim, result):
            return True


def run_pending(db: Session) -> int:
    """Generate up to MAX_PER_SWEEP due explanations. Returns how many rows were handled."""
    if not settings.llm_enabled:
        return 0
    if not settings.llm_ready:
        logger.error("LLM is enabled but misconfigured; case summary sweep skipped")
        return 0
    handled = 0
    for _ in range(MAX_PER_SWEEP):
        try:
            if not _process_one(db):
                break
            handled += 1
        except Exception as error:
            db.rollback()
            # The row stays PENDING with its lease; attempts bound the retries.
            logger.error("Case summary sweep deferred (%s)", type(error).__name__)
            break
    return handled


def run_pending_in_new_session() -> None:
    """Background task of the Job route: a fresh Session, never the request's."""
    try:
        with SessionLocal() as db:
            run_pending(db)
    except Exception as error:
        logger.error("Case summary background task failed (%s)", type(error).__name__)
