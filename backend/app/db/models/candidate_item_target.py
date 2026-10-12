from sqlalchemy import BigInteger, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, StrEnumText
from app.domain.enums import SelectionType, TargetType


class CandidateItemTarget(Base):
    """One target a candidate was selected to fill. A candidate can hold several rows."""

    __tablename__ = "candidate_item_target"
    __table_args__ = (
        # Alembic does not compare CHECK constraints: change these only with a migration
        CheckConstraint(
            "(target_type = 'ROLE') = (role_id IS NOT NULL)",
            name="role_id_matches_target_type",
        ),
        CheckConstraint(
            "(target_type = 'SKILL') = (skill_id IS NOT NULL)",
            name="skill_id_matches_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("candidate_items.id"))
    target_type: Mapped[TargetType] = mapped_column(StrEnumText(TargetType))
    role_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("role.id"))
    skill_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill.id"))
    selection_type: Mapped[SelectionType] = mapped_column(StrEnumText(SelectionType))
