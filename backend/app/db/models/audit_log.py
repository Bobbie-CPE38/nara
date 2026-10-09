from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("actors.id"))
    entity_type: Mapped[str] = mapped_column(Text)  # EntityType
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text)  # AuditAction
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
