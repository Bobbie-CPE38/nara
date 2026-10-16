from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import CandidateSource


class CandidateItem(Base):
    __tablename__ = "candidate_items"
    __table_args__ = (
        # Alembic does not compare CHECK constraints: change these only with a migration
        CheckConstraint(
            "(cover_start_at IS NULL) = (cover_end_at IS NULL)", name="cover_both_or_neither"
        ),
        CheckConstraint("cover_start_at < cover_end_at", name="cover_in_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_plans.id"))
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    rank: Mapped[int] = mapped_column(Integer)
    source: Mapped[CandidateSource] = mapped_column(StrEnumText(CandidateSource))
    proposed_shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    # The snapshot the Solver ranked this candidate with. NULL only on rows from before round 1
    working_time_snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("staff_working_time_snapshot.id")
    )
    # The part of the shift this candidate covers. Both NULL means the whole shift
    cover_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cover_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The roster row the candidate is moved out of. NULL means the candidate is not being moved
    source_assignment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("roster_assignment.id")
    )
