"""Decision of one required ward side; the request stores the final aggregate.

A person's decision has `approver_id`; a side the system approved (round 6 PR EV9, 6.39)
has `approval_mode` AUTO, no approver, `decided_as` naming the queue that was over its cap
(the side ward's Head Nurse queue or the Supervisor queue) and that queue's numbers.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import ApprovalMode, ApprovalSide, ApproverCapacity


class ApprovalWardDecision(Base):
    __tablename__ = "approval_ward_decision"
    __table_args__ = (
        UniqueConstraint("approval_request_id", "side"),
        CheckConstraint(
            "(approval_mode = 'MANUAL' AND approver_id IS NOT NULL AND queue_count IS NULL"
            " AND queue_cap IS NULL AND queue_approver_count IS NULL)"
            " OR (approval_mode = 'AUTO' AND approver_id IS NULL AND is_approved"
            " AND queue_count IS NOT NULL AND queue_cap IS NOT NULL"
            " AND queue_approver_count IS NOT NULL AND queue_count > queue_cap)",
            name="mode_matches_decider",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    approval_request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_request.id"))
    ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ward.id"))
    side: Mapped[ApprovalSide] = mapped_column(StrEnumText(ApprovalSide))
    approver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    decided_as: Mapped[ApproverCapacity] = mapped_column(StrEnumText(ApproverCapacity))
    is_approved: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        StrEnumText(ApprovalMode), default=ApprovalMode.MANUAL
    )
    # AUTO only: the queue that was over its cap when the side was decided
    queue_count: Mapped[int | None] = mapped_column(Integer)
    queue_cap: Mapped[Decimal | None] = mapped_column(Numeric)
    queue_approver_count: Mapped[int | None] = mapped_column(Integer)
