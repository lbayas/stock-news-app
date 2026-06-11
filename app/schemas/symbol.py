from pydantic import BaseModel, Field
from datetime import datetime


class SymbolResponse(BaseModel):
    ticker: str = Field(..., examples=["META"])
    is_active: bool = Field(..., examples=[True])
    created_at: datetime

    class Config:
        from_attributes = True


class SymbolListResponse(BaseModel):
    symbols: list[SymbolResponse]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbols": [
                        {"ticker": "META", "is_active": True, "created_at": "2026-06-11T18:50:02"},
                        {"ticker": "NVDA", "is_active": True, "created_at": "2026-06-11T18:50:02"},
                        {"ticker": "AAPL", "is_active": True, "created_at": "2026-06-11T18:50:02"},
                    ]
                }
            ]
        }
    }
