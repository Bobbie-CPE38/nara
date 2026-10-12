"""
Work that becomes due with time (docs/workflow.md, section 3.8).

One function for both callers, so they can never drift apart: the job service
calls it every 30 seconds through POST /internal/merge-windows/close-due, and
POST /demo/clock/advance calls it after moving the demo clock, because a frozen
clock makes nothing due by itself.

"Due" is always judged with the backend clock (core/clock.py). The job service
only keeps the rhythm: it runs in another process and sees real time only.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services import merge_window_service
from app.services.merge_window_service import ClosedWindow


@dataclass(frozen=True)
class DueWork:
    closed_windows: list[ClosedWindow]


def run_due_work(db: Session) -> DueWork:
    """Close every merge window that is due. Commits one transaction per shift.

    Round 1 PR O adds the offers that timed out to the same round.
    """
    return DueWork(closed_windows=merge_window_service.close_due_windows(db))
