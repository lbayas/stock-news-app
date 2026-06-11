from pydantic import BaseModel, Field
from datetime import date, datetime


class ChatFilters(BaseModel):
    start_date: date | None = Field(None, description="Start date for filtering movements")
    end_date: date | None = Field(None, description="End date for filtering movements")


class ChatRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol", examples=["META"])
    message: str = Field(..., description="Your question about the stock", examples=["Why did the stock drop recently?"])
    filters: ChatFilters | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ticker": "META",
                    "message": "Why did the stock drop recently?"
                }
            ]
        }
    }


class ChatSource(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: datetime
    correlation_score: float
    correlation_tier: str


class ChatResponse(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    message: str = Field(..., description="Original user message")
    response: str = Field(..., description="AI-generated response grounded in data")
    sources: list[ChatSource] = Field(default=[], description="News sources cited in response")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ticker": "META",
                    "message": "Why did the stock drop recently?",
                    "response": "META dropped 2.33% on June 10, 2026, declining from $584.60 to $570.98. This movement coincided with a broader tech sector sell-off. However, the company announced a significant AI infrastructure partnership with Reliance Industries to build data centers in India, which analysts view positively for long-term growth.",
                    "sources": [
                        {
                            "title": "Mark Zuckerberg Teams Up With India's Richest Man To Build Meta's Next AI Powerhouse",
                            "url": "https://www.benzinga.com/markets/tech/26/06/mark-zuckerberg-reliance-ai",
                            "source": "Benzinga",
                            "published_at": "2026-06-10T09:22:17",
                            "correlation_score": 0.9,
                            "correlation_tier": "high"
                        },
                        {
                            "title": "2 Glorious Growth Stocks to Buy During the Latest Tech Sell-Off",
                            "url": "https://www.fool.com/investing/2026/06/10/growth-stocks-tech-sell-off",
                            "source": "The Motley Fool",
                            "published_at": "2026-06-10T13:15:00",
                            "correlation_score": 0.85,
                            "correlation_tier": "high"
                        }
                    ]
                }
            ]
        }
    }
