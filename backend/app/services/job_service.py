"""
Work that becomes due with time (docs/workflow.md, section 3.8).

One function for both callers, so they can never drift apart: the job service
calls it every 30 seconds through POST /internal/merge-windows/close-due, and
POST /demo/clock/advance calls it after moving the demo clock, because a frozen
clock makes nothing due by itself.

"Due" is always judged with the backend clock (core/clock.py). The job service
only keeps the rhythm: it runs in another process and sees real time only.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services import merge_window_service, offer_timeout_service
from app.services.merge_window_service import ClosedWindow


@dataclass(frozen=True)
class DueWork:
    closed_windows: list[ClosedWindow]
    timed_out_outreach_ids: list[int] = field(default_factory=list)
    recovered_case_ids: list[int] = field(default_factory=list)


def run_due_work(db: Session) -> DueWork:
    """Expire offers, recover missed notifications, then close due merge windows.

    Case work commits per case; window work commits per shift. Releasing a case
    first lets its queued window close in this same tick. Route response shapes
    remain unchanged; service callers can inspect timeout/recovery IDs.
    """
    expired = offer_timeout_service.expire_due_offers(db)
    recovered = offer_timeout_service.recover_waiting_cases(
        db, excluded_case_ids=expired.failed_case_ids
    )
    return DueWork(
        closed_windows=merge_window_service.close_due_windows(db),
        timed_out_outreach_ids=expired.outreach_ids,
        recovered_case_ids=recovered,
    )
