from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class Ward(Base):
    __tablename__ = "ward"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean)
