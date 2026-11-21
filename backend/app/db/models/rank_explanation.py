import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import ExplanationStatus


class RankExplanation(Base):
    """One LLM sentence per plan and prompt version (round 3 PR X)."""

    __tablename__ = "rank_explanation"
    __table_args__ = (
        UniqueConstraint("plan_id", "prompt_version"),
        Index(
            "ix_rank_explanation_pending",
            "id",
            postgresql_where=sql_text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_plans.id"))
    prompt_version: Mapped[str] = mapped_column(Text)
    status: Mapped[ExplanationStatus] = mapped_column(StrEnumText(ExplanationStatus))
    input_hash: Mapped[str | None] = mapped_column(Text)
    # Exactly what was sent to the LLM; numbers and ranks only, no personal data.
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    text: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    # Durable attempt counter; bounds LLM calls across crashes.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))
    # Round 6 PR E1: the attempts the row may reach in the current user request. NULL = no
    # user asked (queued by the workflow before E1); the sweep never takes such a row
    attempt_limit: Mapped[int | None] = mapped_column(Integer)
    claim: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # An LlmCallStatus value or INVALID_INPUT, NO_CANDIDATES, ATTEMPTS_EXHAUSTED; no SDK text.
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
