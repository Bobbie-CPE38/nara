"""Real UTC time for accounts and sessions (docs/workflow.md 6.33.2).

The one exception to app.core.clock: a session or a registration code expires on the
real clock, so freezing, advancing or resetting the Demo Clock never keeps one alive.
Tests replace `now` to move past an expiry.
"""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
