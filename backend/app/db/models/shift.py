from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import ShiftType


class Shift(Base):
    __tablename__ = "shift"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ward.id"))
    patient_count: Mapped[int] = mapped_column(Integer)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shift_type: Mapped[ShiftType] = mapped_column(StrEnumText(ShiftType))
    is_active: Mapped[bool] = mapped_column(Boolean)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
