"""
Polygon.io client for fetching stock price data.
"""
import httpx
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import PriceBar, CompanyProfile
from app.config import get_settings


POLYGON_AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
POLYGON_TICKER_URL = "https://api.polygon.io/v3/reference/tickers/{ticker}"
POLYGON_GROUPED_URL = "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}"

# ETF patterns to exclude when fetching popular stocks
ETF_PATTERNS = {
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO", "EEM", "EFA",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLB", "XLU", "XLRE",
    "TQQQ", "SQQQ", "SOXL", "SOXS", "TZA", "TNA", "UVXY", "VXX", "VIXY",
    "GLD", "SLV", "USO", "UNG", "BITO", "HYG", "LQD", "TLT", "IEF", "SHY",
    "IBIT", "ARKK", "ARKG", "ARKW", "ARKF",
}


def fetch_price_history_polygon(db: Session, ticker: str, days: int = None) -> dict:
    """
    Fetch historical daily price bars from Polygon.io.
    """
    settings = get_settings()

    if not settings.massive_api_key:
        return {"bars_added": 0, "error": "MASSIVE_API_KEY not configured"}

    if days is None:
        days = settings.default_lookback_days

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    url = POLYGON_AGGS_URL.format(
        ticker=ticker,
        from_date=start_date.isoformat(),
        to_date=end_date.isoformat(),
    )

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params={
                "adjusted": "true",
                "sort": "asc",
                "limit": 5000,
                "apiKey": settings.massive_api_key,
            })
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK" and data.get("resultsCount", 0) == 0:
            return {"bars_added": 0, "error": data.get("message", "No data returned")}

        results = data.get("results", [])
        bars_added = 0

        for bar in results:
            # Polygon returns timestamp in milliseconds
            ts = bar.get("t", 0) / 1000
            bar_date = datetime.fromtimestamp(ts).date()

            bar_data = {
                "symbol": ticker,
                "date": bar_date,
                "open": Decimal(str(bar.get("o", 0))),
                "high": Decimal(str(bar.get("h", 0))),
                "low": Decimal(str(bar.get("l", 0))),
                "close": Decimal(str(bar.get("c", 0))),
                "volume": int(bar.get("v", 0)),
            }

            stmt = insert(PriceBar).values(**bar_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(stmt)
            bars_added += 1

        db.commit()
        return {"bars_added": bars_added}

    except httpx.HTTPStatusError as e:
        return {"bars_added": 0, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        db.rollback()
        return {"bars_added": 0, "error": str(e)}


def fetch_company_profile_polygon(db: Session, ticker: str) -> dict:
    """
    Fetch company profile/details from Polygon.io.
    """
    settings = get_settings()

    if not settings.massive_api_key:
        return {"updated": False, "error": "MASSIVE_API_KEY not configured"}

    url = POLYGON_TICKER_URL.format(ticker=ticker)

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params={"apiKey": settings.massive_api_key})
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK":
            return {"updated": False, "error": data.get("message", "No data")}

        result = data.get("results", {})

        if not result:
            return {"updated": False, "error": "No ticker data found"}

        profile_data = {
            "symbol": ticker,
            "name": result.get("name", ticker),
            "sector": result.get("sic_description"),
            "industry": result.get("sic_description"),
            "profile_json": {
                "company_name": result.get("name"),
                "ticker": ticker,
                "aliases": [],
                "sector": result.get("sic_description"),
                "industry": result.get("sic_description"),
                "key_products": [],
                "geographies": [result.get("locale", "US").upper()],
                "competitors": [],
                "themes": [],
                "description": result.get("description", "")[:500] if result.get("description") else "",
                "market_cap": result.get("market_cap"),
                "employees": result.get("total_employees"),
                "homepage": result.get("homepage_url"),
            },
            "updated_at": datetime.utcnow(),
        }

        stmt = insert(CompanyProfile).values(**profile_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "name": stmt.excluded.name,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "profile_json": stmt.excluded.profile_json,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)
        db.commit()

        return {"updated": True, "name": result.get("name")}

    except httpx.HTTPStatusError as e:
        return {"updated": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"updated": False, "error": str(e)}


def _is_etf(ticker: str) -> bool:
    """Check if a ticker is likely an ETF."""
    if ticker in ETF_PATTERNS:
        return True
    # Common ETF prefixes
    etf_prefixes = ["XL", "VT", "VO", "VN", "TZ", "SQ", "SO", "IW", "IY", "IJ", "SP"]
    if any(ticker.startswith(p) for p in etf_prefixes):
        return True
    return False


def fetch_popular_symbols(
    limit: int = 25,
    min_price: float = 20.0,
    asset_type: str | None = None,  # "equities", "etfs", or None for both
) -> dict:
    """
    Fetch popular stock symbols from Polygon based on trading volume.

    Args:
        limit: Number of symbols to return
        min_price: Minimum stock price to include
        asset_type: Filter by type - "equities", "etfs", or None for both
    """
    settings = get_settings()

    if not settings.massive_api_key:
        return {"symbols": [], "error": "MASSIVE_API_KEY not configured"}

    # Use yesterday's date to ensure data is available
    target_date = date.today() - timedelta(days=1)
    # Skip weekends
    while target_date.weekday() >= 5:
        target_date -= timedelta(days=1)

    url = POLYGON_GROUPED_URL.format(date=target_date.isoformat())

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params={
                "adjusted": "true",
                "apiKey": settings.massive_api_key,
            })
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK":
            return {"symbols": [], "error": data.get("message", "No data")}

        results = data.get("results", [])

        # Base filter: price > min_price, has volume
        filtered = [
            r for r in results
            if r.get("c", 0) >= min_price
            and r.get("v", 0) > 0
        ]

        # Apply asset type filter
        if asset_type == "equities":
            filtered = [r for r in filtered if not _is_etf(r.get("T", ""))]
        elif asset_type == "etfs":
            filtered = [r for r in filtered if _is_etf(r.get("T", ""))]
        # else: None means both, no additional filtering

        # Sort by volume descending
        filtered.sort(key=lambda x: x.get("v", 0), reverse=True)

        # Take top N
        symbols = [r["T"] for r in filtered[:limit]]

        return {"symbols": symbols, "date": target_date.isoformat()}

    except httpx.HTTPStatusError as e:
        return {"symbols": [], "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"symbols": [], "error": str(e)}
