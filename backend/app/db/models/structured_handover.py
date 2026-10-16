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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StructuredHandover(Base):
    __tablename__ = "structured_handover"
    __table_args__ = (
        UniqueConstraint("roster_assignment_id"),
        CheckConstraint(
            "delivery_attempts >= 0 AND delivery_attempts <= 3", name="delivery_attempts"
        ),
        CheckConstraint(
            "delivery_status IS NULL OR "
            "delivery_status IN ('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
            name="delivery_status",
        ),
        Index(
            "ix_structured_handover_delivery_due",
            "delivery_next_attempt_at",
            postgresql_where=text("delivery_status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    incoming_staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    roster_assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roster_assignment.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # NULL for historical/simulation snapshots; never backfill live messages.
    delivery_status: Mapped[str | None] = mapped_column(Text)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    delivery_retry_key: Mapped[str | None] = mapped_column(Text)
    delivery_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    delivery_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_claim: Mapped[str | None] = mapped_column(Text)
    delivery_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_last_result: Mapped[str | None] = mapped_column(Text)
