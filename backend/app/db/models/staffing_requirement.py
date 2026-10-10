from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class StaffingRequirement(Base):
    __tablename__ = "staffing_requirements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    required_staff: Mapped[int] = mapped_column(Integer)
    minimum_staff: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
