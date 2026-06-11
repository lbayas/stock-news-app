"""Tests for Polygon.io client."""
import pytest
from unittest.mock import patch, Mock
from datetime import date, datetime
from decimal import Decimal

from app.clients.polygon_prices import (
    fetch_price_history_polygon,
    fetch_company_profile_polygon,
    fetch_popular_symbols,
    _is_etf,
)


class TestIsEtf:
    """Tests for ETF detection."""

    def test_known_etfs(self):
        """Test known ETF tickers are detected."""
        assert _is_etf("SPY") is True
        assert _is_etf("QQQ") is True
        assert _is_etf("ARKK") is True
        assert _is_etf("IBIT") is True

    def test_etf_prefixes(self):
        """Test ETF prefix patterns."""
        assert _is_etf("XLF") is True
        assert _is_etf("XLE") is True
        assert _is_etf("VTI") is True

    def test_equities(self):
        """Test equities are not flagged as ETFs."""
        assert _is_etf("AAPL") is False
        assert _is_etf("NVDA") is False
        assert _is_etf("META") is False


class TestFetchPopularSymbols:
    """Tests for fetching popular symbols."""

    def test_no_api_key(self):
        """Test returns error when API key not configured."""
        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = ""
            result = fetch_popular_symbols()
            assert result["symbols"] == []
            assert "not configured" in result["error"]

    def test_success(self):
        """Test successful fetch of popular symbols."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {"T": "NVDA", "c": 150.0, "v": 100000000},
                {"T": "AAPL", "c": 180.0, "v": 80000000},
                {"T": "SPY", "c": 500.0, "v": 50000000},
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_popular_symbols(limit=3)

        assert len(result["symbols"]) == 3
        assert "NVDA" in result["symbols"]

    def test_equities_filter(self):
        """Test filtering to equities only."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {"T": "NVDA", "c": 150.0, "v": 100000000},
                {"T": "SPY", "c": 500.0, "v": 90000000},
                {"T": "AAPL", "c": 180.0, "v": 80000000},
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_popular_symbols(asset_type="equities")

        assert "SPY" not in result["symbols"]
        assert "NVDA" in result["symbols"]

    def test_etfs_filter(self):
        """Test filtering to ETFs only."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {"T": "NVDA", "c": 150.0, "v": 100000000},
                {"T": "SPY", "c": 500.0, "v": 90000000},
                {"T": "QQQ", "c": 400.0, "v": 80000000},
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_popular_symbols(asset_type="etfs")

        assert "NVDA" not in result["symbols"]
        assert "SPY" in result["symbols"]
        assert "QQQ" in result["symbols"]

    def test_min_price_filter(self):
        """Test filtering by minimum price."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {"T": "NVDA", "c": 150.0, "v": 100000000},
                {"T": "PENNY", "c": 5.0, "v": 90000000},
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_popular_symbols(min_price=20.0)

        assert "NVDA" in result["symbols"]
        assert "PENNY" not in result["symbols"]

    def test_api_error(self):
        """Test handles API errors gracefully."""
        import httpx

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_http_client = Mock()
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Rate limit", request=Mock(), response=mock_response
                )
                mock_http_client.get.return_value = mock_response
                mock_client.return_value.__enter__ = Mock(return_value=mock_http_client)
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_popular_symbols()

        assert result["symbols"] == []
        assert "429" in result["error"]


class TestFetchPriceHistory:
    """Tests for fetching price history."""

    def test_no_api_key(self, db_session):
        """Test returns error when API key not configured."""
        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = ""
            result = fetch_price_history_polygon(db_session, "AAPL")
            assert result["bars_added"] == 0
            assert "not configured" in result["error"]

    def test_success(self, db_session):
        """Test successful price history fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "resultsCount": 2,
            "results": [
                {"t": 1704153600000, "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 1000000},
                {"t": 1704240000000, "o": 104.0, "h": 108.0, "l": 103.0, "c": 107.0, "v": 1200000},
            ],
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            mock_settings.return_value.default_lookback_days = 365
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_price_history_polygon(db_session, "TEST")

        assert result["bars_added"] == 2


class TestFetchCompanyProfile:
    """Tests for fetching company profile."""

    def test_no_api_key(self, db_session):
        """Test returns error when API key not configured."""
        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = ""
            result = fetch_company_profile_polygon(db_session, "AAPL")
            assert result["updated"] is False
            assert "not configured" in result["error"]

    def test_success(self, db_session):
        """Test successful company profile fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": {
                "ticker": "TEST",
                "name": "Test Corporation",
                "sic_description": "Technology",
                "description": "A test company",
                "market_cap": 1000000000,
                "total_employees": 5000,
                "homepage_url": "https://test.com",
                "locale": "us",
            },
        }
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_company_profile_polygon(db_session, "TEST")

        assert result["updated"] is True
        assert result["name"] == "Test Corporation"

    def test_no_data(self, db_session):
        """Test handles missing ticker data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "OK", "results": {}}
        mock_response.raise_for_status = Mock()

        with patch("app.clients.polygon_prices.get_settings") as mock_settings:
            mock_settings.return_value.massive_api_key = "test-key"
            with patch("app.clients.polygon_prices.httpx.Client") as mock_client:
                mock_client.return_value.__enter__ = Mock(return_value=Mock(get=Mock(return_value=mock_response)))
                mock_client.return_value.__exit__ = Mock(return_value=False)

                result = fetch_company_profile_polygon(db_session, "FAKE")

        assert result["updated"] is False
        assert "no ticker data" in result["error"].lower()
