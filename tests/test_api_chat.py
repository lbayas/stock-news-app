"""Tests for chat endpoint."""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime, date, timedelta
from decimal import Decimal


def test_chat_symbol_not_found(client):
    """Test chat for non-existent symbol returns 404."""
    response = client.post(
        "/api/v1/chat",
        json={"ticker": "FAKE", "message": "Why did it drop?"},
    )
    assert response.status_code == 404


def test_chat_validation_missing_fields(client, sample_symbol):
    """Test missing required fields return 422."""
    assert client.post("/api/v1/chat", json={"message": "Why?"}).status_code == 422
    assert client.post("/api/v1/chat", json={"ticker": "AAPL"}).status_code == 422


def test_chat_no_data(client, sample_symbol):
    """Test chat response when no movement data exists."""
    response = client.post(
        "/api/v1/chat",
        json={"ticker": "AAPL", "message": "Why did the stock drop?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "don't have data" in data["response"].lower() or "refresh" in data["response"].lower()


def test_chat_with_movements(client, sample_symbol, sample_company_profile, sample_movement):
    """Test chat response includes movement information."""
    response = client.post(
        "/api/v1/chat",
        json={
            "ticker": "AAPL",
            "message": "What happened recently?",
            "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "Apple Inc." in data["response"]
    assert "+3.87%" in data["response"] or "3.87" in data["response"]


def test_chat_with_filters(client, sample_symbol, sample_movement):
    """Test chat respects date filters."""
    response = client.post(
        "/api/v1/chat",
        json={
            "ticker": "AAPL",
            "message": "What happened?",
            "filters": {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Movement from Jan 2 should be included
    assert "3.87" in data["response"] or "up" in data["response"].lower()


def test_chat_case_insensitive_ticker(client, sample_symbol, sample_movement):
    """Test that ticker is normalized to uppercase."""
    response = client.post(
        "/api/v1/chat",
        json={"ticker": "aapl", "message": "What happened?"},
    )
    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"


def test_chat_with_attributions(client, db_session):
    """Test chat includes sources from attributions."""
    from app.models import (
        Symbol, CompanyProfile, PriceMovement, NewsEvent,
        EventSymbolScore, MovementEventAttribution,
    )

    # Create test data with attributions
    symbol = Symbol(ticker="TEST", is_active=True)
    profile = CompanyProfile(symbol="TEST", name="Test Corp")
    movement = PriceMovement(
        symbol="TEST",
        date=datetime(2024, 1, 15).date(),
        pct_change=Decimal("5.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100.0"),
        close=Decimal("105.0"),
    )
    event = NewsEvent(
        title="Test Corp earnings beat expectations",
        source="TestNews",
        url="https://example.com/news/earnings",
        published_at=datetime(2024, 1, 15, 9, 0),
    )
    db_session.add_all([symbol, profile, movement, event])
    db_session.commit()

    score = EventSymbolScore(
        event_id=event.id,
        symbol="TEST",
        correlation_score=Decimal("0.85"),
        correlation_tier="high",
        rationale="Direct earnings news",
    )
    db_session.add(score)
    db_session.commit()

    attribution = MovementEventAttribution(
        movement_id=movement.id,
        event_id=event.id,
        symbol="TEST",
        attribution_label="primary",
        impact_rank=1,
        temporal_score=Decimal("1.0"),
    )
    db_session.add(attribution)
    db_session.commit()

    response = client.post(
        "/api/v1/chat",
        json={
            "ticker": "TEST",
            "message": "Why did the stock go up?",
            "filters": {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "TEST"
    assert len(data["sources"]) > 0
    source = data["sources"][0]
    assert source["title"] == "Test Corp earnings beat expectations"
    assert source["source"] == "TestNews"
    assert source["correlation_score"] == 0.85
    assert source["correlation_tier"] == "high"


def test_chat_llm_response(client, sample_symbol, sample_company_profile, sample_movement):
    """Test chat uses LLM when API key is configured."""
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="The stock moved due to market conditions."))]

    with patch("app.services.chat.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        with patch("app.services.chat.OpenAI") as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            response = client.post(
                "/api/v1/chat",
                json={
                    "ticker": "AAPL",
                    "message": "What happened?",
                    "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert "market conditions" in data["response"]


def test_chat_llm_response_full_schema(
    client,
    sample_symbol,
    sample_company_profile,
    sample_movement,
    sample_news_event,
    sample_event_score,
    sample_attribution,
):
    """Test LLM path returns full response schema including message and sources."""
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="The stock moved due to market conditions."))]

    with patch("app.services.chat.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        with patch("app.services.chat.OpenAI") as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            response = client.post(
                "/api/v1/chat",
                json={
                    "ticker": "AAPL",
                    "message": "What happened?",
                    "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["message"] == "What happened?"
    assert "market conditions" in data["response"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["title"] == "Apple announces record iPhone sales"
    assert data["sources"][0]["correlation_score"] == 0.92
    assert data["sources"][0]["correlation_tier"] == "high"


def test_chat_default_date_range(client, sample_symbol, db_session):
    """Test default date range is last 365 days when filters omitted."""
    from app.models import PriceMovement

    today = date(2024, 6, 15)
    recent = PriceMovement(
        symbol="AAPL",
        date=today - timedelta(days=30),
        pct_change=Decimal("5.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("105"),
    )
    old = PriceMovement(
        symbol="AAPL",
        date=today - timedelta(days=400),
        pct_change=Decimal("7.0"),
        direction="up",
        is_major=True,
        prev_close=Decimal("100"),
        close=Decimal("107"),
    )
    db_session.add_all([recent, old])
    db_session.commit()

    with patch("app.services.chat.get_settings") as mock_settings, patch(
        "app.services.chat.date"
    ) as mock_date:
        mock_settings.return_value.openai_api_key = ""
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        response = client.post(
            "/api/v1/chat",
            json={"ticker": "AAPL", "message": "What happened?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "5.0" in data["response"] or "+5.00%" in data["response"]
    assert "7.0" not in data["response"]


def test_chat_llm_error_fallback(client, sample_symbol, sample_company_profile, sample_movement):
    """Test chat falls back to structured response on LLM error."""
    with patch("app.services.chat.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        with patch("app.services.chat.OpenAI") as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            response = client.post(
                "/api/v1/chat",
                json={
                    "ticker": "AAPL",
                    "message": "What happened?",
                    "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
                },
            )

    assert response.status_code == 200
    data = response.json()
    # Should contain error message and fallback structured response
    assert "Error generating response" in data["response"]
    assert "Apple Inc." in data["response"]


def test_chat_structured_response_no_api_key(client, sample_symbol, sample_company_profile, sample_movement):
    """Test chat uses structured response when no API key."""
    with patch("app.services.chat.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = ""

        response = client.post(
            "/api/v1/chat",
            json={
                "ticker": "AAPL",
                "message": "What happened?",
                "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    # Structured response format
    assert "Here's what I found" in data["response"]
    assert "+3.87%" in data["response"]


def test_chat_structured_response_no_events(client, sample_symbol, sample_company_profile, sample_movement):
    """Test structured response shows note when no events are attributed."""
    with patch("app.services.chat.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = ""

        response = client.post(
            "/api/v1/chat",
            json={
                "ticker": "AAPL",
                "message": "What caused this?",
                "filters": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    # Should mention no news attributions
    assert "No news attributions" in data["response"] or "refresh" in data["response"].lower()
