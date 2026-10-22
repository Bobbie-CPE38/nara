"""Login API bodies (docs/workflow.md 6.33.3, round 6 PR AU1).

Every request body forbids extra fields, so no role, ward, actor or other staff can be
slipped in. Passwords are taken exactly as sent: no trimming.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.core.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.schemas.types import MAX_BIGINT
from app.services.auth_service import ApiRole

# A login answers 401 for any wrong password, whatever its length. This bound only
# stops an oversized body from reaching the hash
LoginPassword = Annotated[StrictStr, Field(max_length=1024)]
NewPassword = Annotated[
    StrictStr, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
]


class AuthConfig(BaseModel):
    auth_mode: Literal["demo", "session"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: Annotated[StrictInt, Field(ge=1, le=MAX_BIGINT)]
    password: LoginPassword


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: LoginPassword
    new_password: NewPassword


class AuthMe(BaseModel):
    """No hash, token or session id."""

    staff_id: int
    role: ApiRole
    home_ward_id: int
    must_change_password: bool


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[StrictStr, Field(max_length=128)]
    password: NewPassword


class RegisteredAccount(BaseModel):
    staff_id: int
