"""
MASSIVE (Polygon.io) client for fetching financial news.
"""
import httpx
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import NewsEvent, PriceMovement
from app.config import get_settings


POLYGON_NEWS_URL = "https://api.polygon.io/v2/reference/news"


def fetch_news_for_movements_massive(db: Session, ticker: str) -> dict:
    """
    Fetch news around major movement dates for a ticker using Polygon/MASSIVE API.
    """
    settings = get_settings()

    if not settings.massive_api_key:
        return {"events_fetched": 0, "error": "MASSIVE_API_KEY not configured"}

    # Get major movements
    movements = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .order_by(PriceMovement.date.desc())
        .limit(10)
        .all()
    )

    if not movements:
        return {"events_fetched": 0, "error": "No major movements found"}

    events_fetched = 0
    errors = []

    # Collect unique date windows
    date_windows = set()
    for movement in movements:
        from_date = movement.date - timedelta(days=1)
        to_date = movement.date
        date_windows.add((from_date, to_date))

    with httpx.Client(timeout=30.0) as client:
        for from_date, to_date in date_windows:
            try:
                params = {
                    "ticker": ticker,
                    "published_utc.gte": from_date.isoformat(),
                    "published_utc.lte": f"{to_date.isoformat()}T23:59:59Z",
                    "order": "desc",
                    "limit": 20,
                    "apiKey": settings.massive_api_key,
                }

                response = client.get(POLYGON_NEWS_URL, params=params)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])

                for article in results:
                    if not article.get("article_url") or not article.get("title"):
                        continue

                    # Parse published date
                    published_str = article.get("published_utc", "")
                    try:
                        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue

                    # Get publisher name
                    publisher = article.get("publisher", {})
                    source_name = publisher.get("name", "") if isinstance(publisher, dict) else ""

                    event_data = {
                        "published_at": published_at,
                        "title": article.get("title", "")[:500],
                        "url": article.get("article_url", "")[:1000],
                        "source": source_name[:100],
                        "provider": "polygon",
                        "summary": article.get("description", "")[:2000] if article.get("description") else None,
                        "body": None,  # Polygon doesn't provide full body in free tier
                    }

                    stmt = insert(NewsEvent).values(**event_data)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
                    result = db.execute(stmt)

                    if result.rowcount > 0:
                        events_fetched += 1

            except httpx.HTTPStatusError as e:
                errors.append(f"HTTP error for {from_date}: {e.response.status_code}")
            except Exception as e:
                errors.append(f"Error for {from_date}: {str(e)}")

    db.commit()

    result = {"events_fetched": events_fetched}
    if errors:
        result["errors"] = errors

    return result


def fetch_news_for_ticker_massive(
    db: Session,
    ticker: str,
    from_date: date,
    to_date: date,
    limit: int = 50,
) -> dict:
    """
    Fetch news for a specific ticker and date range using Polygon/MASSIVE API.
    """
    settings = get_settings()

    if not settings.massive_api_key:
        return {"events_fetched": 0, "error": "MASSIVE_API_KEY not configured"}

    events_fetched = 0

    try:
        with httpx.Client(timeout=30.0) as client:
            params = {
                "ticker": ticker,
                "published_utc.gte": from_date.isoformat(),
                "published_utc.lte": f"{to_date.isoformat()}T23:59:59Z",
                "order": "desc",
                "limit": limit,
                "apiKey": settings.massive_api_key,
            }

            response = client.get(POLYGON_NEWS_URL, params=params)
            response.raise_for_status()
            data = response.json()

            for article in data.get("results", []):
                if not article.get("article_url") or not article.get("title"):
                    continue

                published_str = article.get("published_utc", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                publisher = article.get("publisher", {})
                source_name = publisher.get("name", "") if isinstance(publisher, dict) else ""

                event_data = {
                    "published_at": published_at,
                    "title": article.get("title", "")[:500],
                    "url": article.get("article_url", "")[:1000],
                    "source": source_name[:100],
                    "provider": "polygon",
                    "summary": article.get("description", "")[:2000] if article.get("description") else None,
                    "body": None,
                }

                stmt = insert(NewsEvent).values(**event_data)
                stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
                result = db.execute(stmt)

                if result.rowcount > 0:
                    events_fetched += 1

            db.commit()

    except httpx.HTTPStatusError as e:
        return {"events_fetched": events_fetched, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"events_fetched": events_fetched, "error": str(e)}

    return {"events_fetched": events_fetched}
