"""Small supervisor-only staff directory and existing LINE link-code issuance.

A real web session is required in BOTH auth modes. Demo headers and the shared
Demo Basic credential never grant staff-administration rights.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, exists, func, or_, select

from app.api.dependencies import (
    AUTH_PASSWORD_CHANGE_REQUIRED,
    DbSession,
    SessionUserDep,
    forbidden,
)
from app.core.constants import MAX_BIGINT
from app.core.rate_limit import Limit, limiter
from app.db.models import Contact, Role, Staff, Ward
from app.domain.enums import StaffStatus
from app.schemas.line_account import IssuedLineCode, UnlinkedLineAccount
from app.services import auth_service, line_account_service

router = APIRouter(prefix="/admin/staff", tags=["staff administration"])


def supervisor(user: SessionUserDep) -> auth_service.SessionUser:
    if user.must_change_password:
        raise HTTPException(403, AUTH_PASSWORD_CHANGE_REQUIRED)
    if user.role != "supervisor":
        raise forbidden()
    return user


Supervisor = Annotated[auth_service.SessionUser, Depends(supervisor)]


class StaffEntry(BaseModel):
    id: int
    first_name: str
    last_name: str
    role: str
    ward_name: str
    status: StaffStatus
    line_linked: bool


class StaffPage(BaseModel):
    items: list[StaffEntry]
    total: int


@router.get("")
def list_staff(
    db: DbSession,
    user: Supervisor,
    q: Annotated[str, Query(max_length=100)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StaffPage:
    term = q.strip()
    # Escape wildcard characters: search is literal, not an SQL LIKE expression.
    condition = or_(
        cast(Staff.id, String).contains(term, autoescape=True),
        (Staff.first_name + " " + Staff.last_name).icontains(term, autoescape=True),
    )
    total = db.scalar(select(func.count()).select_from(Staff).where(condition)) or 0
    bound = exists(
        select(Contact.id).where(Contact.staff_id == Staff.id, Contact.line_uid.is_not(None))
    )
    rows = db.execute(
        select(Staff, Role.name, Ward.name, bound)
        .join(Role, Role.id == Staff.role_id)
        .join(Ward, Ward.id == Staff.home_ward_id)
        .where(condition)
        .order_by(Staff.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return StaffPage(
        items=[
            StaffEntry(
                id=staff.id,
                first_name=staff.first_name,
                last_name=staff.last_name,
                role=role,
                ward_name=ward,
                status=staff.status,
                line_linked=linked,
            )
            for staff, role, ward, linked in rows
        ],
        total=total,
    )


@router.post("/{staff_id}/line-code", status_code=201)
def issue_line_code(
    staff_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    db: DbSession,
    user: Supervisor,
) -> IssuedLineCode:
    wait = limiter.hit([Limit(f"line-code:admin:{user.staff.id}", 20)])
    if wait is not None:
        raise HTTPException(429, "AUTH_RATE_LIMITED", headers={"Retry-After": str(wait)})
    try:
        issued = line_account_service.issue_code(db, staff_id)
        db.commit()
    except line_account_service.LineAccountAlreadyBoundError:
        db.rollback()
        raise HTTPException(409, "LINE_ALREADY_LINKED") from None
    except line_account_service.LinkStaffUnavailableError:
        db.rollback()
        raise HTTPException(409, "LINE_STAFF_UNAVAILABLE") from None
    return IssuedLineCode(code=issued.code.get_secret_value(), expires_at=issued.expires_at)


class UnlinkConfirmation(BaseModel):
    confirm_staff_id: str = Field(strict=True, pattern=r"^[1-9][0-9]{0,18}$")


@router.post("/{staff_id}/line-unlink")
def unlink_line_account(
    staff_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    body: UnlinkConfirmation,
    db: DbSession,
    user: Supervisor,
) -> UnlinkedLineAccount:
    # Check on the server too: a browser's disabled button is not authorization.
    if body.confirm_staff_id != str(staff_id):
        raise HTTPException(400, "LINE_CONFIRMATION_MISMATCH")
    try:
        count = line_account_service.unlink(db, staff_id, actor_id=user.actor_id)
        db.commit()
    except line_account_service.LinkStaffUnavailableError:
        db.rollback()
        raise HTTPException(409, "LINE_STAFF_UNAVAILABLE") from None
    return UnlinkedLineAccount(unlinked_contacts=count)
