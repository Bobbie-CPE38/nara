from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import ApprovalMode


class ApprovalRequest(Base):
    __tablename__ = "approval_request"

    __table_args__ = (
        Index(
            "ix_approval_request_pending_expiry",
            "expires_at",
            postgresql_where=text("is_pending = true"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    outreach_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_outreach.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # is_approved=False means no assignment approval; consult is_timed_out before
    # calling a negative outcome a head-nurse rejection. Only the job sets this flag.
    is_timed_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    required_approver_role: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("role.id"))
    approval_mode: Mapped[ApprovalMode] = mapped_column(StrEnumText(ApprovalMode))
    is_pending: Mapped[bool] = mapped_column(Boolean)
    approver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    is_approved: Mapped[bool | None] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
