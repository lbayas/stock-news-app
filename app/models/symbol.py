from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base import Base


class Symbol(Base):
    __tablename__ = "symbols"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    company_profile: Mapped["CompanyProfile"] = relationship(
        back_populates="symbol_rel", uselist=False
    )
    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="symbol_rel")
    price_movements: Mapped[list["PriceMovement"]] = relationship(
        back_populates="symbol_rel"
    )
    event_scores: Mapped[list["EventSymbolScore"]] = relationship(
        back_populates="symbol_rel"
    )
