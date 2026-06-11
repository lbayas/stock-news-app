"""Tests for async refresh service."""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import threading
import time

from app.services.async_refresh import (
    create_refresh_job,
    run_refresh_async,
    start_refresh_job,
    get_job_status,
    _update_progress,
)
from app.models import Job, Symbol, CompanyProfile


class TestCreateRefreshJob:
    """Tests for job creation."""

    def test_creates_job(self, db_session):
        """Test creates a new job with correct attributes."""
        job = create_refresh_job(db_session, "TEST")

        assert job.id is not None
        assert len(job.id) == 36  # UUID format
        assert job.job_type == "refresh"
        assert job.symbol == "TEST"
        assert job.status == "pending"
        assert job.progress["step"] == "queued"
        assert job.created_at is not None

    def test_job_persisted(self, db_session):
        """Test job is persisted to database."""
        job = create_refresh_job(db_session, "TEST")
        job_id = job.id

        # Query fresh from DB
        saved_job = db_session.query(Job).filter_by(id=job_id).first()
        assert saved_job is not None
        assert saved_job.symbol == "TEST"


class TestUpdateProgress:
    """Tests for progress updates."""

    def test_updates_progress(self, db_session):
        """Test progress is updated correctly."""
        job = create_refresh_job(db_session, "TEST")

        _update_progress(db_session, job, "prices", "Fetching prices...")

        assert job.progress["step"] == "prices"
        assert job.progress["message"] == "Fetching prices..."


class TestGetJobStatus:
    """Tests for job status retrieval."""

    def test_job_not_found(self, db_session):
        """Test returns None for non-existent job."""
        result = get_job_status(db_session, "non-existent")
        assert result is None

    def test_pending_job_status(self, db_session):
        """Test status for pending job."""
        job = Job(
            id="status-test-1",
            job_type="refresh",
            symbol="TEST",
            status="pending",
            progress={"step": "queued", "message": "Waiting"},
            created_at=datetime.utcnow(),
        )
        db_session.add(job)
        db_session.commit()

        result = get_job_status(db_session, "status-test-1")

        assert result["job_id"] == "status-test-1"
        assert result["status"] == "pending"
        assert result["symbol"] == "TEST"
        assert "result" not in result
        assert "error" not in result

    def test_completed_job_includes_result(self, db_session):
        """Test completed job includes result."""
        job = Job(
            id="status-test-2",
            job_type="refresh",
            symbol="TEST",
            status="completed",
            progress={"step": "done"},
            result={"events_scored": 50},
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db_session.add(job)
        db_session.commit()

        result = get_job_status(db_session, "status-test-2")

        assert result["status"] == "completed"
        assert result["result"]["events_scored"] == 50
        assert result["completed_at"] is not None

    def test_failed_job_includes_error(self, db_session):
        """Test failed job includes error."""
        job = Job(
            id="status-test-3",
            job_type="refresh",
            symbol="TEST",
            status="failed",
            progress={"step": "error"},
            error="Connection refused",
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db_session.add(job)
        db_session.commit()

        result = get_job_status(db_session, "status-test-3")

        assert result["status"] == "failed"
        assert result["error"] == "Connection refused"


class TestRunRefreshAsync:
    """Tests for async refresh execution."""

    def test_job_not_found(self, db_session):
        """Test handles non-existent job gracefully."""
        # Should not raise
        with patch("app.services.async_refresh.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session.return_value = mock_db

            run_refresh_async("non-existent", "TEST")

    def test_successful_refresh(self, db_session):
        """Test successful refresh updates job status."""
        # Create symbol and job
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        db_session.add_all([symbol, profile])
        db_session.commit()

        job = create_refresh_job(db_session, "TEST")
        job_id = job.id

        # Mock all the service calls
        with patch("app.services.async_refresh.SessionLocal") as mock_session_local:
            # Create a mock session that returns our real job
            mock_db = MagicMock()

            # Make query().filter().first() return the job
            def mock_query(model):
                mock_q = MagicMock()
                if model == Job:
                    mock_q.filter.return_value.first.return_value = job
                elif model == CompanyProfile:
                    mock_q.filter.return_value.first.return_value = profile
                return mock_q

            mock_db.query.side_effect = mock_query
            mock_db.commit = MagicMock()
            mock_db.close = MagicMock()
            mock_session_local.return_value = mock_db

            with patch("app.services.async_refresh.get_settings") as mock_settings:
                settings = MagicMock()
                settings.massive_api_key = "test-key"
                settings.news_api_key = ""
                mock_settings.return_value = settings

                with patch("app.services.async_refresh.fetch_company_profile_polygon") as mock_profile:
                    mock_profile.return_value = {"updated": True}

                    with patch("app.services.async_refresh.fetch_price_history_polygon") as mock_prices:
                        mock_prices.return_value = {"bars_added": 100}

                        with patch("app.services.async_refresh.detect_major_movements") as mock_movements:
                            mock_movements.return_value = {"movements_detected": 10}

                            with patch("app.services.async_refresh.fetch_news_for_movements_massive") as mock_news:
                                mock_news.return_value = {"events_fetched": 50}

                                with patch("app.services.async_refresh.score_events_for_symbol") as mock_score:
                                    mock_score.return_value = {"events_scored": 50}

                                    with patch("app.services.async_refresh.create_movement_attributions") as mock_attr:
                                        mock_attr.return_value = {"attributions_created": 30}

                                        run_refresh_async(job_id, "TEST")

        # Verify job was updated
        assert job.status == "completed"
        assert job.result["price_bars_added"] == 100
        assert job.result["events_scored"] == 50

    def test_refresh_handles_exception(self, db_session):
        """Test refresh handles exceptions and marks job failed."""
        job = create_refresh_job(db_session, "TEST")
        job_id = job.id

        with patch("app.services.async_refresh.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = job
            mock_db.commit = MagicMock()
            mock_db.close = MagicMock()
            mock_session_local.return_value = mock_db

            with patch("app.services.async_refresh.get_settings") as mock_settings:
                mock_settings.side_effect = Exception("Settings error")

                run_refresh_async(job_id, "TEST")

        assert job.status == "failed"
        assert "Settings error" in job.error


class TestStartRefreshJob:
    """Tests for starting refresh jobs."""

    def test_creates_and_starts_job(self, db_session):
        """Test creates job and starts background thread."""
        with patch("app.services.async_refresh.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            job = start_refresh_job(db_session, "TEST")

            assert job.id is not None
            assert job.status == "pending"
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()

    def test_thread_is_daemon(self, db_session):
        """Test thread is started as daemon."""
        with patch("app.services.async_refresh.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            start_refresh_job(db_session, "TEST")

            # Check daemon=True was passed
            call_kwargs = mock_thread.call_args[1]
            assert call_kwargs["daemon"] is True
