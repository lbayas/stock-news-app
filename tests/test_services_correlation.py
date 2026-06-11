"""Tests for correlation scoring service."""
import pytest
from datetime import datetime, timedelta, date
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo

from app.services.correlation import (
    _get_tier_from_score,
    _get_news_lookback_start,
    _get_temporal_score,
    score_events_for_symbol,
    create_movement_attributions,
    ET,
)
from app.models import (
    Symbol,
    CompanyProfile,
    PriceMovement,
    NewsEvent,
    EventSymbolScore,
    MovementEventAttribution,
)


class TestGetTierFromScore:
    """Tests for tier classification."""

    def test_high_tier(self):
        assert _get_tier_from_score(1.0) == "high"
        assert _get_tier_from_score(0.85) == "high"
        assert _get_tier_from_score(0.70) == "high"

    def test_medium_tier(self):
        assert _get_tier_from_score(0.69) == "medium"
        assert _get_tier_from_score(0.50) == "medium"
        assert _get_tier_from_score(0.35) == "medium"

    def test_low_tier(self):
        assert _get_tier_from_score(0.34) == "low"
        assert _get_tier_from_score(0.10) == "low"
        assert _get_tier_from_score(0.0) == "low"


class TestNewsLookbackStart:
    """Tests for weekend/holiday-aware news lookback."""

    def test_monday_looks_back_to_friday(self):
        """Monday movements should look back to Friday (3 days)."""
        # Monday, Jan 6, 2025
        monday = date(2025, 1, 6)
        result = _get_news_lookback_start(monday)
        # Should be Friday, Jan 3
        assert result.date() == date(2025, 1, 3)
        assert result.hour == 0
        assert result.minute == 0

    def test_tuesday_looks_back_one_day(self):
        """Tuesday movements should look back 1 day."""
        tuesday = date(2025, 1, 7)
        result = _get_news_lookback_start(tuesday)
        assert result.date() == date(2025, 1, 6)

    def test_wednesday_looks_back_one_day(self):
        """Wednesday movements should look back 1 day."""
        wednesday = date(2025, 1, 8)
        result = _get_news_lookback_start(wednesday)
        assert result.date() == date(2025, 1, 7)

    def test_friday_looks_back_one_day(self):
        """Friday movements should look back to Thursday."""
        friday = date(2025, 1, 10)
        result = _get_news_lookback_start(friday)
        assert result.date() == date(2025, 1, 9)

    def test_returns_timezone_aware(self):
        """Result should be timezone-aware (ET)."""
        monday = date(2025, 1, 6)
        result = _get_news_lookback_start(monday)
        assert result.tzinfo is not None
        assert result.tzinfo == ET


