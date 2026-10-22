import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import auth_clock
from app.db.base import Base


class AuthAccount(Base):
    """The web login of one permanent person (round 6 PR AU1, docs/database-schema.md).

    Not every staff member has one: an account is made by the account script, or by
    REGISTER in AU5. Role and ward are read from STAFF on every request, not stored here.
    Timestamps are real UTC (app.core.auth_clock), not the Demo Clock.
    """

    __tablename__ = "auth_account"
    __table_args__ = (
        CheckConstraint("credential_version > 0", name="credential_version_positive"),
    )

    staff_subject: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.auth_subject", ondelete="RESTRICT"),
        primary_key=True,
    )
    # Argon2id encoded hash with its own salt and parameters, never the password
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sql_text("false")
    )
    # Closing the account, separate from STAFF.status: both must allow a login
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Raised by every password change or reset; a session of an older version is dead
    credential_version: Mapped[int] = mapped_column(
        BigInteger, default=1, server_default=sql_text("1")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=auth_clock.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=auth_clock.now)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=auth_clock.now
    )
