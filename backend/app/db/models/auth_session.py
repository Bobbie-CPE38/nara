import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core import auth_clock
from app.db.base import Base


class AuthSession(Base):
    """One login (round 6 PR AU1, docs/database-schema.md).

    The cookie holds a random token; only its SHA-256 is stored. A session is valid
    while real UTC now is before both expires_at and last_seen_at + idle seconds, it is
    not revoked, and its credential_version is the account's current one.
    A demo reset deletes every row.
    """

    __tablename__ = "auth_session"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_sha256_hex"),
        CheckConstraint("credential_version > 0", name="credential_version_positive"),
        CheckConstraint(
            "created_at <= last_seen_at AND last_seen_at <= expires_at AND expires_at > created_at",
            name="time_order",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_subject: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_account.staff_subject", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    credential_version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=auth_clock.now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
