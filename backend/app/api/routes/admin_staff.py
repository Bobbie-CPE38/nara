"""Small supervisor-only staff directory and existing LINE link-code issuance.

A real web session is required in BOTH auth modes. Demo headers and the shared
Demo Basic credential never grant staff-administration rights.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, false, func, select

from app.api.dependencies import (
    AUTH_PASSWORD_CHANGE_REQUIRED,
    DbSession,
    SessionUserDep,
    forbidden,
)
from app.core.constants import MAX_BIGINT
from app.core.rate_limit import LINE_ADMIN_PER_MINUTE, Limit, limiter
from app.db.models import Actor, AuthAccount, Contact, Role, Skill, Staff, StaffSkill, Ward
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
    line_binding_present: bool
    # Round 6 PR EV7 (6.37.6): the skills by name, and whether the person has a web account
    skills: list[str]
    has_account: bool


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
    # Numeric searches identify ONE employee, never substring-match other IDs.
    if term.isascii() and term.isdecimal():
        condition = (
            Staff.id == int(term) if len(term) <= 19 and 1 <= int(term) <= MAX_BIGINT else false()
        )
    else:
        condition = (Staff.first_name + " " + Staff.last_name).icontains(term, autoescape=True)
    directory = (
        select(Staff, Role.name, Ward.name)
        .join(Role, Role.id == Staff.role_id)
        .join(Ward, Ward.id == Staff.home_ward_id)
        .where(condition)
    )
    # Count exactly the joined/filtered row set used for the page.
    total = db.scalar(select(func.count()).select_from(directory.subquery())) or 0
    bound = exists(
        select(Contact.id).where(Contact.staff_id == Staff.id, Contact.line_uid.is_not(None))
    )
    usable = (
        (Staff.status == StaffStatus.ACTIVE)
        & exists(select(Actor.id).where(Actor.staff_id == Staff.id))
        & exists(
            select(Contact.id).where(
                Contact.staff_id == Staff.id,
                Contact.line_uid.is_not(None),
                Contact.is_active.is_(True),
            )
        )
    )
    rows = db.execute(
        directory.add_columns(bound, usable).order_by(Staff.id).offset(offset).limit(limit)
    ).all()
    page_ids = [staff.id for staff, *_ in rows]
    skills: dict[int, list[str]] = {staff_id: [] for staff_id in page_ids}
    for staff_id, skill in db.execute(
        select(StaffSkill.staff_id, Skill.name)
        .join(Skill, Skill.id == StaffSkill.skill_id)
        .where(StaffSkill.staff_id.in_(page_ids))
        .order_by(StaffSkill.staff_id, Skill.name)
    ):
        skills[staff_id].append(skill)
    with_account = set(
        db.scalars(
            select(Staff.id)
            .join(AuthAccount, AuthAccount.staff_subject == Staff.auth_subject)
            .where(Staff.id.in_(page_ids))
        )
    )
    return StaffPage(
        items=[
            StaffEntry(
                id=staff.id,
                first_name=staff.first_name,
                last_name=staff.last_name,
                role=role,
                ward_name=ward,
                status=staff.status,
                line_linked=usable_binding,
                line_binding_present=linked,
                skills=skills[staff.id],
                has_account=staff.id in with_account,
            )
            for staff, role, ward, linked, usable_binding in rows
        ],
        total=total,
    )


@router.post("/{staff_id}/line-code", status_code=201)
def issue_line_code(
    staff_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    db: DbSession,
    user: Supervisor,
) -> IssuedLineCode:
    _limit_admin(user)
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
    _limit_admin(user)
    # Check on the server too: a browser's disabled button is not authorization.
    if body.confirm_staff_id != str(staff_id):
        raise HTTPException(400, "LINE_CONFIRMATION_MISMATCH")
    try:
        count = line_account_service.unlink(
            db, staff_id, actor_id=user.actor_id, require_binding=True
        )
        db.commit()
    except line_account_service.LineAccountNotBoundError:
        db.rollback()
        raise HTTPException(409, "LINE_NOT_LINKED") from None
    except line_account_service.LinkStaffUnavailableError:
        db.rollback()
        raise HTTPException(409, "LINE_STAFF_UNAVAILABLE") from None
    return UnlinkedLineAccount(unlinked_contacts=count)


def _limit_admin(user: auth_service.SessionUser) -> None:
    # Shared budget prevents alternating issue/unlink to double the allowed work.
    wait = limiter.hit([Limit(f"line-admin:{user.staff.id}", LINE_ADMIN_PER_MINUTE)])
    if wait is not None:
        raise HTTPException(429, "AUTH_RATE_LIMITED", headers={"Retry-After": str(wait)})
