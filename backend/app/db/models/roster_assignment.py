from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base, StrEnumText
from app.domain.enums import AssignmentType, CandidateSource, RosterStatus


class RosterAssignment(Base):
    __tablename__ = "roster_assignment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    status: Mapped[RosterStatus] = mapped_column(StrEnumText(RosterStatus))
    assignment_type: Mapped[AssignmentType] = mapped_column(StrEnumText(AssignmentType))
    candidate_source: Mapped[CandidateSource | None] = mapped_column(StrEnumText(CandidateSource))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
