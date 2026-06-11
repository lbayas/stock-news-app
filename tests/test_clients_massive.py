"""Tests for MASSIVE (Polygon) news client."""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
from decimal import Decimal

from app.clients.massive_client import fetch_news_for_movements_massive
from app.models import Symbol, PriceMovement


class TestFetchNewsForMovements:
    """Tests for fetching news around movement dates."""

    def test_no_api_key(self, db_session):
        """Test returns error when API key not configured."""
        with patch("app.clients.massive_client.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = ""
            result = fetch_news_for_movements_massive(db_session, "AAPL")
            assert result["events_fetched"] == 0
            assert "not configured" in result["error"]

    def test_no_movements(self, db_session):
        """Test returns error when no major movements exist."""
        with patch("app.clients.massive_client.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            result = fetch_news_for_movements_massive(db_session, "UNKNOWN")
            assert result["events_fetched"] == 0
            assert "no major movements" in result["error"].lower()

    def test_success(self, db_session):
        """Test successful news fetch for movements."""
        # Create a movement
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, movement])
        db_session.commit()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "id": "news123",
                    "title": "Test Corp announces earnings",
                    "article_url": "https://example.com/news/1",
                    "published_utc": datetime.utcnow().isoformat(),
                    "description": "Test Corp reported strong earnings.",
                    "publisher": {"name": "TestNews"},
                    "tickers": ["TEST"],
                },
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.massive_client.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.massive_client.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_news_for_movements_massive(db_session, "TEST")

        assert result["events_fetched"] >= 1
        assert "errors" not in result or len(result.get("errors", [])) == 0

    def test_api_error(self, db_session):
        """Test handles API errors gracefully."""
        import httpx

        # Create a movement
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, movement])
        db_session.commit()

        with patch("app.clients.massive_client.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.massive_client.httpx.Client") as mock_client:
                mock_http_client = Mock()
                mock_response = Mock()
                mock_response.status_code = 500
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Server error", request=Mock(), response=mock_response
                )
                mock_http_client.get.return_value = mock_response
                mock_client.return_value.__enter__ = Mock(return_value=mock_http_client)
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_news_for_movements_massive(db_session, "TEST")

        # Should have errors but not crash
        assert "errors" in result or result["events_fetched"] == 0

    def test_empty_results(self, db_session):
        """Test handles empty API results."""
        # Create a movement
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, movement])
        db_session.commit()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "OK", "results": []}
        mock_response.raise_for_status = Mock()

        with patch("app.clients.massive_client.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.massive_client.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_news_for_movements_massive(db_session, "TEST")

        assert result["events_fetched"] == 0
