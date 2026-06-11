from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal


class AnalysisFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    min_move_pct: float = 2.0
    direction: str | None = None  # "up", "down", or None for both
    min_correlation_score: float | None = None
    correlation_tier: str | None = None  # "high", "medium", "low"
    include_prices: bool = False


class EventExplanation(BaseModel):
    title: str
    url: str
    source: str | None
    published_at: datetime
    correlation_score: float
    correlation_tier: str
    rationale: str | None

    class Config:
        from_attributes = True


class Explanations(BaseModel):
    primary: list[EventExplanation] = Field(default_factory=list)
    supporting: list[EventExplanation] = Field(default_factory=list)
    indirect: list[EventExplanation] = Field(default_factory=list)


class MajorMovement(BaseModel):
    date: date
    pct_change: float
    direction: str
    volume: int | None
    explanations: Explanations


class CompanySummary(BaseModel):
    name: str
    sector: str | None
    industry: str | None


class PriceSummary(BaseModel):
    start_date: date
    end_date: date
    start_close: float
    end_close: float
    total_return_pct: float


class AnalysisResponse(BaseModel):
    ticker: str
    company: CompanySummary | None
    filters_applied: dict
    price_summary: PriceSummary | None
    major_movements: list[MajorMovement]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ticker": "META",
                    "company": {
                        "name": "Meta Platforms, Inc.",
                        "sector": "Technology",
                        "industry": "Social Media"
                    },
                    "filters_applied": {
                        "start_date": "2026-06-04",
                        "end_date": "2026-06-11",
                        "min_move_pct": 2.0,
                        "direction": None,
                        "include_prices": True
                    },
                    "price_summary": {
                        "start_date": "2026-06-04",
                        "end_date": "2026-06-10",
                        "start_close": 627.57,
                        "end_close": 570.98,
                        "total_return_pct": -9.02
                    },
                    "major_movements": [
                        {
                            "date": "2026-06-10",
                            "pct_change": -2.33,
                            "direction": "down",
                            "volume": 17064048,
                            "explanations": {
                                "primary": [
                                    {
                                        "title": "Meta Partners With Reliance for AI Data Centers",
                                        "url": "https://example.com/meta-reliance",
                                        "source": "Reuters",
                                        "published_at": "2026-06-10T09:22:17",
                                        "correlation_score": 0.9,
                                        "correlation_tier": "high",
                                        "rationale": "Direct company partnership announcement"
                                    }
                                ],
                                "supporting": [],
                                "indirect": []
                            }
                        }
                    ]
                }
            ]
        }
    }
