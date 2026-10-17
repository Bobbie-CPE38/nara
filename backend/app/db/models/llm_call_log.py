from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import LlmCallStatus, LlmWorkType

_RANK = LlmWorkType.RANK_EXPLANATION.value
_SUMMARY = LlmWorkType.CASE_SUMMARY.value
_TRIAL = LlmWorkType.MODEL_TRIAL.value

# Round 6 PR B1: each work type fills its own reference columns and leaves the others NULL
WORK_TYPE_SUBJECT_CHECK = (
    f"(work_type = '{_RANK}' AND explanation_id IS NOT NULL AND case_id IS NOT NULL"
    " AND plan_id IS NOT NULL AND subject_id IS NULL AND trial_run_id IS NULL"
    " AND trial_case_key IS NULL)"
    f" OR (work_type = '{_SUMMARY}' AND subject_id IS NOT NULL AND case_id IS NOT NULL"
    " AND explanation_id IS NULL AND plan_id IS NULL AND trial_run_id IS NULL"
    " AND trial_case_key IS NULL)"
    f" OR (work_type = '{_TRIAL}' AND trial_run_id IS NOT NULL AND trial_case_key IS NOT NULL"
    " AND explanation_id IS NULL AND case_id IS NULL AND plan_id IS NULL"
    " AND subject_id IS NULL)"
)


class LlmCallLog(Base):
    """One row per LLM attempt (round 3 PR X). NULL tokens or cost mean unknown, never 0.

    Round 6 PR B1: every work type logs here, so the daily cap and the monthly cost add
    up one table. Only app.services.llm_gateway writes it.
    """

    __tablename__ = "llm_call_log"
    __table_args__ = (
        UniqueConstraint("explanation_id", "attempt"),
        CheckConstraint(WORK_TYPE_SUBJECT_CHECK, name="work_type_subject"),
        Index(
            "uq_llm_call_log_case_summary_attempt",
            "subject_id",
            "attempt",
            unique=True,
            postgresql_where=text(f"work_type = '{_SUMMARY}'"),
        ),
        # trial_case_key names one case and model pair of the run
        Index(
            "uq_llm_call_log_model_trial_attempt",
            "trial_run_id",
            "trial_case_key",
            "attempt",
            unique=True,
            postgresql_where=text(f"work_type = '{_TRIAL}'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    work_type: Mapped[LlmWorkType] = mapped_column(StrEnumText(LlmWorkType))
    explanation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rank_explanation.id")
    )
    case_id: Mapped[int | None] = mapped_column(BigInteger)
    plan_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    # The case summary row (PR S). No FK, so this table does not depend on S's migration
    subject_id: Mapped[int | None] = mapped_column(BigInteger)
    trial_run_id: Mapped[str | None] = mapped_column(Text)
    trial_case_key: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[LlmCallStatus] = mapped_column(StrEnumText(LlmCallStatus))
    # Exception class name or error code only; never an SDK message.
    error_type: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_price_per_mtok_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    output_price_per_mtok_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
