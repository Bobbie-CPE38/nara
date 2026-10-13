from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class SoftConstraintPolicy(Base):
    __tablename__ = "soft_constraint_policy"

    __table_args__ = (
        CheckConstraint("solver_time_limit_seconds > 0", name="solver_time_limit_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(Text)
    candidate_count_weight: Mapped[Decimal] = mapped_column(Numeric)
    consecutive_shift_weight: Mapped[Decimal] = mapped_column(Numeric)
    workload_imbalance_weight: Mapped[Decimal] = mapped_column(Numeric)
    projected_overtime_weight: Mapped[Decimal] = mapped_column(Numeric)
    roster_change_weight: Mapped[Decimal] = mapped_column(Numeric)
    # Weight of the source term of plan_penalty. The order of the sources is
    # candidate_source_priority
    candidate_source_weight: Mapped[Decimal] = mapped_column(Numeric)
    # Ordering of CandidateSource values; JSON shape not fixed yet
    candidate_source_priority: Mapped[Any] = mapped_column(JSONB)
    # Ordering of OptimizationObjective values; JSON shape not fixed yet
    optimization_priority: Mapped[Any] = mapped_column(JSONB)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
    solver_time_limit_seconds: Mapped[int] = mapped_column(Integer)
