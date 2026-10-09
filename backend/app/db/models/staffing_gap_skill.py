from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingGapSkill(Base):
    __tablename__ = "staffing_gap_skill"

    gap_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_gap.id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), primary_key=True)
    required_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)
