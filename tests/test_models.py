"""Tests for database models."""
import pytest
from datetime import date, datetime
from decimal import Decimal

from app.models import (
    Symbol,
    CompanyProfile,
    PriceBar,
    PriceMovement,
    NewsEvent,
    EventSymbolScore,
    MovementEventAttribution,
)


def test_symbol_creation(db_session):
    """Test creating a symbol."""
    symbol = Symbol(ticker="NVDA", is_active=True)
    db_session.add(symbol)
    db_session.commit()

    retrieved = db_session.query(Symbol).filter(Symbol.ticker == "NVDA").first()
    assert retrieved is not None
    assert retrieved.ticker == "NVDA"
    assert retrieved.is_active is True
    assert retrieved.created_at is not None


def test_company_profile_relationship(db_session, sample_symbol, sample_company_profile):
    """Test symbol-profile relationship."""
    symbol = db_session.query(Symbol).filter(Symbol.ticker == "AAPL").first()
    assert symbol.company_profile is not None
    assert symbol.company_profile.name == "Apple Inc."


def test_price_bar_unique_constraint(db_session, sample_symbol):
    """Test that duplicate (symbol, date) raises error."""
    bar1 = PriceBar(
        symbol="AAPL",
        date=date(2024, 1, 1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=1000000,
    )
    db_session.add(bar1)
    db_session.commit()

    bar2 = PriceBar(
        symbol="AAPL",
        date=date(2024, 1, 1),  # Same date
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("98"),
        close=Decimal("101"),
        volume=1100000,
    )
    db_session.add(bar2)
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_event_symbol_score_relationship(
    db_session, sample_symbol, sample_news_event, sample_event_score
):
    """Test event-score relationship."""
    event = db_session.query(NewsEvent).first()
    assert len(event.symbol_scores) == 1
    assert event.symbol_scores[0].symbol == "AAPL"
    assert float(event.symbol_scores[0].correlation_score) == 0.92


def test_event_symbol_score_unique(db_session, sample_symbol, sample_news_event):
    """Test that duplicate (event_id, symbol) raises error."""
    score1 = EventSymbolScore(
        event_id=sample_news_event.id,
        symbol="AAPL",
        correlation_score=Decimal("0.5"),
        correlation_tier="medium",
    )
    db_session.add(score1)
    db_session.commit()

    score2 = EventSymbolScore(
        event_id=sample_news_event.id,
        symbol="AAPL",  # Same symbol
        correlation_score=Decimal("0.8"),
        correlation_tier="high",
    )
    db_session.add(score2)
    with pytest.raises(Exception):
        db_session.commit()


def test_movement_attributions_relationship(
    db_session, sample_movement, sample_news_event, sample_attribution
):
    """Test movement-attribution relationship."""
    movement = db_session.query(PriceMovement).first()
    assert len(movement.attributions) == 1
    assert movement.attributions[0].attribution_label == "primary"
    assert movement.attributions[0].event.title == "Apple announces record iPhone sales"


def test_correlation_tier_values(db_session, sample_symbol, sample_news_event):
    """Test correlation tier mapping."""
    scores = [
        EventSymbolScore(
            event_id=sample_news_event.id,
            symbol="AAPL",
            correlation_score=Decimal("0.92"),
            correlation_tier="high",
        ),
    ]
    db_session.add_all(scores)
    db_session.commit()

    score = db_session.query(EventSymbolScore).first()
    # Verify tier matches expected range
    assert score.correlation_tier == "high"
    assert float(score.correlation_score) >= 0.70
