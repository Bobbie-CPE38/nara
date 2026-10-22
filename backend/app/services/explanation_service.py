"""One LLM sentence per plan (round 3 PR X), made only when a user asks (round 6 PR E1).

POST /cases/{id}/explanation runs request(): it checks why the plan cannot be explained
now, permanent reasons before the daily quota, and only then sets a PENDING row with the
attempts this request may use. It never calls the LLM. A background sweep of the Job tick
claims requested rows with a lease, builds a numbers-only payload, and sends every attempt
through llm_gateway (round 6 PR B1), which reserves the daily quota and logs the attempt
before the network and calls with no transaction or lock open. Attempts are counted
durably and never reset, so the row's attempt_limit and LLM_MAX_ATTEMPTS_PER_ROW hold
across crashes and repeated requests. When the daily quota is used up, the due row ends
SKIPPED with QUOTA_EXHAUSTED without a call. An LLM failure never touches a case. No
prompt, response or SDK message is logged; only exception type names.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import CandidateItem, CandidatePlan, RankExplanation, StaffingCase
from app.db.session import SessionLocal
from app.domain.constraints.score_breakdown import (
    ScoreMismatchError,
    display_number,
    parse_fraction,
    score_from_snapshot,
    weights_from_snapshot,
)
from app.domain.constraints.soft_metrics import source_priority
from app.domain.enums import (
    CandidateSource,
    ExplanationBlock,
    ExplanationStatus,
    ExplanationViewStatus,
    LlmCallStatus,
    LlmRefusal,
)
from app.domain.errors import CaseNotFoundError
from app.schemas.case import RankExplanationView
from app.services import llm_gateway, llm_service
from app.services.llm_service import LlmAttempt, LlmRequest

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rank-explanation-v3"
MAX_EXPLAINED_CANDIDATES = 10
MAX_PER_SWEEP = 3
_MIN_LEASE_SECONDS = 60
_MAX_EXHAUSTED_PER_SWEEP = 50

RANKING_KEY_ORDER = [
    "candidate_source",
    "hours_this_week",
    "projected_consecutive_shifts",
    "overtime_hours",
    "staff_id",
]

SYSTEM_PROMPT = (
    "You explain, for a hospital shift manager, how a ranked list of replacement candidates "
    "was produced by a scheduling program. Answer in 2 to 4 short sentences of natural Thai "
    "only: no English, Chinese or other scripts, no markdown, no bullets, no recommendations. "
    "Use only numbers that appear in the data. "
    'Refer to people only as "อันดับ N" using the rank field. '
    "Never write a field name or an id (ranking_key, plan_penalty, first_wave, "
    "hours_this_week, plan or staff ids): say what it means in plain Thai instead. "
    "plan_penalty.meaning says what chose the first wave. "
    "The first wave is the first group asked (กลุ่มแรกที่ถูกติดต่อ); the other candidates are "
    "reserves (ตัวสำรอง). "
    "ranking_key orders the candidates inside the plan (first wave first, then reserves): "
    "compare two candidates by its items in the order listed, and the first item on which they "
    "differ decides. Items: candidate_source is where the person comes from "
    "(SAME_WARD = ward เดียวกัน, FLOAT_POOL = กลุ่มสำรองกลาง, CROSS_WARD = ต่าง ward), "
    "hours_this_week = ชั่วโมงที่ทำงานในสัปดาห์นี้, "
    "projected_consecutive_shifts = จำนวนเวรติดกันที่จะเกิดขึ้น, "
    "overtime_hours = ชั่วโมงล่วงเวลา. "
    "Never claim that a rank comes from the total points."
)


_PLAN_PENALTY_MEANING = "selects which group becomes the first wave"
# Round 4 PR T4: no group could cover every target (workflow.md 6.15, 6.20)
_PLAN_PENALTY_MEANING_PARTIAL = (
    "breaks ties only: no group could cover every target, so the first wave is the group "
    "that leaves the fewest uncovered person-minutes (headcount first, then role, then "
    "skill); points choose only among groups that cover the same"
)


class InvalidExplanationInput(Exception):
    """The plan cannot be explained: no stored weights, a score mismatch or no candidates."""

    def __init__(self, reason: str = "INVALID_INPUT") -> None:
        super().__init__(reason)
        self.reason = reason


class ExplanationRequestError(Exception):
    """POST /cases/{id}/explanation refused: nothing was changed and no quota was used."""

    def __init__(self, block: ExplanationBlock) -> None:
        super().__init__(block.value)
        self.block = block


@dataclass(frozen=True)
class Claim:
    explanation_id: int
    case_id: int
    plan_id: int
    token: uuid.UUID


def max_attempts() -> int:
    """Attempts one request may use: the first call and its retries."""
    return min(1 + settings.llm_max_retries, settings.llm_max_attempts_per_row)


def _limit(row: RankExplanation) -> int:
    """Attempts the row may reach in its current request. row.attempts is never reset, so
    LLM_MAX_ATTEMPTS_PER_ROW also bounds the row's lifetime across every request."""
    if row.attempt_limit is None:
        return 0
    return min(row.attempt_limit, settings.llm_max_attempts_per_row)


