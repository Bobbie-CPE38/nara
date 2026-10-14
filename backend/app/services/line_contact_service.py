"""Shared active LINE bindings; PR K owns creation and uniqueness migration."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Actor, Contact, Staff
from app.domain.enums import StaffStatus


def staff_for_line_uid(db: Session, uid: str) -> tuple[int, int] | None:
    rows = db.execute(
        select(Contact.staff_id, Actor.id)
        .join(Staff, Staff.id == Contact.staff_id)
        .join(Actor, Actor.staff_id == Staff.id)
        .where(
            Contact.line_uid == uid, Contact.is_active.is_(True), Staff.status == StaffStatus.ACTIVE
        )
        .limit(2)
    ).all()
    return (rows[0][0], rows[0][1]) if len(rows) == 1 else None


def line_uid_for_staff(db: Session, staff_id: int) -> str | None:
    uids = list(
        db.scalars(
            select(Contact.line_uid)
            .where(
                Contact.staff_id == staff_id,
                Contact.is_active.is_(True),
                Contact.line_uid.is_not(None),
            )
            .limit(2)
        )
    )
    if len(uids) != 1 or not uids[0]:
        return None
    staff = staff_for_line_uid(db, uids[0])
    return uids[0] if staff is not None and staff[0] == staff_id else None
