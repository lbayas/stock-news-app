from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal

from app.models import PriceBar, PriceMovement
from app.config import get_settings


def detect_major_movements(db: Session, ticker: str) -> dict:
    """
    Detect major price movements for a symbol.
    A major movement is defined as >= MAJOR_MOVE_THRESHOLD % change in one day.
    """
    settings = get_settings()
    threshold = settings.major_move_threshold

    # Get all price bars ordered by date
    bars = (
        db.query(PriceBar)
        .filter(PriceBar.symbol == ticker)
        .order_by(PriceBar.date)
        .all()
    )

    if len(bars) < 2:
        return {"movements_detected": 0, "error": "Insufficient price data"}

    movements_detected = 0
    prev_bar = bars[0]

    for bar in bars[1:]:
        if prev_bar.close and prev_bar.close > 0:
            pct_change = ((bar.close - prev_bar.close) / prev_bar.close) * 100
            pct_change = round(float(pct_change), 4)
            direction = "up" if pct_change > 0 else "down"
            is_major = abs(pct_change) >= threshold

            movement_data = {
                "symbol": ticker,
                "date": bar.date,
                "pct_change": pct_change,
                "direction": direction,
                "is_major": is_major,
                "prev_close": float(prev_bar.close),
                "close": float(bar.close),
                "volume": bar.volume,
            }

            stmt = insert(PriceMovement).values(**movement_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "date"],
                set_={
                    "pct_change": stmt.excluded.pct_change,
                    "direction": stmt.excluded.direction,
                    "is_major": stmt.excluded.is_major,
                    "prev_close": stmt.excluded.prev_close,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(stmt)

            if is_major:
                movements_detected += 1

        prev_bar = bar

    db.commit()
    return {"movements_detected": movements_detected}
