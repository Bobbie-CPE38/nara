from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base
from app.db.types import StrEnumText
from app.domain.enums import StaffStatus


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"))
    home_ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ward.id"))
    # Employment status only. Leave is stored in STAFF_UNAVAILABILITY
    status: Mapped[StaffStatus] = mapped_column(StrEnumText(StaffStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
