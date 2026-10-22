"""Versioned opt-in dataset marker; reset replays the profile, never credentials."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoDataset(Base):
    __tablename__ = "demo_dataset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile: Mapped[str] = mapped_column(Text, unique=True)
    reference_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
