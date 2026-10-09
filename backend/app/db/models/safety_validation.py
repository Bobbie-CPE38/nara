from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SafetyValidation(Base):
    __tablename__ = "safety_validation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    hard_constraint_policy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hard_constraint_policy.id")
    )
    is_passed: Mapped[bool] = mapped_column(Boolean)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # Per-rule results use ValidationResult (PASS / FAIL)
    validation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