class TestTemporalScore:
    """Tests for timezone-aware temporal scoring."""

    def test_market_hours_high_score(self):
        """News during market hours (9:30-16:00 ET) gets 0.95."""
        # 10:00 AM ET on a Tuesday
        pub_time = datetime(2025, 1, 7, 10, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.95")

        # 3:30 PM ET
        pub_time = datetime(2025, 1, 7, 15, 30, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.95")

    def test_market_open_boundary(self):
        """9:30 AM ET is market hours, 9:29 AM is pre-market."""
        # 9:30 AM - market hours
        pub_time = datetime(2025, 1, 7, 9, 30, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.95")

        # 9:29 AM - pre-market
        pub_time = datetime(2025, 1, 7, 9, 29, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.80")

    def test_pre_market_medium_score(self):
        """Pre-market news (6:00-9:30 ET) gets 0.80."""
        # 7:00 AM ET
        pub_time = datetime(2025, 1, 7, 7, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.80")

    def test_post_market_medium_score(self):
        """Post-market news (16:00-20:00 ET) gets 0.80."""
        # 5:00 PM ET (after-hours earnings release)
        pub_time = datetime(2025, 1, 7, 17, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.80")

    def test_overnight_low_score(self):
        """Overnight news gets 0.60."""
        # 2:00 AM ET
        pub_time = datetime(2025, 1, 7, 2, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.60")

        # 10:00 PM ET
        pub_time = datetime(2025, 1, 7, 22, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.60")

    def test_weekend_low_score(self):
        """Weekend news always gets 0.60 regardless of time."""
        # Saturday at noon
        pub_time = datetime(2025, 1, 11, 12, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.60")

        # Sunday morning
        pub_time = datetime(2025, 1, 12, 9, 0, tzinfo=ET)
        assert _get_temporal_score(pub_time) == Decimal("0.60")

    def test_utc_timezone_converted(self):
        """UTC times should be converted to ET correctly."""
        # 3:00 PM UTC = 10:00 AM ET (during winter, ET is UTC-5)
        pub_time = datetime(2025, 1, 7, 15, 0, tzinfo=ZoneInfo("UTC"))
        # 10 AM ET is market hours
        assert _get_temporal_score(pub_time) == Decimal("0.95")

    def test_naive_datetime_assumed_et(self):
        """Naive datetimes should be treated as ET."""
        # 10:00 AM (no timezone) - assume ET
        pub_time = datetime(2025, 1, 7, 10, 0)
        assert _get_temporal_score(pub_time) == Decimal("0.95")


class TestScoreEventsForSymbol:
    """Tests for OpenAI-based event scoring."""

    def test_no_api_key(self, db_session):
        """Test returns error when API key not configured."""
        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = ""
            result = score_events_for_symbol(db_session, "TEST")
            assert result["events_scored"] == 0
            assert "not configured" in result["error"]

    def test_no_company_profile(self, db_session):
        """Test returns error when company profile not found."""
        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            result = score_events_for_symbol(db_session, "UNKNOWN")
            assert result["events_scored"] == 0
            assert "profile not found" in result["error"].lower()

    def test_no_major_movements(self, db_session):
        """Test returns error when no major movements exist."""
        # Create symbol and profile but no movements
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        db_session.add_all([symbol, profile])
        db_session.commit()

        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            result = score_events_for_symbol(db_session, "TEST")
            assert result["events_scored"] == 0
            assert "no major movements" in result["error"].lower()

    def test_all_events_already_scored(self, db_session):
        """Test returns message when all events already scored."""
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, profile, movement])
        db_session.commit()

        # No events in the window = nothing to score
        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            result = score_events_for_symbol(db_session, "TEST")
            assert result["events_scored"] == 0
            assert "already scored" in result.get("message", "")

    def test_score_events_success(self, db_session):
        """Test successful event scoring with mocked OpenAI."""
        # Setup test data
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(
            symbol="TEST",
            name="Test Corp",
            sector="Technology",
            industry="Software",
            profile_json={"aliases": ["TC"], "key_products": ["TestApp"]},
        )
        movement_date = datetime.utcnow().date()
        movement = PriceMovement(
            symbol="TEST",
            date=movement_date,
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test Corp announces new product",
            source="TestNews",
            url="https://example.com/news/score1",
            published_at=datetime.combine(movement_date, datetime.min.time()),
        )
        db_session.add_all([symbol, profile, movement, event])
        db_session.commit()

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content='[{"event_number": 1, "score": 0.85, "rationale": "Direct product news"}]'))
        ]

        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.openai_max_workers = 5
            with patch("app.services.correlation.OpenAI") as mock_openai:
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                result = score_events_for_symbol(db_session, "TEST")

        assert result["events_scored"] == 1
        assert "errors" not in result

        # Verify score was saved
        score = db_session.query(EventSymbolScore).filter_by(symbol="TEST").first()
        assert score is not None
        assert float(score.correlation_score) == 0.85
        assert score.correlation_tier == "high"
        assert score.rationale == "Direct product news"

    def test_score_events_handles_markdown_json(self, db_session):
        """Test handles JSON wrapped in markdown code blocks."""
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test news",
            source="TestNews",
            url="https://example.com/news/markdown2",
            published_at=datetime.utcnow(),
        )
        db_session.add_all([symbol, profile, movement, event])
        db_session.commit()

        # Mock response with markdown code block
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content='```json\n[{"event_number": 1, "score": 0.50, "rationale": "Industry news"}]\n```'))
        ]

        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.openai_max_workers = 5
            with patch("app.services.correlation.OpenAI") as mock_openai:
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                result = score_events_for_symbol(db_session, "TEST")

        assert result["events_scored"] == 1
        score = db_session.query(EventSymbolScore).filter_by(symbol="TEST").first()
        assert float(score.correlation_score) == 0.50
        assert score.correlation_tier == "medium"

    def test_score_events_handles_json_error(self, db_session):
        """Test handles invalid JSON response gracefully."""
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test news",
            source="TestNews",
            url="https://example.com/news/jsonerr3",
            published_at=datetime.utcnow(),
        )
        db_session.add_all([symbol, profile, movement, event])
        db_session.commit()

        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="This is not valid JSON"))]

        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.openai_max_workers = 5
            with patch("app.services.correlation.OpenAI") as mock_openai:
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client

                result = score_events_for_symbol(db_session, "TEST")

        assert result["events_scored"] == 0
        assert "errors" in result
        assert any("JSON parse error" in e for e in result["errors"])

    def test_score_events_handles_api_error(self, db_session):
        """Test handles OpenAI API errors gracefully."""
        symbol = Symbol(ticker="TEST", is_active=True)
        profile = CompanyProfile(symbol="TEST", name="Test Corp")
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test news",
            source="TestNews",
            url="https://example.com/news/apierr4",
            published_at=datetime.utcnow(),
        )
        db_session.add_all([symbol, profile, movement, event])
        db_session.commit()

        with patch("app.services.correlation.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.openai_max_workers = 5
            with patch("app.services.correlation.OpenAI") as mock_openai:
                mock_client = Mock()
                mock_client.chat.completions.create.side_effect = Exception("API rate limit exceeded")
                mock_openai.return_value = mock_client

                result = score_events_for_symbol(db_session, "TEST")

        assert result["events_scored"] == 0
        assert "errors" in result
        assert any("OpenAI error" in e for e in result["errors"])


class TestCreateMovementAttributions:
    """Tests for movement-event attribution creation."""

    def test_no_movements(self, db_session):
        """Test returns zero when no movements exist."""
        result = create_movement_attributions(db_session, "UNKNOWN")
        assert result["attributions_created"] == 0

    def test_creates_attributions(self, db_session):
        """Test creates attributions for scored events."""
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test news",
            source="TestNews",
            url="https://example.com/news/attr5",
            published_at=datetime.utcnow(),
        )
        db_session.add_all([symbol, movement, event])
        db_session.commit()

        # Create a score for the event
        score = EventSymbolScore(
            event_id=event.id,
            symbol="TEST",
            correlation_score=Decimal("0.85"),
            correlation_tier="high",
            rationale="Test rationale",
        )
        db_session.add(score)
        db_session.commit()

        result = create_movement_attributions(db_session, "TEST")
        assert result["attributions_created"] == 1

        # Verify attribution
        attr = db_session.query(MovementEventAttribution).first()
        assert attr is not None
        assert attr.symbol == "TEST"
        assert attr.attribution_label == "primary"
        assert attr.impact_rank == 1

    def test_attribution_labels_by_rank_and_score(self, db_session):
        """Test attribution labels are assigned correctly."""
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, movement])
        db_session.commit()

        # Create multiple events with different scores
        events_data = [
            ("High score 1", 0.90, "high"),
            ("High score 2", 0.85, "high"),
            ("Medium score 1", 0.60, "medium"),
            ("Medium score 2", 0.50, "medium"),
            ("Medium score 3", 0.40, "medium"),
            ("Low score", 0.20, "low"),
        ]

        for i, (title, score_val, tier) in enumerate(events_data):
            event = NewsEvent(
                title=title,
                source="TestNews",
                url=f"https://example.com/news/labels{i}",
                published_at=datetime.utcnow(),
            )
            db_session.add(event)
            db_session.commit()

            score = EventSymbolScore(
                event_id=event.id,
                symbol="TEST",
                correlation_score=Decimal(str(score_val)),
                correlation_tier=tier,
            )
            db_session.add(score)

        db_session.commit()

        result = create_movement_attributions(db_session, "TEST")
        assert result["attributions_created"] == 6

        # Check labels
        attrs = db_session.query(MovementEventAttribution).order_by(MovementEventAttribution.impact_rank).all()

        # Rank 1-2 with high scores = primary
        assert attrs[0].attribution_label == "primary"
        assert attrs[1].attribution_label == "primary"
        # Rank 3-5 with medium scores = supporting
        assert attrs[2].attribution_label == "supporting"
        assert attrs[3].attribution_label == "supporting"
        assert attrs[4].attribution_label == "supporting"
        # Rank 6+ = indirect
        assert attrs[5].attribution_label == "indirect"

    def test_temporal_scores(self, db_session):
        """Test temporal scores based on event time."""
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        db_session.add_all([symbol, movement])
        db_session.commit()

        # Event during market hours (10 AM)
        market_event = NewsEvent(
            title="Market hours event",
            source="TestNews",
            url="https://example.com/temporal/market",
            published_at=datetime.combine(movement.date, datetime.min.time().replace(hour=10)),
        )
        # Event early morning (7 AM)
        early_event = NewsEvent(
            title="Early event",
            source="TestNews",
            url="https://example.com/temporal/early",
            published_at=datetime.combine(movement.date, datetime.min.time().replace(hour=7)),
        )
        # Event overnight (2 AM)
        night_event = NewsEvent(
            title="Night event",
            source="TestNews",
            url="https://example.com/temporal/night",
            published_at=datetime.combine(movement.date, datetime.min.time().replace(hour=2)),
        )

        db_session.add_all([market_event, early_event, night_event])
        db_session.commit()

        for event in [market_event, early_event, night_event]:
            score = EventSymbolScore(
                event_id=event.id,
                symbol="TEST",
                correlation_score=Decimal("0.50"),
                correlation_tier="medium",
            )
            db_session.add(score)
        db_session.commit()

        create_movement_attributions(db_session, "TEST")

        attrs = {a.event_id: a for a in db_session.query(MovementEventAttribution).all()}

        # Market hours = 0.95
        assert float(attrs[market_event.id].temporal_score) == 0.95
        # Pre/post market = 0.80
        assert float(attrs[early_event.id].temporal_score) == 0.80
        # Overnight = 0.60
        assert float(attrs[night_event.id].temporal_score) == 0.60

    def test_idempotent_attributions(self, db_session):
        """Test running attributions twice doesn't create duplicates."""
        symbol = Symbol(ticker="TEST", is_active=True)
        movement = PriceMovement(
            symbol="TEST",
            date=datetime.utcnow().date(),
            pct_change=Decimal("5.0"),
            direction="up",
            is_major=True,
            prev_close=Decimal("100.0"),
            close=Decimal("105.0"),
        )
        event = NewsEvent(
            title="Test news",
            source="TestNews",
            url="https://example.com/idem/test",
            published_at=datetime.utcnow(),
        )
        db_session.add_all([symbol, movement, event])
        db_session.commit()

        score = EventSymbolScore(
            event_id=event.id,
            symbol="TEST",
            correlation_score=Decimal("0.85"),
            correlation_tier="high",
        )
        db_session.add(score)
        db_session.commit()

        # Run twice
        result1 = create_movement_attributions(db_session, "TEST")
        result2 = create_movement_attributions(db_session, "TEST")

        assert result1["attributions_created"] == 1
        assert result2["attributions_created"] == 0  # Second run creates nothing

        # Only one attribution exists
        count = db_session.query(MovementEventAttribution).count()
        assert count == 1
