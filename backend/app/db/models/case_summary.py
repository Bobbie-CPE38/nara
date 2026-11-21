"""An immutable, anonymous case snapshot and its requested LLM summary (round 6 S)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import ExplanationStatus


class CaseSummary(Base):
    __tablename__ = "case_summary"
    __table_args__ = (
        UniqueConstraint("case_id", "input_hash", "prompt_version"),
        CheckConstraint("attempts >= 0 AND attempt_limit >= attempts", name="attempt_bounds"),
        Index("ix_case_summary_pending", "id", postgresql_where=sql_text("status = 'PENDING'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"), index=True)
    input_hash: Mapped[str] = mapped_column(Text)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prompt_version: Mapped[str] = mapped_column(Text)
    status: Mapped[ExplanationStatus] = mapped_column(StrEnumText(ExplanationStatus))
    text: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))
    attempt_limit: Mapped[int] = mapped_column(Integer)
    claim: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
