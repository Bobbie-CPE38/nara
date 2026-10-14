"""Sensitive, administrator-only command results; never cache/log raw codes."""

from pydantic import BaseModel, Field

from app.schemas.types import AppDatetime


class IssuedLineCode(BaseModel):
    code: str = Field(repr=False)
    expires_at: AppDatetime


class UnlinkedLineAccount(BaseModel):
    unlinked_contacts: int
