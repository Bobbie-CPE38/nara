from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingRequirementSkill(Base):
    __tablename__ = "staffing_requirement_skill"

    staffing_requirement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staffing_requirements.id"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), primary_key=True)
    required_count: Mapped[int] = mapped_column(Integer)
