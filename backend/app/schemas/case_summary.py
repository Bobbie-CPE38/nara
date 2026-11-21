"""Public summary fields; never expose snapshot, prompt, failure details or usage."""

from pydantic import BaseModel

from app.domain.enums import ExplanationBlock, ExplanationViewStatus
from app.schemas.types import AppDatetime


class SummaryCurrent(BaseModel):
    summary_id: int | None
    status: ExplanationViewStatus
    text: str | None
    generated_at: AppDatetime | None
    stale: bool
    can_request: bool
    request_blocked_reason: ExplanationBlock | None


class SummaryHistory(BaseModel):
    summary_id: int
    text: str
    generated_at: AppDatetime


class CaseSummaryView(BaseModel):
    current: SummaryCurrent
    history: list[SummaryHistory]
