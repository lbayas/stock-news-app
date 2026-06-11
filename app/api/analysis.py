from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import date, timedelta

from app.db import get_db
from app.models import Symbol
from app.schemas import AnalysisResponse
from app.services.analysis import get_ticker_analysis

router = APIRouter()


@router.get(
    "/tickers/{ticker}/analysis",
    response_model=AnalysisResponse,
    summary="Get stock movement analysis",
    description="""
Returns major price movements for a ticker with correlated news explanations.

**Movement Detection:**
- Major movements are days where the stock moved >= min_move_pct (default 2%)
- Each movement includes direction (up/down), percentage change, and volume

**Explanations:**
- **primary**: Top 1-3 directly related events (earnings, lawsuits, product launches)
- **supporting**: Industry/competitor news providing context
- **indirect**: Macro events (Fed decisions, geopolitics) worth noting

**Filters:**
- Date range, direction, minimum correlation score, correlation tier
- Use `include_prices=true` to get price summary for the period
    """,
    response_description="Analysis with major movements and news explanations",
)
def get_analysis(
    ticker: str = Path(..., description="Stock ticker symbol (e.g., AAPL)"),
    start_date: date | None = Query(None, description="Start date (default: 1 week ago)"),
    end_date: date | None = Query(None, description="End date (default: today)"),
    min_move_pct: float = Query(2.0, description="Minimum % change to consider major", ge=0),
    direction: str | None = Query(None, description="Filter by direction: 'up' or 'down'"),
    min_correlation_score: float | None = Query(None, description="Minimum correlation score (0.0-1.0)", ge=0, le=1),
    correlation_tier: str | None = Query(None, description="Filter by tier: 'high', 'medium', 'low'"),
    include_prices: bool = Query(False, description="Include price summary in response"),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not symbol:
        raise HTTPException(status_code=404, detail=f"Symbol {ticker} not found")

    # Default date range: last week
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=7)

    # Validate direction
    if direction and direction not in ("up", "down"):
        raise HTTPException(
            status_code=400, detail="direction must be 'up' or 'down'"
        )

    # Validate correlation_tier
    if correlation_tier and correlation_tier not in ("high", "medium", "low"):
        raise HTTPException(
            status_code=400, detail="correlation_tier must be 'high', 'medium', or 'low'"
        )

    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "min_move_pct": min_move_pct,
        "direction": direction,
        "min_correlation_score": min_correlation_score,
        "correlation_tier": correlation_tier,
        "include_prices": include_prices,
    }

    return get_ticker_analysis(db, ticker, filters)
