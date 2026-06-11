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

## Key Endpoints

These are the two primary interfaces for consuming Menton data. Run a refresh first (`POST /api/v1/symbols/{ticker}/refresh`) so price, news, and correlation data is available.

### 1. Stock + news analysis

**`GET /api/v1/tickers/{ticker}/analysis`**

Returns major price movements for a ticker with correlated news explanations grouped as **primary**, **supporting**, and **indirect**.

| Filter | Description |
|--------|-------------|
| `start_date` / `end_date` | Date range (default: last 7 days) |
| `min_move_pct` | Minimum % change to include (default: `2.0`) |
| `direction` | `up` or `down` |
| `min_correlation_score` | Minimum event correlation (0.0–1.0) |
| `correlation_tier` | `high`, `medium`, or `low` |
| `include_prices` | Include period price summary (`true`/`false`) |

```bash
curl "http://localhost:8000/api/v1/tickers/META/analysis?start_date=2026-06-01&end_date=2026-06-11&include_prices=true"
```

**Swagger:** [Analysis endpoint](http://localhost:8000/docs#/analysis/get_analysis_api_v1_tickers__ticker__analysis_get)

### 2. Chat

**`POST /api/v1/chat`**

Ask natural language questions about a ticker's movements and the news that may have caused them. Responses are grounded in stored data and include source citations with correlation scores.

| Field | Description |
|-------|-------------|
| `ticker` | Stock symbol (required) |
| `message` | Your question (required) |
| `filters.start_date` / `filters.end_date` | Optional date range (default: last 365 days) |

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "META", "message": "Why did the stock drop recently?"}'
```

**Swagger:** [Chat endpoint](http://localhost:8000/docs#/chat/chat_api_v1_chat_post)

## API Documentation (Swagger)

Interactive API docs are available when the server is running:

| UI | URL |
|----|-----|
| **Swagger UI** | http://localhost:8000/docs |
| **ReDoc** | http://localhost:8000/redoc |
| **OpenAPI JSON** | http://localhost:8000/openapi.json |

Use Swagger to try requests, inspect request/response schemas, and view example payloads.

## Bootstrap

From scratch — get the API running and load data before using [Key Endpoints](#key-endpoints):

```bash
# 1. Clone and configure
git clone https://github.com/lbayas/stock-news-app.git
cd stock-news-app
cp .env.example .env
# Set MASSIVE_API_KEY and OPENAI_API_KEY in .env

# 2. Start services (Postgres + API; runs Alembic migrations automatically)
docker compose up -d --build

# 3. Verify the API is up
curl http://localhost:8000/health

# 4. Sync popular symbols from MASSIVE
curl -X POST http://localhost:8000/api/v1/symbols/sync

# 5. Refresh a ticker — async; returns a job_id
curl -X POST http://localhost:8000/api/v1/symbols/META/refresh
# → {"job_id":"...", "status":"pending", ...}

# 6. Poll job status until status is "completed" (typically 20–60 seconds)
curl http://localhost:8000/api/v1/jobs/{job_id}

# 7. Get analysis
curl "http://localhost:8000/api/v1/tickers/META/analysis?start_date=2026-06-01&end_date=2026-06-11"

# 8. Ask questions via chat
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"ticker": "META", "message": "Why did the stock drop recently?"}'
```

Open http://localhost:8000/docs to explore all endpoints interactively.

> **Note:** Refresh is async — analysis and chat return empty or unhelpful results until the job in step 6 completes.
>
> **Port conflict:** If `docker compose up` fails because port 5432 is in use, stop the other Postgres instance or change the host port mapping in `docker-compose.yml`.

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
# Run tests (inside the api container)
docker compose exec api python -m pytest tests/ -v

# Run with coverage
docker compose exec api python -m pytest tests/ --cov=app --cov-report=term-missing

# View logs
docker compose logs -f api

# Reset database
docker compose down -v && docker compose up -d
```

## API Endpoints

See **[Key Endpoints](#key-endpoints)** for the primary analysis and chat APIs. Full reference:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/symbols` | List tracked symbols |
| POST | `/api/v1/symbols/sync` | Sync popular symbols from MASSIVE |
| POST | `/api/v1/symbols/{ticker}/refresh` | Add & refresh a symbol |
| GET | `/api/v1/jobs/{job_id}` | Get job status |
| GET | `/api/v1/jobs` | List recent jobs |
| **GET** | **`/api/v1/tickers/{ticker}/analysis`** | **Get movements + news explanations** |
| **POST** | **`/api/v1/chat`** | **Ask about stock movements** |
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
