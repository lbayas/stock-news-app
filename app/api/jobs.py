"""
Jobs API for tracking async operations.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Literal

from app.db import get_db
from app.models import Job
from app.services.async_refresh import get_job_status

router = APIRouter()


@router.get(
    "/jobs/{job_id}",
    summary="Get job status",
    description="""
Get the status of an async job.

**Status values:**
- `pending` - Job created, waiting to start
- `processing` - Job is running
- `completed` - Job finished successfully
- `failed` - Job encountered an error

When completed, the response includes the full result.
When failed, the response includes the error message.
    """,
    responses={
        200: {
            "description": "Job status",
            "content": {
                "application/json": {
                    "examples": {
                        "processing": {
                            "summary": "Job in progress",
                            "value": {
                                "job_id": "c35edcda-d3ca-4439-a67d-6a6445223b9d",
                                "job_type": "refresh",
                                "symbol": "META",
                                "status": "processing",
                                "progress": {"step": "scoring", "message": "Scoring events with AI..."},
                                "created_at": "2026-06-11T18:33:08",
                                "started_at": "2026-06-11T18:33:08",
                                "completed_at": None
                            }
                        },
                        "completed": {
                            "summary": "Job completed",
                            "value": {
                                "job_id": "c35edcda-d3ca-4439-a67d-6a6445223b9d",
                                "job_type": "refresh",
                                "symbol": "META",
                                "status": "completed",
                                "progress": {"step": "done", "message": "Refresh completed"},
                                "created_at": "2026-06-11T18:33:08",
                                "started_at": "2026-06-11T18:33:08",
                                "completed_at": "2026-06-11T18:34:40",
                                "result": {
                                    "ticker": "META",
                                    "profile_updated": True,
                                    "price_bars_added": 251,
                                    "movements_detected": 65,
                                    "news_fetched": 150,
                                    "events_scored": 314,
                                    "attributions_created": 207
                                }
                            }
                        }
                    }
                }
            }
        }
    },
)
def get_job(job_id: str, db: Session = Depends(get_db)):
    result = get_job_status(db, job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return result


@router.get(
    "/jobs",
    summary="List recent jobs",
    description="List recent jobs, optionally filtered by symbol or status.",
)
def list_jobs(
    symbol: str | None = Query(None, description="Filter by symbol"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, description="Max jobs to return", le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Job).order_by(Job.created_at.desc())

    if symbol:
        query = query.filter(Job.symbol == symbol.upper())
    if status:
        query = query.filter(Job.status == status)

    jobs = query.limit(limit).all()

    return {
        "jobs": [
            {
                "job_id": job.id,
                "job_type": job.job_type,
                "symbol": job.symbol,
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ]
    }
