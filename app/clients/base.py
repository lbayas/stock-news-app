"""Base interfaces for external API clients.

Use Protocol (structural typing) for extensibility - any class that implements
the required methods will satisfy the interface without explicit inheritance.
"""
from typing import Protocol
from sqlalchemy.orm import Session


class NewsClient(Protocol):
    """Interface for news data providers.

    To add a new news source:
    1. Create a class that implements fetch_news_for_movements()
    2. Register it in async_refresh.py's news fetching loop

    Example:
        class MyNewsClient:
            def __init__(self, api_key: str):
                self.api_key = api_key

            def fetch_news_for_movements(self, db: Session, ticker: str) -> dict:
                # Fetch news and return {"events_fetched": N} or {"error": "..."}
                ...
    """

    def fetch_news_for_movements(self, db: Session, ticker: str, **kwargs) -> dict:
        """Fetch news articles around major movement dates.

        Args:
            db: Database session for querying movements and storing events
            ticker: Stock ticker symbol
            **kwargs: Provider-specific options (e.g., company_name)

        Returns:
            dict with keys:
                - events_fetched: int - number of news events stored
                - error: str (optional) - error message if failed
        """
        ...


class PriceClient(Protocol):
    """Interface for price data providers.

    To add a new price source:
    1. Create a class that implements both methods
    2. Update async_refresh.py to use your client
    """

    def fetch_price_history(self, db: Session, ticker: str, days: int = None) -> dict:
        """Fetch historical daily price bars.

        Returns:
            dict with keys:
                - bars_added: int - number of price bars stored
                - error: str (optional) - error message if failed
        """
        ...

    def fetch_company_profile(self, db: Session, ticker: str) -> dict:
        """Fetch company profile/metadata.

        Returns:
            dict with keys:
                - updated: bool - whether profile was updated
                - name: str (optional) - company name
                - error: str (optional) - error message if failed
        """
        ...
