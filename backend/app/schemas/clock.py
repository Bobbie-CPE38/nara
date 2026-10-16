from pydantic import BaseModel

from app.schemas.types import AppDatetime


class ClockView(BaseModel):
    """GET /clock: the time the backend runs on (docs/workflow.md 9.7, R5-Q18)."""

    now: AppDatetime
    # True while the demo clock is frozen; False when it follows real time
    frozen: bool
