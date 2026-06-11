from sqlalchemy import String, Date, Numeric, BigInteger, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date as date_type
from decimal import Decimal

from app.db.base import Base


class PriceBar(Base):
    __tablename__ = "price_bars"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), ForeignKey("symbols.ticker"))
    date: Mapped[date_type] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int] = mapped_column(BigInteger)

    symbol_rel: Mapped["Symbol"] = relationship(back_populates="price_bars")

    __table_args__ = (
        Index("ix_price_bars_symbol_date", "symbol", "date", unique=True),
    )
