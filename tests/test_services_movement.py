"""Tests for movement detection service."""
import pytest
from datetime import date
from decimal import Decimal

from app.models import PriceBar, PriceMovement
from app.services.movement import detect_major_movements


def test_detect_movements_insufficient_data(db_session, sample_symbol):
    """Test movement detection with insufficient price data."""
    result = detect_major_movements(db_session, "AAPL")
    assert result["movements_detected"] == 0
    assert "error" in result


def test_detect_movements_no_major(db_session, sample_symbol):
    """Test movement detection when no major moves exist."""
    # Add bars with small price changes
    bars = [
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000000,
        ),
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 2),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.50"),  # +0.5%
            volume=1000000,
        ),
    ]
    db_session.add_all(bars)
    db_session.commit()

    result = detect_major_movements(db_session, "AAPL")
    assert result["movements_detected"] == 0

    # Verify movement was still recorded, just not as major
    movement = db_session.query(PriceMovement).filter(PriceMovement.symbol == "AAPL").first()
    assert movement is not None
    assert movement.is_major is False


def test_detect_movements_major_up(db_session, sample_symbol):
    """Test detection of major upward movement."""
    bars = [
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000000,
        ),
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 2),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("100"),
            close=Decimal("105"),  # +5%
            volume=2000000,
        ),
    ]
    db_session.add_all(bars)
    db_session.commit()

    result = detect_major_movements(db_session, "AAPL")
    assert result["movements_detected"] == 1

    movement = (
        db_session.query(PriceMovement)
        .filter(PriceMovement.symbol == "AAPL", PriceMovement.is_major == True)
        .first()
    )
    assert movement is not None
    assert movement.direction == "up"
    assert float(movement.pct_change) == 5.0


def test_detect_movements_major_down(db_session, sample_symbol):
    """Test detection of major downward movement."""
    bars = [
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000000,
        ),
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 2),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("95"),
            close=Decimal("96"),  # -4%
            volume=3000000,
        ),
    ]
    db_session.add_all(bars)
    db_session.commit()

    result = detect_major_movements(db_session, "AAPL")
    assert result["movements_detected"] == 1

    movement = (
        db_session.query(PriceMovement)
        .filter(PriceMovement.symbol == "AAPL", PriceMovement.is_major == True)
        .first()
    )
    assert movement is not None
    assert movement.direction == "down"
    assert float(movement.pct_change) == -4.0


def test_detect_movements_idempotent(db_session, sample_symbol, sample_price_bars):
    """Test that running detection twice doesn't create duplicates."""
    result1 = detect_major_movements(db_session, "AAPL")
    result2 = detect_major_movements(db_session, "AAPL")

    movements = db_session.query(PriceMovement).filter(PriceMovement.symbol == "AAPL").all()
    # Should have exactly 2 movements (for 3 bars)
    assert len(movements) == 2
