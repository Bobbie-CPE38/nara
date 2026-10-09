from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import CandidateSource


class CandidateItem(Base):
    __tablename__ = "candidate_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_plans.id"))
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id"))
    rank: Mapped[int] = mapped_column(Integer)
    source: Mapped[CandidateSource] = mapped_column(StrEnumText(CandidateSource))
    proposed_shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
