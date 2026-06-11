from sqlalchemy import String, Date, Numeric, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date as date_type
from decimal import Decimal

from app.db.base import Base


class PriceMovement(Base):
    __tablename__ = "price_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), ForeignKey("symbols.ticker"))
    date: Mapped[date_type] = mapped_column(Date)
    pct_change: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    direction: Mapped[str] = mapped_column(String(4))  # "up" or "down"
    is_major: Mapped[bool] = mapped_column(Boolean, default=False)
    prev_close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column()

    symbol_rel: Mapped["Symbol"] = relationship(back_populates="price_movements")
    attributions: Mapped[list["MovementEventAttribution"]] = relationship(
        back_populates="movement"
    )

    __table_args__ = (
        Index("ix_price_movements_symbol_date", "symbol", "date", unique=True),
        Index("ix_price_movements_is_major", "is_major"),
    )
