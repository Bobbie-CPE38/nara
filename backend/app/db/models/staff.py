import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import StaffStatus


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    # Kept for compatibility (the seed writes "!"). Login never reads it: passwords live
    # in AUTH_ACCOUNT (round 6 PR AU1)
    password_hash: Mapped[str] = mapped_column(Text)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"))
    home_ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ward.id"))
    # Employment status only. Leave is stored in STAFF_UNAVAILABILITY
    status: Mapped[StaffStatus] = mapped_column(StrEnumText(StaffStatus))
    # The permanent person behind this row and its web account (docs/workflow.md 6.33.2).
    # Random once, never changed (a trigger refuses an UPDATE) and never given to someone
    # else. A demo reset hands the same subject back to the same staff ID
    auth_subject: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
