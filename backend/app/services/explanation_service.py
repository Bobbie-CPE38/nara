"""One LLM sentence per plan (round 3 PR X): enqueue in the workflow, generate in the Job.

The workflow only inserts a small PENDING row. A background sweep of the Job tick claims
rows with a lease, builds a numbers-only payload, calls the gateway with no transaction
or lock open, and records every attempt in llm_call_log. Attempts are counted durably, so
the bound of 1 + LLM_MAX_RETRIES holds across crashes. An LLM failure never touches a case.
No prompt, response or SDK message is logged; only exception type names.
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import CandidatePlan, LlmCallLog, RankExplanation
from app.db.session import SessionLocal
from app.domain.constraints.score_breakdown import (
    ScoreMismatchError,
    display_number,
    parse_fraction,
    score_from_snapshot,
    weights_from_snapshot,
)
from app.domain.constraints.soft_metrics import source_priority
from app.domain.enums import CandidateSource, ExplanationStatus, LlmCallStatus
from app.services import llm_service
from app.services.llm_service import LlmAttempt, LlmRequest

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rank-explanation-v1"
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
    "was produced by a scheduling program. Answer in Thai, in 2 to 4 sentences, as plain text "
    "with no markdown and no recommendations. Use only numbers that appear in the data. "
    'Refer to people only as "อันดับ N" using the rank field. '
    "plan_penalty selects which group of candidates becomes the first wave. "
    "ranking_key orders the candidates inside the plan (first wave first, then reserves). "
    "Never claim that a rank comes from the total points."
)


class InvalidExplanationInput(Exception):
    """The plan cannot be explained: no stored weights, a score mismatch or no candidates."""

    def __init__(self, reason: str = "INVALID_INPUT") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Claim:
    explanation_id: int
    case_id: int
    plan_id: int
    token: uuid.UUID


def max_attempts() -> int:
    return 1 + settings.llm_max_retries


def lease_duration() -> timedelta:
    seconds = settings.llm_request_timeout_seconds * max_attempts() + 30
    return timedelta(seconds=max(_MIN_LEASE_SECONDS, seconds))


# --------------------------------------------------------------------------- #
# Workflow side
# --------------------------------------------------------------------------- #
def enqueue(db: Session, plan: CandidatePlan, *, candidate_count: int) -> None:
    """Insert a PENDING row inside the plan's transaction. No payload, no network."""
    if candidate_count <= 0:
        return
    db.add(
        RankExplanation(
            case_id=plan.case_id,
            plan_id=plan.id,
            prompt_version=PROMPT_VERSION,
            status=ExplanationStatus.PENDING,
        )
    )
    db.flush()


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
            "meaning": "selects which group becomes the first wave",
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
        now = clock.now()
        row = db.scalar(
            select(RankExplanation)
            .where(
                RankExplanation.status == ExplanationStatus.PENDING,
                or_(RankExplanation.lease_until.is_(None), RankExplanation.lease_until <= now),
            )
            .order_by(RankExplanation.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            db.rollback()
            return None
        if row.attempts >= max_attempts():
            # An earlier lease expired after a crash. Leftover IN_FLIGHT log rows stay as
            # they are: they mean "usage unknown".
            _fail(row, "ATTEMPTS_EXHAUSTED", ExplanationStatus.FAILED)
            db.commit()
            continue
        token = uuid.uuid4()
        row.claim = token
        row.lease_until = now + lease_duration()
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


def _start_attempt(db: Session, claim: Claim, payload: dict[str, Any], digest: str) -> int | None:
    """Count the attempt durably and log it IN_FLIGHT. Returns the attempt number or None."""
    row = _lock(db, claim)
    if row is None:
        return None
    if row.attempts >= max_attempts():
        _fail(row, "ATTEMPTS_EXHAUSTED", ExplanationStatus.FAILED)
        db.commit()
        return None
    row.attempts += 1
    row.input_payload = payload
    row.input_hash = digest
    bedrock = settings.llm_provider == "bedrock"
    db.add(
        LlmCallLog(
            explanation_id=row.id,
            case_id=row.case_id,
            plan_id=row.plan_id,
            provider=settings.llm_provider,
            prompt_version=row.prompt_version,
            model_id=settings.llm_model_id if bedrock else None,
            region=settings.aws_region if bedrock else None,
            input_hash=digest,
            attempt=row.attempts,
            status=LlmCallStatus.IN_FLIGHT,
            started_at=clock.now(),
        )
    )
    attempt = row.attempts
    db.commit()
    return attempt


def _call(request: LlmRequest) -> tuple[LlmAttempt, int]:
    """The only place the network is reached. Never raises; no transaction is open."""
    started = time.monotonic()
    try:
        result = llm_service.generate_explanation(request)
    except Exception as error:
        logger.error("LLM call failed (%s)", type(error).__name__)
        result = LlmAttempt(
            status=LlmCallStatus.SERVICE_ERROR,
            text=None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            duration_ms=None,
            error_type=type(error).__name__,
            provider=settings.llm_provider,
            model_id=None,
            region=None,
            input_rate=None,
            output_rate=None,
        )
    return result, int((time.monotonic() - started) * 1000)


def _record(db: Session, claim: Claim, attempt: int, result: LlmAttempt, elapsed_ms: int) -> bool:
    """Persist one attempt. True asks the caller to try again."""
    row = _lock(db, claim)
    if row is None:
        return False
    log = db.scalar(
        select(LlmCallLog)
        .where(LlmCallLog.explanation_id == row.id, LlmCallLog.attempt == attempt)
        .with_for_update()
    )
    now = clock.now()
    if log is not None:
        log.status = result.status
        log.error_type = result.error_type
        log.input_tokens = result.input_tokens
        log.output_tokens = result.output_tokens
        log.total_tokens = result.total_tokens
        log.duration_ms = result.duration_ms if result.duration_ms is not None else elapsed_ms
        log.provider = result.provider
        log.model_id = result.model_id
        log.region = result.region
        log.input_price_per_mtok_usd = result.input_rate
        log.output_price_per_mtok_usd = result.output_rate
        log.estimated_cost_usd = llm_service.estimate_cost(result)
        log.finished_at = now
    retry = False
    if result.status == LlmCallStatus.SUCCEEDED and result.text:
        row.status = ExplanationStatus.READY
        row.text = result.text
        row.provider = result.provider
        row.model_id = result.model_id
        row.ready_at = now
        row.failure_reason = None
        row.claim = None
        row.lease_until = None
    elif llm_service.is_retryable(result.status) and row.attempts < max_attempts():
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
    request = LlmRequest(
        system=SYSTEM_PROMPT,
        prompt=render_prompt(payload),
        payload=payload,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    while True:
        started = _start_attempt(db, claim, payload, digest)
        if started is None:
            return True
        # _start_attempt committed: no transaction or lock is open during the call
        result, elapsed_ms = _call(request)
        if not _record(db, claim, started, result, elapsed_ms):
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
