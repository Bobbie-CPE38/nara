from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class LlmDailyUsage(Base):
    """Attempts sent in one LLM_QUOTA_TIMEZONE day, DEMO scope only (round 6 PR B1).

    A new day is a new row, so the count restarts by itself and survives a restart.
    Only app.services.llm_gateway writes it, with one conditional upsert.
    """

    __tablename__ = "llm_daily_usage"
    __table_args__ = (CheckConstraint("used >= 0", name="used_not_negative"),)

    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    used: Mapped[int] = mapped_column(Integer)


class LlmTrialUsage(Base):
    """Attempts of one model trial run, TRIAL scope only (round 6 PR B1).

    No date in the key: crossing midnight or restarting never renews the allowance, and
    `cap` is set once when the run is created.
    """

    __tablename__ = "llm_trial_usage"
    __table_args__ = (
        CheckConstraint("cap >= 0", name="cap_not_negative"),
        CheckConstraint("used >= 0 AND used <= cap", name="used_within_cap"),
    )

    trial_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    cap: Mapped[int] = mapped_column(Integer)
    used: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
