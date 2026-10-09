"""Field types shared by the API schemas."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from app.core import clock


def _to_app_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(clock.APP_TIMEZONE)


# A moment in time, always sent as +07:00 (docs/workflow.md, section 9.3).
# PostgreSQL returns timestamptz in the session time zone, which is UTC, so a
# plain datetime field would send "...Z" for a row that was read from the DB.
AppDatetime = Annotated[datetime, AfterValidator(_to_app_timezone)]
