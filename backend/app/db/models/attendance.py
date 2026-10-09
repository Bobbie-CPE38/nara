from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_minutes: Mapped[int | None] = mapped_column(Integer)
    overtime_minutes: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
