from sqlalchemy import String, Integer, Numeric, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal

from app.db.base import Base


class MovementEventAttribution(Base):
    __tablename__ = "movement_event_attributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("price_movements.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("news_events.id"))
    symbol: Mapped[str] = mapped_column(String(10), ForeignKey("symbols.ticker"))
    impact_rank: Mapped[int] = mapped_column(Integer)
    temporal_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    attribution_label: Mapped[str | None] = mapped_column(
        String(50)
    )  # primary/supporting/indirect

    movement: Mapped["PriceMovement"] = relationship(back_populates="attributions")
    event: Mapped["NewsEvent"] = relationship()

    __table_args__ = (
        Index(
            "ix_movement_event_attributions_movement_event",
            "movement_id",
            "event_id",
            unique=True,
        ),
        Index("ix_movement_event_attributions_movement", "movement_id"),
    )
