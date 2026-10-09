from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandidateOutreach(Base):
    __tablename__ = "candidate_outreach"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    channel: Mapped[str] = mapped_column(Text)  # Channel
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)  # OutreachStatus
