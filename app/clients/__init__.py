"""External API clients for data fetching."""
from app.clients.massive_client import (
    fetch_news_for_movements_massive,
    fetch_news_for_ticker_massive,
)
from app.clients.polygon_prices import (
    fetch_price_history_polygon,
    fetch_company_profile_polygon,
    fetch_popular_symbols,
)

__all__ = [
    "fetch_news_for_movements_massive",
    "fetch_news_for_ticker_massive",
    "fetch_price_history_polygon",
    "fetch_company_profile_polygon",
    "fetch_popular_symbols",
]
