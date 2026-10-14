from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class ManualAssignment(Base):
    """One person a head nurse put on the shift of a MANUAL_HANDOFF case.

    Ties the roster row to the case, which ROSTER_ASSIGNMENT cannot do
    (workflow.md section 6.12). The person, the shift and the status are read
    from the roster row, never copied here.
    """

    __tablename__ = "manual_assignment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"), index=True)
    # One roster row closes the gap of one case only
    roster_assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roster_assignment.id"), unique=True
    )
    assigned_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    # A note of the head nurse. It never changes the Hard Rule result
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
