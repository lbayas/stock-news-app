from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base import Base


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    source: Mapped[str | None] = mapped_column(String(100))  # Publisher name (Reuters, CNBC)
    provider: Mapped[str | None] = mapped_column(String(50))  # API provider (newsapi, gnews, polygon)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    symbol_scores: Mapped[list["EventSymbolScore"]] = relationship(
        back_populates="event"
    )

    __table_args__ = (Index("ix_news_events_published_at", "published_at"),)
