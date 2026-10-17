"""Durable promotion and final-outcome notices, separate from the original offer push."""

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

from app.core import clock
from app.db.base import Base


class OfferOutcomeNotification(Base):
    __tablename__ = "offer_outcome_notification"
    __table_args__ = (
        UniqueConstraint("outreach_id", "kind"),
        CheckConstraint("kind IN ('FINAL','RESERVE_PROMOTED')", name="kind"),
        CheckConstraint("delivery_attempts BETWEEN 0 AND 3", name="delivery_attempts"),
        CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN "
            "('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
            name="delivery_status",
        ),
        Index(
            "ix_offer_outcome_notification_delivery_due",
            "delivery_next_attempt_at",
            postgresql_where=text("delivery_status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    outreach_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_outreach.id"))
    kind: Mapped[str] = mapped_column(Text, default="FINAL", server_default=text("'FINAL'"))
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    audit_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("audit_log.id"))
    reason: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    # Simulation keeps the outcome for the UI without backfilling messages later.
    delivery_status: Mapped[str | None] = mapped_column(Text)
    delivery_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    delivery_retry_key: Mapped[str | None] = mapped_column(Text)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    delivery_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_claim: Mapped[str | None] = mapped_column(Text)
    delivery_last_result: Mapped[str | None] = mapped_column(Text)
