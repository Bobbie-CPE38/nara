"""Merge Gap scenario: the night shift of the Golden Case waits ten minutes.

Call after base_data.seed() and golden_case.seed(). Only the row that differs
from the Golden Case is changed. Used by tests in round 1; there is no button
that loads it (docs/round1/round1-contract-draft.md, section 9.1).

With the window open, 104 and 105 can both report leave for shift 1 and get one
case that needs two people. An event that arrives while that case is still
running waits for it to end.
"""

from sqlalchemy.orm import Session

from app.db.models import Shift

SHIFT_ID = 1
MERGE_WINDOW_SECONDS = 600


def seed(db: Session) -> None:
    """Give shift 1 a merge window, leaving the commit to the caller."""
    shift = db.get(Shift, SHIFT_ID)
    if shift is None:
        raise ValueError("Load the Golden Case before the merge gap scenario")
    shift.merge_window_seconds = MERGE_WINDOW_SECONDS
    db.flush()
