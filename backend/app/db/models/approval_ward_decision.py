"""Human decision of one required ward; the request stores the final aggregate."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import ApprovalSide, ApproverCapacity


class ApprovalWardDecision(Base):
    __tablename__ = "approval_ward_decision"
    __table_args__ = (UniqueConstraint("approval_request_id", "side"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    approval_request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_request.id"))
    ward_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ward.id"))
    side: Mapped[ApprovalSide] = mapped_column(StrEnumText(ApprovalSide))
    approver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    decided_as: Mapped[ApproverCapacity] = mapped_column(StrEnumText(ApproverCapacity))
    is_approved: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
