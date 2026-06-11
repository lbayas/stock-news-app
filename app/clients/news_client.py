"""
NewsAPI client for fetching news around major movement dates.
"""
import httpx
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import NewsEvent, PriceMovement
from app.config import get_settings


NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"


def fetch_news_for_movements(db: Session, ticker: str, company_name: str) -> dict:
    """
    Fetch news around major movement dates for a ticker.

    Strategy:
    - Get all major movements for the ticker
    - For each movement, fetch news from (date - 1 day) to (date)
    - Search for ticker, company name, and aliases
    """
    settings = get_settings()

    if not settings.news_api_key:
        return {"events_fetched": 0, "error": "NEWS_API_KEY not configured"}

    # Get major movements
    movements = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .order_by(PriceMovement.date.desc())
        .limit(10)  # Limit to recent movements to manage API calls
        .all()
    )

    if not movements:
        return {"events_fetched": 0, "error": "No major movements found"}

    # Build search query
    search_terms = [ticker, company_name]
    query = " OR ".join(f'"{term}"' for term in search_terms if term)

    events_fetched = 0
    errors = []

    # Collect unique date windows to avoid duplicate API calls
    date_windows = set()
    for movement in movements:
        # News window: day before to day of movement
        from_date = movement.date - timedelta(days=1)
        to_date = movement.date
        date_windows.add((from_date, to_date))

    headers = {"X-Api-Key": settings.news_api_key}

    with httpx.Client(timeout=30.0) as client:
        for from_date, to_date in date_windows:
            try:
                params = {
                    "q": query,
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "language": "en",
                    "sortBy": "relevancy",
                    "pageSize": 20,
                }

                response = client.get(NEWSAPI_BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "ok":
                    errors.append(f"API error: {data.get('message', 'Unknown error')}")
                    continue

                articles = data.get("articles", [])

                for article in articles:
                    # Skip articles without required fields
                    if not article.get("url") or not article.get("title"):
                        continue

                    # Parse published date
                    published_str = article.get("publishedAt", "")
                    try:
                        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue

                    event_data = {
                        "published_at": published_at,
                        "title": article.get("title", "")[:500],
                        "url": article.get("url", "")[:1000],
                        "source": article.get("source", {}).get("name", "")[:100],
                        "provider": "newsapi",
                        "summary": article.get("description", "")[:2000] if article.get("description") else None,
                        "body": article.get("content", "")[:5000] if article.get("content") else None,
                    }

                    # Upsert - skip if URL already exists
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


def fetch_news_for_date_range(
    db: Session,
    ticker: str,
    company_name: str,
    from_date: date,
    to_date: date,
) -> dict:
    """
    Fetch news for a specific date range.
    Useful for manual refresh or backfill.
    """
    settings = get_settings()

    if not settings.news_api_key:
        return {"events_fetched": 0, "error": "NEWS_API_KEY not configured"}

    search_terms = [ticker, company_name]
    query = " OR ".join(f'"{term}"' for term in search_terms if term)

    headers = {"X-Api-Key": settings.news_api_key}
    events_fetched = 0

    try:
        with httpx.Client(timeout=30.0) as client:
            params = {
                "q": query,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": 100,
            }

            response = client.get(NEWSAPI_BASE_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                return {"events_fetched": 0, "error": data.get("message", "Unknown error")}

            for article in data.get("articles", []):
                if not article.get("url") or not article.get("title"):
                    continue

                published_str = article.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                event_data = {
                    "published_at": published_at,
                    "title": article.get("title", "")[:500],
                    "url": article.get("url", "")[:1000],
                    "source": article.get("source", {}).get("name", "")[:100],
                    "provider": "newsapi",
                    "summary": article.get("description", "")[:2000] if article.get("description") else None,
                    "body": article.get("content", "")[:5000] if article.get("content") else None,
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
