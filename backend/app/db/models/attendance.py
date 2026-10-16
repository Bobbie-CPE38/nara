from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        # Passes while either column is NULL: NULL = not summarised yet, not 0
        CheckConstraint(
            "overtime_minutes >= 0 AND overtime_minutes <= work_minutes",
            name="overtime_within_work",
        ),
        # One check-in per staff member per shift (docs/workflow.md 6.24); old rows have no shift
        Index(
            "uq_attendance_staff_shift",
            "staff_id",
            "shift_id",
            unique=True,
            postgresql_where=text("shift_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    # NULL for rows that predate shift-based check-in
    shift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("shift.id"))
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # All time actually worked, overtime included
    work_minutes: Mapped[int | None] = mapped_column(Integer)
    # The part of work_minutes that is overtime, not added on top of it
    overtime_minutes: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
