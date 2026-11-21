from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class ApprovalPolicy(Base):
    __tablename__ = "approval_policy"

    __table_args__ = (
        CheckConstraint("approval_timeout_seconds > 0", name="approval_timeout_positive"),
        CheckConstraint(
            "supervisor_after_seconds > 0 AND supervisor_after_seconds < approval_timeout_seconds",
            name="supervisor_delay_valid",
        ),
        CheckConstraint(
            "supervisor_ratio >= 0 AND supervisor_incoming_count >= 0",
            name="supervisor_capacity_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ratio: Mapped[Decimal] = mapped_column(Numeric)
    incoming_count: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    approval_timeout_seconds: Mapped[int] = mapped_column(Integer)
    supervisor_after_seconds: Mapped[int] = mapped_column(Integer)
    # The Supervisor queue's capacity (round 6 PR EV9, 6.39): ratio x active Supervisors,
    # at most incoming_count, apart from the Head Nurse's ratio and incoming_count above
    supervisor_ratio: Mapped[Decimal] = mapped_column(Numeric)
    supervisor_incoming_count: Mapped[int] = mapped_column(Integer)
