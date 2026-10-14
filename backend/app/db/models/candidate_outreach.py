from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import Channel, OutreachStatus


class CandidateOutreach(Base):
    __tablename__ = "candidate_outreach"
    __table_args__ = (
        CheckConstraint("status != 'SENT' OR expires_at IS NOT NULL", name="sent_has_expiry"),
        CheckConstraint(
            "delivery_attempts >= 0 AND delivery_attempts <= 3", name="delivery_attempts"
        ),
        CheckConstraint(
            "delivery_status IS NULL OR "
            "delivery_status IN ('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
            name="delivery_status",
        ),
        Index(
            "ix_candidate_outreach_delivery_due",
            "delivery_next_attempt_at",
            postgresql_where=text("delivery_status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    channel: Mapped[Channel] = mapped_column(StrEnumText(Channel))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[OutreachStatus] = mapped_column(StrEnumText(OutreachStatus))
    # NULL for simulation and historical offers; never backfill live delivery.
    delivery_status: Mapped[str | None] = mapped_column(Text)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    delivery_retry_key: Mapped[str | None] = mapped_column(Text)
    delivery_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    delivery_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_claim: Mapped[str | None] = mapped_column(Text)
    delivery_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_last_result: Mapped[str | None] = mapped_column(Text)
