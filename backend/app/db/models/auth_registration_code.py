"""One-time web signup proof issued to a currently bound personal LINE account."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import auth_clock
from app.db.base import Base


class AuthRegistrationCode(Base):
    __tablename__ = "auth_registration_code"
    __table_args__ = (
        CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="code_hash_sha256_hex"),
        CheckConstraint("line_uid_hash ~ '^[0-9a-f]{64}$'", name="uid_hash_sha256_hex"),
        CheckConstraint("expires_at > created_at", name="time_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_subject: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.auth_subject", ondelete="RESTRICT"), index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, unique=True)
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"))
    line_uid_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=auth_clock.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
