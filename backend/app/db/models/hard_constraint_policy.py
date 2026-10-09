from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class HardConstraintPolicy(Base):
    __tablename__ = "hard_constraint_policy"
    __table_args__ = (
        CheckConstraint(
            "maximum_patients_per_nurse > 0 AND maximum_patients_per_nurse < 'Infinity'::numeric",
            name="maximum_patients_per_nurse_positive_finite",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(Text)
    minimum_rest_hours: Mapped[Decimal] = mapped_column(Numeric)
    maximum_daily_hours: Mapped[Decimal] = mapped_column(Numeric)
    maximum_weekly_hours: Mapped[Decimal] = mapped_column(Numeric)
    maximum_patients_per_nurse: Mapped[Decimal] = mapped_column(Numeric)
    prevent_shift_conflict: Mapped[bool] = mapped_column(Boolean)
    require_matching_role: Mapped[bool] = mapped_column(Boolean)
    require_matching_skill: Mapped[bool] = mapped_column(Boolean)
    require_active_staff: Mapped[bool] = mapped_column(Boolean)
    preserve_minimum_staffing: Mapped[bool] = mapped_column(Boolean)
    preserve_source_ward_minimum: Mapped[bool] = mapped_column(Boolean)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
