from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router

DESCRIPTION = """
Menton explains major stock price movements using correlated news events.

## Quick Start

1. **Sync popular symbols** → `POST /api/v1/symbols/sync`
2. **Refresh a ticker** → `POST /api/v1/symbols/{ticker}/refresh`
3. **Get analysis** → `GET /api/v1/tickers/{ticker}/analysis`
4. **Ask questions** → `POST /api/v1/chat`

## How It Works

For any ticker, Menton:
1. Fetches historical prices from **MASSIVE (Polygon)**
2. Detects **major movements** (days with ≥2% change)
3. Fetches news around those dates
4. Scores relevance using **OpenAI** (0.0-1.0)
5. Creates attributions linking news → price moves

## Correlation Tiers

| Tier | Score | Examples |
|------|-------|----------|
| **High** | ≥0.70 | Earnings, lawsuits, product launches, exec changes |
| **Medium** | 0.35-0.70 | Competitor news, industry trends, supply chain |
| **Low** | <0.35 | Fed rates, geopolitics, broad market moves |

## Attribution Labels

Each movement includes ranked explanations:
- **Primary**: Top 1-3 directly related events
- **Supporting**: Industry/competitor context
- **Indirect**: Macro factors worth noting
"""

app = FastAPI(
    title="Menton",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "symbols",
            "description": "Sync and refresh stock symbols. Start here to add tickers to the system.",
        },
        {
            "name": "jobs",
            "description": "Track async refresh jobs. Poll job status after calling `/symbols/{ticker}/refresh`.",
        },
        {
            "name": "analysis",
            "description": "Get structured analysis of price movements with correlated news events.",
        },
        {
            "name": "chat",
            "description": "Ask natural language questions about why a stock moved.",
        },
        {
            "name": "health",
            "description": "System health checks.",
        },
    ],
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "name": "Menton",
        "description": "Stock Movement + News Correlation System",
        "docs": "/docs",
    }
