from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingRequirementRole(Base):
    __tablename__ = "staffing_requirement_role"

    staffing_requirement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staffing_requirements.id"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"), primary_key=True)
    required_count: Mapped[int] = mapped_column(Integer)
