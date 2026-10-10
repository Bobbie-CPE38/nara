from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffingGap(Base):
    __tablename__ = "staffing_gap"
    __table_args__ = (
        # Same rule as HARD_CONSTRAINT_POLICY: PostgreSQL sorts NaN above Infinity
        CheckConstraint(
            "patients_per_nurse > 0 AND patients_per_nurse < 'Infinity'::numeric",
            name="patients_per_nurse_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    staffing_requirement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staffing_requirements.id")
    )
    headcount_gap: Mapped[int] = mapped_column(Integer)
    # Snapshot of the inputs of this calculation: SHIFT.patient_count and
    # HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse can both change later
    patient_count: Mapped[int] = mapped_column(Integer)
    patients_per_nurse: Mapped[Decimal] = mapped_column(Numeric)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
