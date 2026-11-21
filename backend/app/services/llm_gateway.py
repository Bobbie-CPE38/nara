"""The only way to reach an LLM (round 6 PR B1, docs/workflow.md 6.27).

Every attempt of every work type, retries included, takes two steps:

  start()  inside the caller's transaction: refuse what must not be sent, reserve one
           unit of quota with one conditional statement, and add the IN_FLIGHT log row.
           The caller commits, so both are durable before the network is reached.
  send()   with no transaction open: call the provider, then record the result in a new
           transaction and commit it.

call() does both for a caller with no row of its own, such as the model trial script.
A crash after start() leaves the IN_FLIGHT row and keeps the reserved quota: the usage is
unknown and never refunded. A refusal sends nothing, writes no log row and uses no quota.
Callers own retries; each retry is a new start().

The scope follows the work type: MODEL_TRIAL counts against its run's LLM_TRIAL_USAGE row,
everything else against the DEMO day in LLM_DAILY_USAGE. No caller picks a scope or a cap.
"""

import logging
import math
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core import clock
from app.core.config import settings
from app.db.models import LlmCallLog, LlmDailyUsage, LlmTrialUsage
from app.domain.enums import LlmCallStatus, LlmQuotaScope, LlmRefusal, LlmWorkType
from app.services import llm_service
from app.services.llm_service import LlmAttempt, LlmRequest

logger = logging.getLogger(__name__)

# The prompt is not tokenized before sending. One token per 3 UTF-8 bytes overestimates
# JSON and English and counts a Thai character (3 bytes) as a whole token. The real count
# is logged in input_tokens; PR B2 checks the estimate against it
BYTES_PER_TOKEN_ESTIMATE = 3


@dataclass(frozen=True)
class Subject:
    """What one attempt is for. Build it with rank_explanation(), case_summary() or
    model_trial(); the LLM_CALL_LOG CHECK accepts only those shapes."""

    work_type: LlmWorkType
    prompt_version: str
    attempt: int
    input_hash: str | None = None
    explanation_id: int | None = None
    case_id: int | None = None
    plan_id: int | None = None
    subject_id: int | None = None
    trial_run_id: str | None = None
    trial_case_key: str | None = None


def rank_explanation(
    *,
    explanation_id: int,
    case_id: int,
    plan_id: int,
    prompt_version: str,
    attempt: int,
    input_hash: str | None,
) -> Subject:
    return Subject(
        LlmWorkType.RANK_EXPLANATION,
        prompt_version,
        attempt,
        input_hash,
        explanation_id=explanation_id,
        case_id=case_id,
        plan_id=plan_id,
    )


def case_summary(
    *, summary_id: int, case_id: int, prompt_version: str, attempt: int, input_hash: str | None
) -> Subject:
    return Subject(
        LlmWorkType.CASE_SUMMARY,
        prompt_version,
        attempt,
        input_hash,
        subject_id=summary_id,
        case_id=case_id,
    )


def model_trial(
    *,
    trial_run_id: str,
    trial_case_key: str,
    prompt_version: str,
    attempt: int,
    input_hash: str | None,
) -> Subject:
    """trial_case_key names one case and model pair of the run, e.g. "case-07/nova-lite"."""
    return Subject(
        LlmWorkType.MODEL_TRIAL,
        prompt_version,
        attempt,
        input_hash,
        trial_run_id=trial_run_id,
        trial_case_key=trial_case_key,
    )


@dataclass
class Ticket:
    """An attempt that start() counted and logged. send() accepts each ticket once."""

    log_id: int
    request: LlmRequest
    _sent: bool = field(default=False, repr=False)


@dataclass(frozen=True)
class Spend:
    known_usd: Decimal
    # Attempts whose tokens or price are unknown (a crash, no usage, no configured price)
    unknown_calls: int


def scope_of(work_type: LlmWorkType) -> LlmQuotaScope:
    return LlmQuotaScope.TRIAL if work_type == LlmWorkType.MODEL_TRIAL else LlmQuotaScope.DEMO


def estimate_input_tokens(request: LlmRequest) -> int:
    size = len(request.system.encode()) + len(request.prompt.encode())
    return math.ceil(size / BYTES_PER_TOKEN_ESTIMATE)


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #
def _quota_day(at: datetime | None) -> ColumnElement[date]:
    """The DEMO day, from the database's real time (an exception to D10, like the lease
    in explanation_service): moving the Demo Clock must never renew the allowance."""
    now = func.clock_timestamp() if at is None else literal(at, DateTime(timezone=True))
    return cast(func.timezone(settings.llm_quota_timezone, now), Date)


