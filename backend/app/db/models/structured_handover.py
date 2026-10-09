from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StructuredHandover(Base):
    __tablename__ = "structured_handover"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staffing_cases.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    incoming_staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
