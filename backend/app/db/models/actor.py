from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import StrEnumText
from app.domain.enums import ActorType


class Actor(Base):
    __tablename__ = "actors"
    __table_args__ = (
        # A user actor must be linked to a staff member, and only a user actor may be
        CheckConstraint(
            f"(actor_type = '{ActorType.USER.value}') = (staff_id IS NOT NULL)",
            name="user_has_staff",
        ),
        # One actor per staff member
        UniqueConstraint("staff_id"),
        # One row per system/component name
        Index(
            "uq_actors_name_non_user",
            "name",
            unique=True,
            postgresql_where=text(f"actor_type <> '{ActorType.USER.value}'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # user: str(staff.id) / others: ActorName
    name: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[ActorType] = mapped_column(StrEnumText(ActorType))
    staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
