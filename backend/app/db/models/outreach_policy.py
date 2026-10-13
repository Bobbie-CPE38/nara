from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class OutreachPolicy(Base):
    __tablename__ = "outreach_policy"
    __table_args__ = (
        CheckConstraint("maximum_concurrent_offers_per_staff > 0", name="offer_limit_positive"),
        CheckConstraint("offer_timeout_seconds > 0", name="offer_timeout_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    maximum_concurrent_offers_per_staff: Mapped[int] = mapped_column(Integer)
    offer_timeout_seconds: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
