from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class LineAccountLinkCode(Base):
    __tablename__ = "line_account_link_code"
    __table_args__ = (
        UniqueConstraint("code_hash"),
        CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        CheckConstraint("expires_at > created_at", name="positive_lifetime"),
        CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name="single_terminal_state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"), index=True)
    code_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
