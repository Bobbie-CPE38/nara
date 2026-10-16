"""Snapshot read model shared by the nurse and case APIs."""

from typing import Any

from pydantic import BaseModel

from app.schemas.types import AppDatetime


class HandoverView(BaseModel):
    handover_id: int
    roster_assignment_id: int
    active: bool
    generated_at: AppDatetime
    # Keep unknown keys/versions intact for future readers (workflow.md 6.25).
    content: dict[str, Any]
