from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.symbols import router as symbols_router
from app.api.analysis import router as analysis_router
from app.api.chat import router as chat_router
from app.api.jobs import router as jobs_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(symbols_router, prefix="/api/v1", tags=["symbols"])
api_router.include_router(analysis_router, prefix="/api/v1", tags=["analysis"])
api_router.include_router(chat_router, prefix="/api/v1", tags=["chat"])
api_router.include_router(jobs_router, prefix="/api/v1", tags=["jobs"])