def _reserve_demo(db: Session, at: datetime | None = None) -> bool:
    cap = settings.llm_daily_call_cap
    if cap <= 0:  # the insert of a new day below would otherwise count 1 past the cap
        return False
    statement = (
        insert(LlmDailyUsage)
        .values(usage_date=_quota_day(at), used=1)
        .on_conflict_do_update(
            index_elements=[LlmDailyUsage.usage_date],
            set_={"used": LlmDailyUsage.used + 1},
            where=LlmDailyUsage.used < cap,
        )
        .returning(LlmDailyUsage.used)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def _reserve_trial(db: Session, trial_run_id: str) -> bool:
    statement = (
        update(LlmTrialUsage)
        .where(LlmTrialUsage.trial_run_id == trial_run_id, LlmTrialUsage.used < LlmTrialUsage.cap)
        .values(used=LlmTrialUsage.used + 1)
        .returning(LlmTrialUsage.used)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def demo_used(db: Session, at: datetime | None = None) -> int:
    """Attempts already counted today (DEMO scope)."""
    used = db.scalar(select(LlmDailyUsage.used).where(LlmDailyUsage.usage_date == _quota_day(at)))
    return used or 0


def quota_day(db: Session) -> date:
    """Today's DEMO quota day, the key demo_used() reads (round 6 PR F1, the dashboard)."""
    return db.execute(select(_quota_day(None))).scalar_one()


def demo_quota_left(db: Session, at: datetime | None = None) -> int:
    """How many more DEMO attempts today allows. A read only: start() reserves."""
    return max(0, settings.llm_daily_call_cap - demo_used(db, at))


def create_trial_run(db: Session, trial_run_id: str, cap: int | None = None) -> LlmTrialUsage:
    """Create the run's counter once, in the caller's transaction, and return it.

    The cap is fixed when the run is created: calling again with any cap returns the
    existing row unchanged. It may not exceed settings.llm_trial_call_cap.
    """
    cap = settings.llm_trial_call_cap if cap is None else cap
    if not 0 <= cap <= settings.llm_trial_call_cap:
        raise ValueError(f"trial cap must be between 0 and {settings.llm_trial_call_cap}")
    db.execute(
        insert(LlmTrialUsage)
        .values(trial_run_id=trial_run_id, cap=cap, used=0, created_at=clock.now())
        .on_conflict_do_nothing(index_elements=[LlmTrialUsage.trial_run_id])
    )
    return db.scalars(
        select(LlmTrialUsage)
        .where(LlmTrialUsage.trial_run_id == trial_run_id)
        .execution_options(populate_existing=True)
    ).one()


# --------------------------------------------------------------------------- #
# Attempts
# --------------------------------------------------------------------------- #
def _refusal(request: LlmRequest, scope: LlmQuotaScope) -> LlmRefusal | None:
    # The trial runs from an internal script and does not need LLM_ENABLED (6.27)
    if scope == LlmQuotaScope.DEMO and not settings.llm_enabled:
        return LlmRefusal.DISABLED
    if not settings.llm_configured:
        return LlmRefusal.NOT_CONFIGURED
    if estimate_input_tokens(request) > settings.llm_max_input_tokens:
        return LlmRefusal.INPUT_TOO_LARGE
    return None


def start(db: Session, request: LlmRequest, subject: Subject) -> Ticket | LlmRefusal:
    """Reserve quota and log the attempt IN_FLIGHT in the caller's transaction.

    The caller must commit before send(). On a refusal nothing was written; the caller may
    record it on its own row. If the caller rolls back instead, the reservation goes too.
    """
    scope = scope_of(subject.work_type)
    refusal = _refusal(request, scope)
    if refusal is not None:
        return refusal
    if scope == LlmQuotaScope.TRIAL:
        if subject.trial_run_id is None or not _reserve_trial(db, subject.trial_run_id):
            return LlmRefusal.QUOTA_EXHAUSTED
    elif not _reserve_demo(db):
        return LlmRefusal.QUOTA_EXHAUSTED
    request = replace(
        request, max_output_tokens=min(request.max_output_tokens, settings.llm_max_output_tokens)
    )
    # Bedrock directly or through the Lambda proxy; send() records what the call reports
    real = settings.llm_provider != "fake"
    log = LlmCallLog(
        work_type=subject.work_type,
        explanation_id=subject.explanation_id,
        case_id=subject.case_id,
        plan_id=subject.plan_id,
        subject_id=subject.subject_id,
        trial_run_id=subject.trial_run_id,
        trial_case_key=subject.trial_case_key,
        provider=settings.llm_provider,
        prompt_version=subject.prompt_version,
        model_id=settings.llm_model_id if real else None,
        region=settings.aws_region if real else None,
        input_hash=subject.input_hash,
        attempt=subject.attempt,
        status=LlmCallStatus.IN_FLIGHT,
        started_at=clock.now(),
    )
    db.add(log)
    db.flush()
    return Ticket(log.id, request)


def _failure(error: Exception) -> LlmAttempt:
    return LlmAttempt(
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


def send(db: Session, ticket: Ticket) -> LlmAttempt:
    """Call the provider for a committed ticket, then record the result and commit.

    Never raises for a provider error: it comes back as a status. No prompt, response or
    exception message is logged, only the exception type.
    """
    if ticket._sent:
        raise RuntimeError("this attempt was already sent")
    if db.in_transaction():
        # A transaction here could hold row locks for the whole network call
        raise RuntimeError("commit or roll back before sending an LLM attempt")
    ticket._sent = True
    started = time.monotonic()
    try:
        result = llm_service.generate_explanation(ticket.request)
    except Exception as error:
        logger.error("LLM call failed (%s)", type(error).__name__)
        result = _failure(error)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log = db.get(LlmCallLog, ticket.log_id, with_for_update=True, populate_existing=True)
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
        log.finished_at = clock.now()
    db.commit()
    return result


def call(db: Session, request: LlmRequest, subject: Subject) -> LlmAttempt | LlmRefusal:
    """start() then send() for a caller with no row of its own. Commits; on a refusal it
    rolls back. The session must hold no other unsaved work."""
    started = start(db, request, subject)
    if isinstance(started, LlmRefusal):
        db.rollback()
        return started
    db.commit()
    return send(db, started)


def spend(db: Session, *, start_at: datetime, end_at: datetime) -> Spend:
    """Cost of every work type together for attempts started in [start_at, end_at)."""
    known, unknown = db.execute(
        select(
            func.coalesce(func.sum(LlmCallLog.estimated_cost_usd), 0),
            func.count().filter(LlmCallLog.estimated_cost_usd.is_(None)),
        ).where(LlmCallLog.started_at >= start_at, LlmCallLog.started_at < end_at)
    ).one()
    return Spend(known_usd=Decimal(known or 0), unknown_calls=unknown)
