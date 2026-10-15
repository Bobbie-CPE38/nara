from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import AssignmentType, CandidateSource, RosterStatus


class RosterAssignment(Base):
    __tablename__ = "roster_assignment"
    __table_args__ = (
        CheckConstraint("actual_start_at < actual_end_at", name="actual_times_in_order"),
        UniqueConstraint("transferred_from_assignment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    status: Mapped[RosterStatus] = mapped_column(StrEnumText(RosterStatus))
    assignment_type: Mapped[AssignmentType] = mapped_column(StrEnumText(AssignmentType))
    candidate_source: Mapped[CandidateSource | None] = mapped_column(StrEnumText(CandidateSource))
    # Each NULL endpoint falls back to the corresponding Shift endpoint.
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transferred_from_assignment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("roster_assignment.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
