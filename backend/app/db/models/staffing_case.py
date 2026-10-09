from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base
from app.db.types import StrEnumText
from app.domain.enums import CaseStatus


class StaffingCase(Base):
    __tablename__ = "staffing_cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_events.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    # Only the orchestrator changes this (docs/workflow.md)
    status: Mapped[CaseStatus] = mapped_column(StrEnumText(CaseStatus))
    required_replacement_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, onupdate=clock.now
    )
