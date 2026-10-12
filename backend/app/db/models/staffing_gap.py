from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingGap(Base):
    __tablename__ = "staffing_gap"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    staffing_requirement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staffing_requirements.id")
    )
    headcount_gap: Mapped[int] = mapped_column(Integer)
    # The headcount target this gap was measured against. The requirement row is
    # updated in place later, so this is the only record of the target at that time
    effective_minimum: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
