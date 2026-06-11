from sqlalchemy import String, Numeric, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from decimal import Decimal

from app.db.base import Base


class EventSymbolScore(Base):
    __tablename__ = "event_symbol_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("news_events.id"))
    symbol: Mapped[str] = mapped_column(String(10), ForeignKey("symbols.ticker"))
    correlation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    correlation_tier: Mapped[str] = mapped_column(String(10))  # high/medium/low
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped["NewsEvent"] = relationship(back_populates="symbol_scores")
    symbol_rel: Mapped["Symbol"] = relationship(back_populates="event_scores")

    __table_args__ = (
        Index("ix_event_symbol_scores_event_symbol", "event_id", "symbol", unique=True),
        Index("ix_event_symbol_scores_symbol", "symbol"),
    )
