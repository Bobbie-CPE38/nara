from pydantic import BaseModel

from app.domain.enums import CaseStatus


class HandlerResult(BaseModel):
    """Requested transition; wait=True tells the orchestrator to stop this round."""

    next_status: CaseStatus
    wait: bool = False