def _db_now() -> Any:
    """Database wall clock for leases (an exception to D10, see workflow.md 6.15).

    A lease times a real network call, so it must not follow the Demo Clock: advancing or
    freezing that clock would let a second sweep claim a row whose call is still running,
    or keep a crashed row leased for hours. clock_timestamp() is real time even inside a
    long transaction.
    """
    return func.clock_timestamp()


def lease_duration() -> timedelta:
    seconds = settings.llm_request_timeout_seconds * max_attempts() + 30
    return timedelta(seconds=max(_MIN_LEASE_SECONDS, seconds))


# --------------------------------------------------------------------------- #
# Payload and prompt
# --------------------------------------------------------------------------- #
def build_payload(plan: CandidatePlan) -> dict[str, Any]:
    """Numbers, ranks and term names only. Reads plan.input_snapshot and objective_score.

    The snapshot lists candidates in CandidateItem.rank order (optimization_service builds
    both from the same ranked list), so position i is rank i + 1. staff_id is never emitted.
    """
    snapshot = plan.input_snapshot
    raw_weights = snapshot.get("weights") if isinstance(snapshot, dict) else None
    entries = snapshot.get("candidates") if isinstance(snapshot, dict) else None
    if not isinstance(raw_weights, dict) or plan.objective_score is None:
        raise InvalidExplanationInput
    if not isinstance(entries, list) or not entries:
        raise InvalidExplanationInput("NO_CANDIDATES")
    try:
        weights = weights_from_snapshot(raw_weights)
        candidates: list[dict[str, Any]] = []
        for rank, entry in enumerate(entries[:MAX_EXPLAINED_CANDIDATES], start=1):
            score = score_from_snapshot(weights, entry)
            candidates.append(
                {
                    "rank": rank,
                    "first_wave": score.first_wave,
                    "total": display_number(score.total),
                    "terms": [
                        {
                            "name": term.name,
                            "value": display_number(term.value),
                            "weight": display_number(term.weight),
                            "points": display_number(term.points),
                        }
                        for term in score.terms
                    ],
                    "ranking_key": {
                        "candidate_source": source_priority(
                            CandidateSource(entry["source"]), weights.source_order
                        ),
                        "hours_this_week": display_number(
                            parse_fraction(entry["hours_this_week_exact"])
                        ),
                        "projected_consecutive_shifts": entry["projected_consecutive_shifts"],
                        "overtime_hours": display_number(
                            parse_fraction(entry["overtime_hours_exact"])
                        ),
                    },
                }
            )
        penalty = display_number(Fraction(plan.objective_score))
    except (ScoreMismatchError, KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise InvalidExplanationInput from error
    return {
        "targets": snapshot.get("targets"),
        "plan_penalty": {
            "value": penalty,
            "meaning": _PLAN_PENALTY_MEANING_PARTIAL
            if snapshot.get("partial_plan")
            else _PLAN_PENALTY_MEANING,
        },
        "ranking_key": {
            "order": RANKING_KEY_ORDER,
            "meaning": "orders candidates inside the plan; first wave first, then reserves",
        },
        "candidate_count": len(entries),
        "candidates": candidates,
    }


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def render_prompt(payload: dict[str, Any]) -> str:
    return f"Explain this ranking.\nData (JSON):\n{canonical_json(payload)}"


def llm_request(payload: dict[str, Any]) -> LlmRequest:
    return LlmRequest(
        system=SYSTEM_PROMPT,
        prompt=render_prompt(payload),
        payload=payload,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )


# --------------------------------------------------------------------------- #
# User side (round 6 PR E1, docs/workflow.md 6.27 and 9.8)
# --------------------------------------------------------------------------- #
# A failed or skipped row may be asked for again only after these: a passing fault, a
# request cut short by a crash, the day's quota, or a provider configuration error
# (credentials or Bedrock access can be repaired without the row knowing; a user has to
# ask, the sweep never retries it). Every other reason (TRUNCATED, INVALID_OUTPUT, the
# invalid inputs) would fail the same way again
_ASK_AGAIN_REASONS = frozenset(
    {
        LlmCallStatus.TIMEOUT.value,
        LlmCallStatus.THROTTLED.value,
        LlmCallStatus.SERVICE_ERROR.value,
        LlmCallStatus.CONFIG_ERROR.value,
        "ATTEMPTS_EXHAUSTED",
        LlmRefusal.QUOTA_EXHAUSTED.value,
    }
)
_ANSWERED = (ExplanationBlock.ALREADY_READY, ExplanationBlock.PENDING)


def _requested(row: RankExplanation) -> bool:
    return row.status == ExplanationStatus.PENDING and row.attempt_limit is not None


def _view_status(row: RankExplanation | None) -> ExplanationViewStatus:
    if row is None:
        return ExplanationViewStatus.NOT_REQUESTED
    if row.status == ExplanationStatus.READY:
        return ExplanationViewStatus.READY
    if row.status == ExplanationStatus.PENDING:
        # A row queued by the workflow before E1 waits for a user like no row at all
        if _requested(row):
            return ExplanationViewStatus.PENDING
        return ExplanationViewStatus.NOT_REQUESTED
    if (
        row.status == ExplanationStatus.SKIPPED
        and row.failure_reason == LlmRefusal.QUOTA_EXHAUSTED.value
    ):
        return ExplanationViewStatus.QUOTA_EXHAUSTED
    return ExplanationViewStatus.UNAVAILABLE


def _cannot_explain(plan: CandidatePlan) -> bool:
    """The plan's payload cannot be built, or is too large to be sent."""
    try:
        payload = build_payload(plan)
    except InvalidExplanationInput:
        return True
    return llm_gateway.estimate_input_tokens(llm_request(payload)) > settings.llm_max_input_tokens


def _blocked(
    db: Session, plan: CandidatePlan, row: RankExplanation | None
) -> ExplanationBlock | None:
    """Why the plan's explanation cannot be asked for now, or None. Order matters (9.8):
    an answered row first, then permanent reasons, then the daily quota."""
    if row is not None:
        if row.status == ExplanationStatus.READY:
            return ExplanationBlock.ALREADY_READY
        if _requested(row):
            return ExplanationBlock.PENDING
    if not settings.llm_ready:
        return ExplanationBlock.NOT_CONFIGURED
    if (
        row is not None
        and row.status in (ExplanationStatus.FAILED, ExplanationStatus.SKIPPED)
        and row.failure_reason not in _ASK_AGAIN_REASONS
    ):
        return ExplanationBlock.INVALID_INPUT
    if _cannot_explain(plan):
        return ExplanationBlock.INVALID_INPUT
    if row is not None and row.attempts >= settings.llm_max_attempts_per_row:
        return ExplanationBlock.ATTEMPTS_EXHAUSTED
    if llm_gateway.demo_quota_left(db) <= 0:
        return ExplanationBlock.QUOTA_EXHAUSTED
    return None


def _view(db: Session, plan: CandidatePlan, row: RankExplanation | None) -> RankExplanationView:
    blocked = _blocked(db, plan, row)
    if row is not None and row.status == ExplanationStatus.READY:
        text, provider, model_id = row.text, row.provider, row.model_id
    else:
        text = provider = model_id = None
    return RankExplanationView(
        status=_view_status(row),
        text=text,
        provider=provider,
        model_id=model_id,
        can_request=blocked is None,
        request_blocked_reason=blocked,
    )


def _latest_plan(db: Session, case_id: int) -> CandidatePlan | None:
    return db.scalar(
        select(CandidatePlan)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )


def _has_candidates(db: Session, plan: CandidatePlan) -> bool:
    return bool(db.scalar(select(exists().where(CandidateItem.plan_id == plan.id))))


def _latest_row(db: Session, plan: CandidatePlan, *, lock: bool = False) -> RankExplanation | None:
    """The plan's newest row, whatever its prompt version: a plan explained under an older
    prompt keeps its sentence (6.27)."""
    statement = (
        select(RankExplanation)
        .where(RankExplanation.plan_id == plan.id)
        .order_by(RankExplanation.id.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def view(db: Session, plan: CandidatePlan | None) -> RankExplanationView | None:
    """`explanation` of GET /cases/{id} for the latest plan. Reads only and never calls the
    LLM. null without a plan or without candidates."""
    if plan is None or not _has_candidates(db, plan):
        return None
    return _view(db, plan, _latest_row(db, plan))


def request(db: Session, case_id: int) -> RankExplanationView:
    """Ask for the explanation of the case's latest plan (POST /cases/{id}/explanation).

    An answered row (PENDING or READY) comes back unchanged. Otherwise the row is created,
    or set PENDING again with room for one more request's attempts, and committed; the
    sweep calls the LLM later. A refusal rolls back and raises ExplanationRequestError: no
    row, attempt or quota changes. The plan's row is locked first, and two first requests
    at once meet the UNIQUE (plan_id, prompt_version), so pressing twice makes one row.
    """
    if db.get(StaffingCase, case_id) is None:
        raise CaseNotFoundError(f"Case {case_id} not found")
    plan = _latest_plan(db, case_id)
    if plan is None:
        raise CaseNotFoundError(f"Case {case_id} has no plan")
    if not _has_candidates(db, plan):
        db.rollback()
        raise ExplanationRequestError(ExplanationBlock.INVALID_INPUT)
    row = _latest_row(db, plan, lock=True)
    if row is None:
        blocked = _blocked(db, plan, None)
        if blocked is not None:
            db.rollback()
            raise ExplanationRequestError(blocked)
        created = db.execute(
            insert(RankExplanation)
            .values(
                case_id=plan.case_id,
                plan_id=plan.id,
                prompt_version=PROMPT_VERSION,
                status=ExplanationStatus.PENDING,
                attempt_limit=max_attempts(),
            )
            .on_conflict_do_nothing(index_elements=["plan_id", "prompt_version"])
            .returning(RankExplanation.id)
        ).scalar_one_or_none()
        if created is not None:
            db.commit()
            return _view(db, plan, _latest_row(db, plan))
        # A concurrent request made the row first and has committed it: decide on that row
        row = _latest_row(db, plan, lock=True)
        if row is None:  # pragma: no cover - the conflicting row cannot vanish
            db.rollback()
            raise ExplanationRequestError(ExplanationBlock.INVALID_INPUT)
    blocked = _blocked(db, plan, row)
    if blocked in _ANSWERED:
        db.rollback()
        return _view(db, plan, row)
    if blocked is not None:
        db.rollback()
        raise ExplanationRequestError(blocked)
    row.status = ExplanationStatus.PENDING
    row.failure_reason = None
    row.claim = None
    row.lease_until = None
    row.attempt_limit = min(row.attempts + max_attempts(), settings.llm_max_attempts_per_row)
    db.commit()
    return _view(db, plan, row)


# --------------------------------------------------------------------------- #
# Job side
# --------------------------------------------------------------------------- #
def _fail(row: RankExplanation, reason: str, status: ExplanationStatus) -> None:
    row.status = status
    row.failure_reason = reason
    row.claim = None
    row.lease_until = None


def _claim(db: Session) -> Claim | None:
    """Claim the oldest due PENDING row, or None. Rows with no attempts left end FAILED here."""
    for _ in range(_MAX_EXHAUSTED_PER_SWEEP):
        row = db.scalar(
            select(RankExplanation)
            .where(
                RankExplanation.status == ExplanationStatus.PENDING,
                # Only rows a user asked for (round 6 PR E1)
                RankExplanation.attempt_limit.is_not(None),
                or_(
                    RankExplanation.lease_until.is_(None), RankExplanation.lease_until <= _db_now()
                ),
            )
            .order_by(RankExplanation.id)
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
        row.lease_until = _db_now() + lease_duration()
        claim = Claim(row.id, row.case_id, row.plan_id, token)
        db.commit()
        return claim
    return None


def _lock(db: Session, claim: Claim) -> RankExplanation | None:
    row = db.scalar(
        select(RankExplanation)
        .where(RankExplanation.id == claim.explanation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.claim != claim.token or row.status != ExplanationStatus.PENDING:
        db.rollback()
        return None
    return row


def _skip(db: Session, claim: Claim, reason: str) -> None:
    row = _lock(db, claim)
    if row is not None:
        _fail(row, reason, ExplanationStatus.SKIPPED)
        db.commit()


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
    subject = llm_gateway.rank_explanation(
        explanation_id=row.id,
        case_id=row.case_id,
        plan_id=row.plan_id,
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
    row.input_payload = payload
    row.input_hash = digest
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
        row.provider = result.provider
        row.model_id = result.model_id
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
    plan = db.get(CandidatePlan, claim.plan_id)
    try:
        if plan is None:
            raise InvalidExplanationInput
        payload = build_payload(plan)
    except InvalidExplanationInput as error:
        logger.error("Explanation %s skipped (%s)", claim.explanation_id, error.reason)
        _skip(db, claim, error.reason)
        return True
    db.rollback()  # end the read transaction before anything else
    digest = input_hash(payload)
    prepared = llm_request(payload)
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
        logger.error("LLM is enabled but misconfigured; explanation sweep skipped")
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
            logger.error("Explanation sweep deferred (%s)", type(error).__name__)
            break
    return handled


def run_pending_in_new_session() -> None:
    """Background task of the Job route: a fresh Session, never the request's."""
    try:
        with SessionLocal() as db:
            run_pending(db)
    except Exception as error:
        logger.error("Explanation background task failed (%s)", type(error).__name__)
