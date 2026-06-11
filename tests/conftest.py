import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from datetime import datetime, date
from decimal import Decimal

from app.db.base import Base
from app.db import get_db
from app.main import app
from app.models import (
    Symbol,
    CompanyProfile,
    PriceBar,
    PriceMovement,
    NewsEvent,
    EventSymbolScore,
    MovementEventAttribution,
    Job,
)

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database dependency override."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_symbol(db_session):
    """Create a sample symbol."""
    symbol = Symbol(ticker="AAPL", is_active=True)
    db_session.add(symbol)
    db_session.commit()
    return symbol


@pytest.fixture
def sample_company_profile(db_session, sample_symbol):
    """Create a sample company profile."""
    profile = CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        profile_json={
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "aliases": ["Apple"],
            "sector": "Technology",
            "industry": "Consumer Electronics",
        },
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def sample_price_bars(db_session, sample_symbol):
    """Create sample price bars with a major movement."""
    bars = [
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 1),
            open=Decimal("180.00"),
            high=Decimal("182.00"),
            low=Decimal("179.00"),
            close=Decimal("181.00"),
            volume=1000000,
        ),
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 2),
            open=Decimal("181.00"),
            high=Decimal("190.00"),
            low=Decimal("180.00"),
            close=Decimal("188.00"),  # +3.87% - major movement
            volume=2000000,
        ),
        PriceBar(
            symbol="AAPL",
            date=date(2024, 1, 3),
            open=Decimal("188.00"),
            high=Decimal("189.00"),
            low=Decimal("187.00"),
            close=Decimal("188.50"),  # +0.27% - not major
            volume=1500000,
        ),
    ]
    db_session.add_all(bars)
    db_session.commit()
    return bars


@pytest.fixture
def sample_movement(db_session, sample_symbol):
    """Create a sample major movement."""
    movement = PriceMovement(
        symbol="AAPL",
        date=date(2024, 1, 2),
        pct_change=Decimal("3.87"),
        direction="up",
        is_major=True,
        prev_close=Decimal("181.00"),
        close=Decimal("188.00"),
        volume=2000000,
    )
    db_session.add(movement)
    db_session.commit()
    return movement


@pytest.fixture
def sample_news_event(db_session):
    """Create a sample news event."""
    event = NewsEvent(
        published_at=datetime(2024, 1, 2, 10, 30, 0),
        title="Apple announces record iPhone sales",
        url="https://example.com/apple-iphone-sales",
        source="Reuters",
        summary="Apple reported record-breaking iPhone sales for Q4.",
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def sample_event_score(db_session, sample_symbol, sample_news_event):
    """Create a sample event-symbol correlation score."""
    score = EventSymbolScore(
        event_id=sample_news_event.id,
        symbol="AAPL",
        correlation_score=Decimal("0.92"),
        correlation_tier="high",
        rationale="Direct company news about iPhone sales performance.",
        confidence=Decimal("0.95"),
    )
    db_session.add(score)
    db_session.commit()
    return score


@pytest.fixture
def sample_attribution(db_session, sample_movement, sample_news_event):
    """Create a sample movement-event attribution."""
    attribution = MovementEventAttribution(
        movement_id=sample_movement.id,
        event_id=sample_news_event.id,
        symbol="AAPL",
        impact_rank=1,
        temporal_score=Decimal("0.95"),
        attribution_label="primary",
    )
    db_session.add(attribution)
    db_session.commit()
    return attribution
