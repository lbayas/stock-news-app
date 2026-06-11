# Menton

Stock Movement + News Correlation System. Menton explains major stock price movements using correlated news events.

## What It Does

For any stock ticker, Menton:

1. **Fetches historical prices** from MASSIVE (Polygon.io)
2. **Detects major movements** (days with ≥2% price change)
3. **Fetches news** around those movement dates
4. **Scores relevance** using OpenAI (0.0-1.0 correlation score)
5. **Creates attributions** linking news events to price movements
6. **Exposes findings** via REST API and natural language chat

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your API keys

# 2. Start services
docker compose up -d

# 3. Sync popular symbols
curl -X POST http://localhost:8000/api/v1/symbols/sync

# 4. Refresh a ticker (fetches data + scores events)
curl -X POST http://localhost:8000/api/v1/symbols/META/refresh

# 5. Check job status
curl http://localhost:8000/api/v1/jobs/{job_id}

# 6. Get analysis
curl http://localhost:8000/api/v1/tickers/META/analysis

# 7. Ask questions
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "META", "message": "Why did the stock drop recently?"}'
```

API docs available at http://localhost:8000/docs

## Requirements

### API Keys

| Key | Required | Source |
|-----|----------|--------|
| `MASSIVE_API_KEY` | Yes | [Polygon.io](https://polygon.io) - prices, company data, news |
| `OPENAI_API_KEY` | Yes | [OpenAI](https://platform.openai.com) - correlation scoring, chat |
| `NEWS_API_KEY` | Optional | [NewsAPI](https://newsapi.org) - additional news source |

### Infrastructure

- Docker & Docker Compose
- PostgreSQL 16 (runs in Docker)
- Python 3.12+ (runs in Docker)

## Configuration

```bash
# .env
DATABASE_URL=postgresql://menton:menton@db:5432/menton

# Required
MASSIVE_API_KEY=your_polygon_api_key
OPENAI_API_KEY=your_openai_api_key

# Optional
NEWS_API_KEY=your_newsapi_key

# Tuning
MAJOR_MOVE_THRESHOLD=2.0      # Minimum % change to flag as major
DEFAULT_LOOKBACK_DAYS=365     # How far back to fetch prices
OPENAI_MAX_WORKERS=5          # Concurrent API calls for scoring
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                          │
├─────────────────────────────────────────────────────────────────┤
│  /symbols/sync     - Fetch popular tickers from MASSIVE        │
│  /symbols/{}/refresh - Async refresh pipeline (returns job_id) │
│  /jobs/{}          - Poll job status                            │
│  /tickers/{}/analysis - Get movements + explanations           │
│  /chat             - Natural language queries                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Async Refresh Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│  1. Fetch company profile (MASSIVE)                             │
│  2. Fetch price history (MASSIVE)                               │
│  3. Detect major movements (≥2% days)                           │
│  4. Fetch news around movement dates (MASSIVE + NewsAPI)        │
│  5. Score events with OpenAI (parallel batches)                 │
│  6. Create movement-event attributions                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PostgreSQL                               │
├─────────────────────────────────────────────────────────────────┤
│  symbols              - Tracked tickers                         │
│  company_profiles     - Company metadata                        │
│  price_bars           - Daily OHLCV data                        │
│  price_movements      - Detected movements (major/minor)        │
│  news_events          - News articles                           │
│  event_symbol_scores  - Correlation scores (event↔symbol)       │
│  movement_event_attributions - Links movements to events        │
│  jobs                 - Async job tracking                      │
└─────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Correlation Tiers

| Tier | Score | Description |
|------|-------|-------------|
| **High** | ≥0.70 | Direct company news - earnings, lawsuits, product launches |
| **Medium** | 0.35-0.70 | Competitor news, industry trends, supply chain |
| **Low** | <0.35 | Macro/political - Fed rates, geopolitics |

### Attribution Labels

Each major movement includes ranked explanations:

- **Primary**: Top 1-3 directly related events (main drivers)
- **Supporting**: Industry/competitor context
- **Indirect**: Macro factors worth noting

### Event↔Symbol Decoupling

News events are stored once, then scored per-symbol. This allows:
- One event to affect multiple tickers differently
- Efficient storage (no duplicate articles)
- Per-symbol correlation scoring

## Project Structure

```
app/
├── api/                 # FastAPI endpoints
│   ├── symbols.py       # Sync, refresh, list symbols
│   ├── analysis.py      # Movement analysis
│   ├── chat.py          # Natural language queries
│   ├── jobs.py          # Job status tracking
│   └── health.py        # Health checks
├── clients/             # External API clients
│   ├── polygon_prices.py   # MASSIVE price/profile data
│   ├── massive_client.py   # MASSIVE news
│   └── news_client.py      # NewsAPI (optional secondary source)
├── services/            # Business logic
│   ├── async_refresh.py    # Async job pipeline
│   ├── correlation.py      # OpenAI scoring (parallel)
│   ├── movement.py         # Movement detection
│   ├── analysis.py         # Analysis aggregation
│   └── chat.py             # Chat processing
├── models/              # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── db/                  # Database config
└── config.py            # Settings
```

## Development

```bash
# Run tests
docker exec menton-api-1 python -m pytest tests/ -v

# Run with coverage
docker exec menton-api-1 python -m pytest tests/ --cov=app --cov-report=term-missing

# View logs
docker compose logs -f api

# Reset database
docker compose down -v && docker compose up -d
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/symbols` | List tracked symbols |
| POST | `/api/v1/symbols/sync` | Sync popular symbols from MASSIVE |
| POST | `/api/v1/symbols/{ticker}/refresh` | Add & refresh a symbol |
| GET | `/api/v1/jobs/{job_id}` | Get job status |
| GET | `/api/v1/jobs` | List recent jobs |
| GET | `/api/v1/tickers/{ticker}/analysis` | Get movement analysis |
| POST | `/api/v1/chat` | Ask about stock movements |
| GET | `/health` | Health check |

## Performance

- **Parallel OpenAI calls**: Scores events in concurrent batches (configurable via `OPENAI_MAX_WORKERS`)
- **Async refresh**: Non-blocking job execution with progress tracking
- **Typical refresh time**: 20-60 seconds depending on news volume

## Extending

### Adding a News Source

News clients implement the `NewsClient` protocol in `app/clients/base.py`:

```python
from app.clients.base import NewsClient

class MyNewsClient:
    def fetch_news_for_movements(self, db: Session, ticker: str, **kwargs) -> dict:
        # Fetch news around major movement dates
        # Store events using NewsEvent model
        return {"events_fetched": count}
```

Then register in `app/services/async_refresh.py`.

## License

MIT
