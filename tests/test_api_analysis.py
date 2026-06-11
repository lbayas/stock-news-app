"""Tests for analysis endpoint."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch


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


def test_analysis_default_date_range(client, sample_symbol, db_session):
    """Test default date range is last 7 days when params omitted."""
    from app.models import PriceMovement

    today = date(2024, 6, 15)
    recent = PriceMovement(
        symbol="AAPL",
        date=today - timedelta(days=3),
        pct_change=Decimal("3.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("103"),
    )
    old = PriceMovement(
        symbol="AAPL",
        date=today - timedelta(days=10),
        pct_change=Decimal("4.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("104"),
    )
    db_session.add_all([recent, old])
    db_session.commit()

    with patch("app.api.analysis.date") as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        response = client.get("/api/v1/tickers/AAPL/analysis")

    assert response.status_code == 200
    data = response.json()
    assert data["filters_applied"]["start_date"] == str(today - timedelta(days=7))
    assert data["filters_applied"]["end_date"] == str(today)
    assert len(data["major_movements"]) == 1
    assert data["major_movements"][0]["pct_change"] == 3.0


def test_analysis_min_move_pct_filter(client, sample_symbol, db_session):
    """Test min_move_pct excludes movements below threshold."""
    from app.models import PriceMovement

    small_move = PriceMovement(
        symbol="AAPL",
        date=date(2024, 1, 2),
        pct_change=Decimal("2.5"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("102.5"),
    )
    big_move = PriceMovement(
        symbol="AAPL",
        date=date(2024, 1, 3),
        pct_change=Decimal("6.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("102.5"),
        close=Decimal("108.65"),
    )
    db_session.add_all([small_move, big_move])
    db_session.commit()

    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "min_move_pct": 5.0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["major_movements"]) == 1
    assert data["major_movements"][0]["pct_change"] == 6.0


def test_analysis_min_correlation_score_filter(
    client, sample_symbol, sample_movement, db_session
):
    """Test min_correlation_score filters event explanations."""
    from app.models import NewsEvent, EventSymbolScore, MovementEventAttribution
    from datetime import datetime

    high_event = NewsEvent(
        title="High correlation news",
        url="https://example.com/high",
        source="Reuters",
        published_at=datetime(2024, 1, 2, 9, 0),
    )
    low_event = NewsEvent(
        title="Low correlation news",
        url="https://example.com/low",
        source="Bloomberg",
        published_at=datetime(2024, 1, 2, 10, 0),
    )
    db_session.add_all([high_event, low_event])
    db_session.commit()

    db_session.add_all([
        EventSymbolScore(
            event_id=high_event.id,
            symbol="AAPL",
            correlation_score=Decimal("0.90"),
            correlation_tier="high",
            rationale="Direct news",
        ),
        EventSymbolScore(
            event_id=low_event.id,
            symbol="AAPL",
            correlation_score=Decimal("0.40"),
            correlation_tier="low",
            rationale="Weak link",
        ),
        MovementEventAttribution(
            movement_id=sample_movement.id,
            event_id=high_event.id,
            symbol="AAPL",
            impact_rank=1,
            temporal_score=Decimal("0.95"),
            attribution_label="primary",
        ),
        MovementEventAttribution(
            movement_id=sample_movement.id,
            event_id=low_event.id,
            symbol="AAPL",
            impact_rank=2,
            temporal_score=Decimal("0.50"),
            attribution_label="indirect",
        ),
    ])
    db_session.commit()

    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "min_correlation_score": 0.8,
        },
    )

    assert response.status_code == 200
    explanations = response.json()["major_movements"][0]["explanations"]
    titles = [e["title"] for e in explanations["primary"] + explanations["indirect"]]
    assert titles == ["High correlation news"]


def test_analysis_correlation_tier_filter(
    client, sample_symbol, sample_movement, db_session
):
    """Test correlation_tier filters event explanations."""
    from app.models import NewsEvent, EventSymbolScore, MovementEventAttribution
    from datetime import datetime

    high_event = NewsEvent(
        title="High tier news",
        url="https://example.com/high-tier",
        source="Reuters",
        published_at=datetime(2024, 1, 2, 9, 0),
    )
    medium_event = NewsEvent(
        title="Medium tier news",
        url="https://example.com/medium-tier",
        source="CNBC",
        published_at=datetime(2024, 1, 2, 11, 0),
    )
    db_session.add_all([high_event, medium_event])
    db_session.commit()

    db_session.add_all([
        EventSymbolScore(
            event_id=high_event.id,
            symbol="AAPL",
            correlation_score=Decimal("0.90"),
            correlation_tier="high",
            rationale="Direct news",
        ),
        EventSymbolScore(
            event_id=medium_event.id,
            symbol="AAPL",
            correlation_score=Decimal("0.55"),
            correlation_tier="medium",
            rationale="Sector news",
        ),
        MovementEventAttribution(
            movement_id=sample_movement.id,
            event_id=high_event.id,
            symbol="AAPL",
            impact_rank=1,
            temporal_score=Decimal("0.95"),
            attribution_label="primary",
        ),
        MovementEventAttribution(
            movement_id=sample_movement.id,
            event_id=medium_event.id,
            symbol="AAPL",
            impact_rank=2,
            temporal_score=Decimal("0.70"),
            attribution_label="supporting",
        ),
    ])
    db_session.commit()

    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "correlation_tier": "medium",
        },
    )

    assert response.status_code == 200
    explanations = response.json()["major_movements"][0]["explanations"]
    assert len(explanations["primary"]) == 0
    assert len(explanations["supporting"]) == 1
    assert explanations["supporting"][0]["title"] == "Medium tier news"


def test_analysis_supporting_indirect_explanations(
    client, sample_symbol, sample_movement, db_session
):
    """Test explanations are grouped into primary, supporting, and indirect."""
    from app.models import NewsEvent, EventSymbolScore, MovementEventAttribution
    from datetime import datetime

    tiers = [
        ("Primary news", "primary", Decimal("0.92"), "high"),
        ("Supporting news", "supporting", Decimal("0.55"), "medium"),
        ("Indirect news", "indirect", Decimal("0.20"), "low"),
    ]
    for i, (title, label, score_val, tier) in enumerate(tiers, start=1):
        event = NewsEvent(
            title=title,
            url=f"https://example.com/{label}",
            source="TestNews",
            published_at=datetime(2024, 1, 2, 8 + i, 0),
        )
        db_session.add(event)
        db_session.commit()
        db_session.add_all([
            EventSymbolScore(
                event_id=event.id,
                symbol="AAPL",
                correlation_score=score_val,
                correlation_tier=tier,
                rationale=f"{label} rationale",
            ),
            MovementEventAttribution(
                movement_id=sample_movement.id,
                event_id=event.id,
                symbol="AAPL",
                impact_rank=i,
                temporal_score=Decimal("0.80"),
                attribution_label=label,
            ),
        ])
        db_session.commit()

    response = client.get(
        "/api/v1/tickers/AAPL/analysis",
        params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    )

    assert response.status_code == 200
    explanations = response.json()["major_movements"][0]["explanations"]
    assert [e["title"] for e in explanations["primary"]] == ["Primary news"]
    assert [e["title"] for e in explanations["supporting"]] == ["Supporting news"]
    assert [e["title"] for e in explanations["indirect"]] == ["Indirect news"]
