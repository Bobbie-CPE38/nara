from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffWorkingTimeSnapshot(Base):
    __tablename__ = "staff_working_time_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    hours_today: Mapped[Decimal] = mapped_column(Numeric)
    hours_this_week: Mapped[Decimal] = mapped_column(Numeric)
    rest_hours: Mapped[Decimal] = mapped_column(Numeric)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric)
    consecutive_shifts: Mapped[int] = mapped_column(Integer)
    consecutive_night_shifts: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
