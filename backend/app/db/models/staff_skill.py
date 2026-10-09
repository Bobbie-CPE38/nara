from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffSkill(Base):
    __tablename__ = "staff_skill"

    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), primary_key=True)
