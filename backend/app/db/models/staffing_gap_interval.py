"""Time slices of a STAFFING_GAP (round 4 PR T3, docs/workflow.md 6.20).

A gap is measured from evaluated_from to the end of the shift. That window is cut
wherever a covering roster row starts or ends, and each slice stores the
headcount, role and skill counts of that slice. The three tables share the same
slices. Slices are [start_at, end_at). A gap written before round 4 has no slice.
"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_COUNTS_VALID = (
    "required_count >= 0 AND current_count >= 0 "
    "AND gap_count = GREATEST(required_count - current_count, 0)"
)


class StaffingGapInterval(Base):
    __tablename__ = "staffing_gap_interval"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="times_in_order"),
        CheckConstraint(_COUNTS_VALID, name="counts_valid"),
        UniqueConstraint("gap_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gap_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_gap.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    required_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)


class StaffingGapRoleInterval(Base):
    __tablename__ = "staffing_gap_role_interval"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="times_in_order"),
        CheckConstraint(_COUNTS_VALID, name="counts_valid"),
        UniqueConstraint("gap_id", "role_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gap_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_gap.id"), index=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    required_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)


class StaffingGapSkillInterval(Base):
    __tablename__ = "staffing_gap_skill_interval"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="times_in_order"),
        CheckConstraint(_COUNTS_VALID, name="counts_valid"),
        UniqueConstraint("gap_id", "skill_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gap_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_gap.id"), index=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    required_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)
