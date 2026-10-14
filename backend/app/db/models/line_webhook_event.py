from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class LineWebhookEvent(Base):
    __tablename__ = "line_webhook_event"

    webhook_event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
