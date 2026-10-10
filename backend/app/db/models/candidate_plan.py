from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import SolverStatus


class CandidatePlan(Base):
    __tablename__ = "candidate_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    solver_status: Mapped[SolverStatus] = mapped_column(StrEnumText(SolverStatus))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execution_time_ms: Mapped[int] = mapped_column(Integer)
    objective_score: Mapped[Decimal | None] = mapped_column(Numeric)
    # Skeleton = "stub"
    solver_version: Mapped[str] = mapped_column(Text)
    hard_constraint_policy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hard_constraint_policy.id")
    )
    soft_constraint_policy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("soft_constraint_policy.id")
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
