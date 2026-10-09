from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import AvailabilityReason


class StaffUnavailability(Base):
    """Periods when a staff member is unavailable. No row means available."""

    __tablename__ = "staff_unavailability"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL = return date not known yet
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Never changes after the row is created
    reason: Mapped[AvailabilityReason] = mapped_column(StrEnumText(AvailabilityReason))
