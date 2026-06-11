"""Tests for symbols endpoints."""
import pytest
from unittest.mock import patch


def test_list_symbols_empty(client):
    """Test listing symbols when none exist."""
    response = client.get("/api/v1/symbols")
    assert response.status_code == 200
    data = response.json()
    assert data["symbols"] == []


def test_list_symbols(client, sample_symbol):
    """Test listing symbols returns active symbols."""
    response = client.get("/api/v1/symbols")
    assert response.status_code == 200
    data = response.json()
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["ticker"] == "AAPL"
    assert data["symbols"][0]["is_active"] is True


def test_list_symbols_excludes_inactive(client, db_session):
    """Test that inactive symbols are excluded."""
    from app.models import Symbol

    active = Symbol(ticker="AAPL", is_active=True)
    inactive = Symbol(ticker="META", is_active=False)
    db_session.add_all([active, inactive])
    db_session.commit()

    response = client.get("/api/v1/symbols")
    assert response.status_code == 200
    data = response.json()
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["ticker"] == "AAPL"


def test_refresh_symbol_creates_new(client, db_session, mocker):
    """Test refreshing a new symbol auto-creates it."""
    from app.models import Job
    from datetime import datetime

    # Create a pending job
    job = Job(
        id="test-new-symbol-job",
        job_type="refresh",
        symbol="FAKE",
        status="pending",
        progress={"step": "queued", "message": "Waiting"},
        created_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    # Mock start_refresh_job to return our job
    mocker.patch("app.api.symbols.start_refresh_job", return_value=job)

    response = client.post("/api/v1/symbols/FAKE/refresh")
    assert response.status_code == 200

    data = response.json()
    assert data["symbol_created"] is True
    assert data["job_id"] == "test-new-symbol-job"


def test_refresh_symbol_returns_job(client, sample_symbol, db_session, mocker):
    """Test that refresh returns job_id immediately."""
    from app.models import Job
    from datetime import datetime

    # Create a pending job
    job = Job(
        id="test-refresh-job",
        job_type="refresh",
        symbol="AAPL",
        status="pending",
        progress={"step": "queued", "message": "Waiting"},
        created_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    # Mock start_refresh_job to return our job
    mock_start = mocker.patch(
        "app.api.symbols.start_refresh_job",
        return_value=job,
    )

    response = client.post("/api/v1/symbols/aapl/refresh")
    assert response.status_code == 200

    data = response.json()
    assert data["job_id"] == "test-refresh-job"
    assert data["status"] == "pending"
    assert "Poll" in data["message"]

    # Verify the ticker was uppercased
    mock_start.assert_called_once()
    call_args = mock_start.call_args
    assert call_args[0][1] == "AAPL"


def test_sync_symbols_success(client, db_session):
    """Test syncing symbols from MASSIVE API."""
    mock_result = {
        "symbols": ["NVDA", "AAPL", "MSFT"],
        "date": "2026-06-10",
    }
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result):
        response = client.post("/api/v1/symbols/sync?limit=3")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert set(data["added"]) == {"NVDA", "AAPL", "MSFT"}
    assert data["existing"] == []
    assert data["source_date"] == "2026-06-10"


def test_sync_symbols_with_existing(client, sample_symbol, db_session):
    """Test sync skips existing symbols."""
    mock_result = {
        "symbols": ["AAPL", "NVDA"],
        "date": "2026-06-10",
    }
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result):
        response = client.post("/api/v1/symbols/sync")

    assert response.status_code == 200
    data = response.json()
    assert "AAPL" in data["existing"]
    assert "NVDA" in data["added"]


def test_sync_symbols_api_error(client):
    """Test sync returns 500 on API error."""
    mock_result = {"error": "API rate limit exceeded"}
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result):
        response = client.post("/api/v1/symbols/sync")

    assert response.status_code == 500
    assert "rate limit" in response.json()["detail"]


def test_sync_symbols_equities_filter(client, db_session):
    """Test sync with equities filter."""
    mock_result = {"symbols": ["AAPL", "NVDA"], "date": "2026-06-10"}
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result) as mock_fetch:
        response = client.post("/api/v1/symbols/sync?asset_type=equities")

    assert response.status_code == 200
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["asset_type"] == "equities"


def test_sync_symbols_etfs_filter(client, db_session):
    """Test sync with ETFs filter."""
    mock_result = {"symbols": ["SPY", "QQQ"], "date": "2026-06-10"}
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result) as mock_fetch:
        response = client.post("/api/v1/symbols/sync?asset_type=etfs")

    assert response.status_code == 200
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["asset_type"] == "etfs"


def test_sync_symbols_min_price(client, db_session):
    """Test sync with custom min_price."""
    mock_result = {"symbols": ["BRK.A"], "date": "2026-06-10"}
    with patch("app.api.symbols.fetch_popular_symbols", return_value=mock_result) as mock_fetch:
        response = client.post("/api/v1/symbols/sync?min_price=100.0")

    assert response.status_code == 200
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["min_price"] == 100.0
