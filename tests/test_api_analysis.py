"""Tests for analysis endpoint."""
import pytest
from datetime import date


def test_analysis_symbol_not_found(client):
    """Test analysis for non-existent symbol returns 404."""
    response = client.get("/api/v1/tickers/FAKE/analysis")
    assert response.status_code == 404


def test_analysis_empty_data(client, sample_symbol):
    """Test analysis with no price data returns empty movements."""
    response = client.get("/api/v1/tickers/AAPL/analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["major_movements"] == []


def test_analysis_with_company_profile(client, sample_symbol, sample_company_profile):
    """Test analysis includes company info when profile exists."""
    response = client.get("/api/v1/tickers/AAPL/analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["name"] == "Apple Inc."
    assert data["company"]["sector"] == "Technology"


def test_analysis_with_movements(client, sample_symbol, sample_movement):
    """Test analysis returns major movements."""
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["major_movements"]) == 1
    assert data["major_movements"][0]["pct_change"] == 3.87
    assert data["major_movements"][0]["direction"] == "up"


def test_analysis_direction_filter(client, sample_symbol, db_session):
    """Test filtering movements by direction."""
    from app.models import PriceMovement
    from decimal import Decimal

    # Add both up and down movements
    up_move = PriceMovement(
        symbol="AAPL",
        date=date(2024, 1, 2),
        pct_change=Decimal("3.5"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("103.5"),
    )
    down_move = PriceMovement(
        symbol="AAPL",
        date=date(2024, 1, 3),
        pct_change=Decimal("-4.0"),
        direction="down",
        is_major=True,
        prev_close=Decimal("103.5"),
        close=Decimal("99.36"),
    )
    db_session.add_all([up_move, down_move])
    db_session.commit()

    # Filter for "up" only
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"start_date": "2024-01-01", "end_date": "2024-12-31", "direction": "up"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["major_movements"]) == 1
    assert data["major_movements"][0]["direction"] == "up"


def test_analysis_invalid_direction(client, sample_symbol):
    """Test invalid direction returns 400."""
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"direction": "sideways"},
    )
    assert response.status_code == 400


def test_analysis_invalid_correlation_tier(client, sample_symbol):
    """Test invalid correlation tier returns 400."""
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"correlation_tier": "super"},
    )
    assert response.status_code == 400


def test_analysis_with_price_summary(client, sample_symbol, sample_price_bars):
    """Test analysis includes price summary when requested."""
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "include_prices": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["price_summary"] is not None
    assert data["price_summary"]["start_close"] == 181.0
    assert data["price_summary"]["end_close"] == 188.5


def test_analysis_with_explanations(
    client,
    sample_symbol,
    sample_movement,
    sample_news_event,
    sample_event_score,
    sample_attribution,
):
    """Test analysis includes event explanations for movements."""
    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["major_movements"]) == 1

    explanations = data["major_movements"][0]["explanations"]
    assert len(explanations["primary"]) == 1
    assert explanations["primary"][0]["title"] == "Apple announces record iPhone sales"
    assert explanations["primary"][0]["correlation_tier"] == "high"
