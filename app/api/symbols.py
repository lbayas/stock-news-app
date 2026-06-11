from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Symbol
from app.schemas import SymbolResponse, SymbolListResponse
from app.services.async_refresh import start_refresh_job
from app.clients import fetch_popular_symbols

router = APIRouter()


class AssetType(str, Enum):
    equities = "equities"
    etfs = "etfs"


@router.get(
    "/symbols",
    response_model=SymbolListResponse,
    summary="List all symbols",
    description="Returns all active stock symbols tracked by the system.",
)
def list_symbols(db: Session = Depends(get_db)):
    """List all active symbols in the database."""
    symbols = db.query(Symbol).filter(Symbol.is_active == True).all()
    return SymbolListResponse(symbols=symbols)


@router.post(
    "/symbols/{ticker}/refresh",
    summary="Add & refresh symbol",
    description="""
Adds a symbol (if new) and triggers a full data refresh pipeline:

1. **Fetch company profile** from Polygon/yfinance
2. **Fetch historical prices** for the configured lookback period
3. **Detect major movements** (days with >= threshold % change)
4. **Fetch news** around movement windows from Polygon/NewsAPI
5. **LLM score events** for correlation using OpenAI
6. **Create attributions** linking events to movements

Returns immediately with a job_id. Poll `/api/v1/jobs/{job_id}` for status.
    """,
    response_description="Job ID for tracking refresh progress",
)
def refresh_symbol(
    ticker: str = Path(..., description="Stock ticker symbol (e.g., AAPL, MSFT)"),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()

    created = False
    if not symbol:
        # Auto-create the symbol
        symbol = Symbol(ticker=ticker, is_active=True)
        db.add(symbol)
        db.commit()
        created = True

    job = start_refresh_job(db, ticker)

    return {
        "job_id": job.id,
        "status": "pending",
        "symbol_created": created,
        "message": f"Refresh job started for {ticker}. Poll /api/v1/jobs/{job.id} for status.",
    }


@router.post(
    "/symbols/sync",
    summary="Sync popular symbols",
    description="""
Fetches the most actively traded symbols from MASSIVE (Polygon) and adds them to the system.

**Asset types:**
- `equities` - Individual stocks only (AAPL, NVDA, META, etc.)
- `etfs` - ETFs only (SPY, QQQ, ARKK, etc.)
- No filter - Both equities and ETFs

Does NOT auto-refresh them - call `/symbols/{ticker}/refresh` to fetch data for each.
    """,
    response_description="List of symbols synced from MASSIVE",
)
def sync_symbols(
    limit: int = Query(25, description="Number of symbols to fetch", ge=1, le=100),
    min_price: float = Query(20.0, description="Minimum stock price to include", ge=1),
    asset_type: AssetType | None = Query(None, description="Filter by asset type"),
    db: Session = Depends(get_db),
):
    # Fetch popular symbols from MASSIVE
    result = fetch_popular_symbols(
        limit=limit,
        min_price=min_price,
        asset_type=asset_type.value if asset_type else None,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    symbols = result.get("symbols", [])
    added = []
    existing = []

    for ticker in symbols:
        symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()
        if not symbol:
            symbol = Symbol(ticker=ticker, is_active=True)
            db.add(symbol)
            added.append(ticker)
        else:
            existing.append(ticker)

    db.commit()

    return {
        "added": added,
        "existing": existing,
        "source_date": result.get("date"),
        "total": len(symbols),
    }
