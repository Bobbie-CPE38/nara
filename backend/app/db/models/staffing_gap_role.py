from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingGapRole(Base):
    __tablename__ = "staffing_gap_role"

    gap_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_gap.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"), primary_key=True)
    required_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)
