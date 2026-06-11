"""
Async refresh service with job tracking and progress updates.
"""
import uuid
import threading
from datetime import datetime
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Job, CompanyProfile
from app.clients import (
    fetch_price_history_polygon,
    fetch_company_profile_polygon,
    fetch_news_for_movements,
    fetch_news_for_movements_massive,
)
from app.services.movement import detect_major_movements
from app.services.correlation import score_events_for_symbol, create_movement_attributions
from app.config import get_settings


def create_refresh_job(db: Session, ticker: str) -> Job:
    """Create a new refresh job and return it."""
    job = Job(
        id=str(uuid.uuid4()),
        job_type="refresh",
        symbol=ticker,
        status="pending",
        progress={"step": "queued", "message": "Job created, waiting to start"},
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_refresh_async(job_id: str, ticker: str):
    """
    Run the refresh pipeline in a background thread.
    Updates job progress as it runs.
    """
    # Create a new session for this thread
    db = SessionLocal()

    try:
        # Get the job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        # Mark as processing
        job.status = "processing"
        job.started_at = datetime.utcnow()
        job.progress = {"step": "starting", "message": "Starting refresh pipeline"}
        db.commit()

        settings = get_settings()
        results = {
            "ticker": ticker,
            "profile_updated": False,
            "price_bars_added": 0,
            "movements_detected": 0,
            "news_fetched": 0,
            "events_scored": 0,
            "attributions_created": 0,
            "errors": [],
        }

        # Step 1: Company profile
        _update_progress(db, job, "profile", "Fetching company profile...")
        profile_result = fetch_company_profile_polygon(db, ticker)
        results["profile_updated"] = profile_result.get("updated", False)
        if "error" in profile_result:
            results["errors"].append(f"Profile: {profile_result['error']}")

        # Step 2: Price history
        _update_progress(db, job, "prices", "Fetching price history...")
        price_result = fetch_price_history_polygon(db, ticker)
        results["price_bars_added"] = price_result.get("bars_added", 0)
        if "error" in price_result:
            results["errors"].append(f"Prices: {price_result['error']}")

        # Step 3: Movement detection
        _update_progress(db, job, "movements", "Detecting major movements...")
        movement_result = detect_major_movements(db, ticker)
        results["movements_detected"] = movement_result.get("movements_detected", 0)
        if "error" in movement_result:
            results["errors"].append(f"Movements: {movement_result['error']}")

        # Step 4: News fetching
        _update_progress(db, job, "news", "Fetching news articles...")
        profile = db.query(CompanyProfile).filter(CompanyProfile.symbol == ticker).first()
        company_name = profile.name if profile else ticker

        total_news = 0
        # Primary: MASSIVE (Polygon) news
        massive_result = fetch_news_for_movements_massive(db, ticker)
        total_news += massive_result.get("events_fetched", 0)
        if "error" in massive_result:
            results["errors"].append(f"MASSIVE: {massive_result['error']}")

        # Optional: NewsAPI as secondary source
        if settings.news_api_key:
            news_result = fetch_news_for_movements(db, ticker, company_name)
            total_news += news_result.get("events_fetched", 0)
            if "error" in news_result:
                results["errors"].append(f"NewsAPI: {news_result['error']}")

        results["news_fetched"] = total_news

        # Step 5: LLM scoring (the slow part)
        _update_progress(db, job, "scoring", "Scoring events with AI (this may take a while)...")
        score_result = score_events_for_symbol(db, ticker)
        results["events_scored"] = score_result.get("events_scored", 0)
        if "error" in score_result:
            results["errors"].append(f"Scoring: {score_result['error']}")
        if "errors" in score_result:
            results["errors"].extend([f"Scoring: {e}" for e in score_result["errors"]])

        # Step 6: Attribution creation
        _update_progress(db, job, "attributions", "Creating movement attributions...")
        attr_result = create_movement_attributions(db, ticker)
        results["attributions_created"] = attr_result.get("attributions_created", 0)

        # Clean up errors
        if not results["errors"]:
            del results["errors"]

        # Mark as completed
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.progress = {"step": "done", "message": "Refresh completed"}
        job.result = results
        db.commit()

    except Exception as e:
        # Mark as failed
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.error = str(e)
            job.progress = {"step": "error", "message": str(e)}
            db.commit()

    finally:
        db.close()


def _update_progress(db: Session, job: Job, step: str, message: str):
    """Update job progress."""
    job.progress = {"step": step, "message": message}
    db.commit()


def start_refresh_job(db: Session, ticker: str) -> Job:
    """
    Create a job and start the refresh in a background thread.
    Returns the job immediately.
    """
    job = create_refresh_job(db, ticker)

    # Start background thread
    thread = threading.Thread(
        target=run_refresh_async,
        args=(job.id, ticker),
        daemon=True,
    )
    thread.start()

    return job


def get_job_status(db: Session, job_id: str) -> dict | None:
    """Get the status of a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None

    result = {
        "job_id": job.id,
        "job_type": job.job_type,
        "symbol": job.symbol,
        "status": job.status,
        "progress": job.progress,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }

    if job.status == "completed" and job.result:
        result["result"] = job.result

    if job.status == "failed" and job.error:
        result["error"] = job.error

    return result
