"""Tests for Jobs API endpoints."""
import pytest
from datetime import datetime

from app.models import Job


def test_get_job_not_found(client):
    """Test getting a non-existent job returns 404."""
    response = client.get("/api/v1/jobs/non-existent-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_job_pending(client, db_session):
    """Test getting a pending job."""
    job = Job(
        id="test-job-1",
        job_type="refresh",
        symbol="TEST",
        status="pending",
        progress={"step": "queued", "message": "Waiting to start"},
        created_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs/test-job-1")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-1"
    assert data["status"] == "pending"
    assert data["symbol"] == "TEST"
    assert data["progress"]["step"] == "queued"


def test_get_job_completed_with_result(client, db_session):
    """Test getting a completed job includes result."""
    job = Job(
        id="test-job-2",
        job_type="refresh",
        symbol="TEST",
        status="completed",
        progress={"step": "done", "message": "Completed"},
        result={"events_scored": 10, "movements_detected": 5},
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs/test-job-2")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["result"]["events_scored"] == 10
    assert data["result"]["movements_detected"] == 5


def test_get_job_failed_with_error(client, db_session):
    """Test getting a failed job includes error."""
    job = Job(
        id="test-job-3",
        job_type="refresh",
        symbol="TEST",
        status="failed",
        progress={"step": "error", "message": "Something went wrong"},
        error="Connection timeout",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs/test-job-3")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "Connection timeout"


def test_list_jobs_empty(client):
    """Test listing jobs when none exist."""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json()["jobs"] == []


def test_list_jobs(client, db_session):
    """Test listing jobs returns all jobs."""
    for i in range(3):
        job = Job(
            id=f"list-job-{i}",
            job_type="refresh",
            symbol="TEST",
            status="completed",
            created_at=datetime.utcnow(),
        )
        db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 3


def test_list_jobs_filter_by_symbol(client, db_session):
    """Test filtering jobs by symbol."""
    job1 = Job(id="sym-job-1", job_type="refresh", symbol="AAPL", status="completed", created_at=datetime.utcnow())
    job2 = Job(id="sym-job-2", job_type="refresh", symbol="MSFT", status="completed", created_at=datetime.utcnow())
    db_session.add_all([job1, job2])
    db_session.commit()

    response = client.get("/api/v1/jobs?symbol=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["symbol"] == "AAPL"


def test_list_jobs_filter_by_status(client, db_session):
    """Test filtering jobs by status."""
    job1 = Job(id="stat-job-1", job_type="refresh", symbol="TEST", status="completed", created_at=datetime.utcnow())
    job2 = Job(id="stat-job-2", job_type="refresh", symbol="TEST", status="failed", created_at=datetime.utcnow())
    db_session.add_all([job1, job2])
    db_session.commit()

    response = client.get("/api/v1/jobs?status=failed")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "failed"


def test_list_jobs_limit(client, db_session):
    """Test limiting number of jobs returned."""
    for i in range(10):
        job = Job(id=f"limit-job-{i}", job_type="refresh", symbol="TEST", status="completed", created_at=datetime.utcnow())
        db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 5
