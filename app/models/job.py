"""
Job model for tracking async refresh operations.
"""
from sqlalchemy import String, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    job_type: Mapped[str] = mapped_column(String(50))  # "refresh", "score", etc.
    symbol: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))  # pending, processing, completed, failed
    progress: Mapped[dict | None] = mapped_column(JSON)  # {"step": "scoring", "current": 50, "total": 100}
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
