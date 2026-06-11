from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://menton:menton@localhost:5432/menton"
    openai_api_key: str = ""
    news_api_key: str = ""
    massive_api_key: str = ""  # Polygon.io / MASSIVE
    major_move_threshold: float = 2.0
    default_lookback_days: int = 365
    openai_max_workers: int = 5  # Concurrent API calls for scoring

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
