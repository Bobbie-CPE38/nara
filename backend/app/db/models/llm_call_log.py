from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import LlmCallStatus


class LlmCallLog(Base):
    """One row per LLM attempt (round 3 PR X). NULL tokens or cost mean unknown, never 0."""

    __tablename__ = "llm_call_log"
    __table_args__ = (UniqueConstraint("explanation_id", "attempt"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    explanation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rank_explanation.id"))
    case_id: Mapped[int] = mapped_column(BigInteger)
    plan_id: Mapped[int] = mapped_column(BigInteger, index=True)
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
