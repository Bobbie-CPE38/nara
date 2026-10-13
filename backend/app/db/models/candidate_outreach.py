from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import Channel, OutreachStatus


class CandidateOutreach(Base):
    __tablename__ = "candidate_outreach"
    __table_args__ = (
        CheckConstraint("status != 'SENT' OR expires_at IS NOT NULL", name="sent_has_expiry"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    channel: Mapped[Channel] = mapped_column(StrEnumText(Channel))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[OutreachStatus] = mapped_column(StrEnumText(OutreachStatus))
