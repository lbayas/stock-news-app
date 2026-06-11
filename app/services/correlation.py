"""
OpenAI-based correlation scoring service.

Scores (news_event, symbol) pairs using LLM with company profile context.
Uses parallel API calls for faster processing.
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from openai import OpenAI

from app.models import (
    NewsEvent,
    CompanyProfile,
    PriceMovement,
    EventSymbolScore,
    MovementEventAttribution,
)
from app.config import get_settings

# US Eastern timezone for market hours
ET = ZoneInfo("America/New_York")


def _get_news_lookback_start(movement_date: date) -> datetime:
    """
    Calculate the start datetime for news lookback based on the movement date.

    Handles weekends and looks back to previous trading day:
    - Monday: looks back to Friday (3 days)
    - Tuesday-Friday: looks back 1 day
    - Saturday/Sunday: shouldn't have movements, but handles gracefully

    Returns datetime at start of day (00:00) in ET timezone.
    """
    weekday = movement_date.weekday()

    if weekday == 0:  # Monday - look back to Friday
        lookback_days = 3
    elif weekday == 6:  # Sunday (shouldn't happen, but handle it)
        lookback_days = 2
    elif weekday == 5:  # Saturday (shouldn't happen)
        lookback_days = 1
    else:  # Tuesday-Friday
        lookback_days = 1

    start_date = movement_date - timedelta(days=lookback_days)
    return datetime.combine(start_date, datetime.min.time(), tzinfo=ET)


def _get_temporal_score(published_at: datetime) -> Decimal:
    """
    Calculate temporal score based on when news was published relative to market hours.

    Converts to ET timezone for accurate market hour comparison.
    - During market hours (9:30-16:00 ET): 0.95
    - Pre/post market (6:00-9:30, 16:00-20:00 ET): 0.80
    - Overnight/weekend: 0.60
    """
    # Convert to ET if timezone-aware, assume ET if naive
    if published_at.tzinfo is None:
        pub_et = published_at.replace(tzinfo=ET)
    else:
        pub_et = published_at.astimezone(ET)

    hour = pub_et.hour
    minute = pub_et.minute
    weekday = pub_et.weekday()

    # Weekend news gets lower score
    if weekday >= 5:
        return Decimal("0.60")

    # Market hours: 9:30 AM - 4:00 PM ET
    if (hour == 9 and minute >= 30) or (10 <= hour < 16):
        return Decimal("0.95")
    # Pre-market: 6:00 AM - 9:30 AM ET
    elif 6 <= hour < 9 or (hour == 9 and minute < 30):
        return Decimal("0.80")
    # Post-market: 4:00 PM - 8:00 PM ET
    elif 16 <= hour < 20:
        return Decimal("0.80")
    # Overnight
    else:
        return Decimal("0.60")


def _get_tier_from_score(score: float) -> str:
    """Convert numeric score to tier label."""
    if score >= 0.70:
        return "high"
    elif score >= 0.35:
        return "medium"
    else:
        return "low"


def score_events_for_symbol(db: Session, ticker: str) -> dict:
    """
    Score all unscored news events for a symbol using OpenAI.

    For each major movement:
    1. Find news events from (date - 1 day) to (date)
    2. Score each event against the symbol using LLM
    3. Store scores in event_symbol_scores table
    """
    settings = get_settings()

    if not settings.openai_api_key:
        return {"events_scored": 0, "error": "OPENAI_API_KEY not configured"}

    # Get company profile for context
    profile = db.query(CompanyProfile).filter(CompanyProfile.symbol == ticker).first()
    if not profile:
        return {"events_scored": 0, "error": "Company profile not found"}

    # Get major movements
    movements = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .order_by(PriceMovement.date.desc())
        .limit(10)
        .all()
    )

    if not movements:
        return {"events_scored": 0, "error": "No major movements found"}

    # Collect events around movement dates that haven't been scored yet
    events_to_score = []
    for movement in movements:
        # Use smart lookback that handles weekends
        from_dt = _get_news_lookback_start(movement.date)
        to_dt = datetime.combine(movement.date, datetime.max.time(), tzinfo=ET)

        # Find events in this window that aren't already scored for this symbol
        events = (
            db.query(NewsEvent)
            .outerjoin(
                EventSymbolScore,
                (EventSymbolScore.event_id == NewsEvent.id)
                & (EventSymbolScore.symbol == ticker),
            )
            .filter(NewsEvent.published_at >= from_dt)
            .filter(NewsEvent.published_at <= to_dt)
            .filter(EventSymbolScore.id == None)  # Not yet scored
            .all()
        )
        events_to_score.extend(events)

    # Dedupe
    events_to_score = list({e.id: e for e in events_to_score}.values())

    if not events_to_score:
        return {"events_scored": 0, "message": "All events already scored"}

    # Build company context
    profile_json = profile.profile_json or {}
    company_context = f"""
Company: {profile.name} ({ticker})
Sector: {profile.sector or 'Unknown'}
Industry: {profile.industry or 'Unknown'}
Aliases: {', '.join(profile_json.get('aliases', []))}
Key Products: {', '.join(profile_json.get('key_products', []))}
Competitors: {', '.join(profile_json.get('competitors', []))}
Themes: {', '.join(profile_json.get('themes', []))}
""".strip()

    client = OpenAI(api_key=settings.openai_api_key)
    errors = []
    all_score_records = []

    # Score events in batches using parallel API calls
    batch_size = 15
    max_workers = settings.openai_max_workers

    def score_batch(batch_index: int, batch: list) -> list:
        """Score a single batch of events. Returns list of score records."""
        events_text = "\n\n".join(
            f"EVENT {j+1}:\nTitle: {e.title}\nSource: {e.source}\nSummary: {e.summary or 'N/A'}"
            for j, e in enumerate(batch)
        )

        prompt = f"""You are a financial analyst. Score how relevant each news event is to the stock {ticker}.

COMPANY CONTEXT:
{company_context}

NEWS EVENTS:
{events_text}

SCORING CRITERIA:
- HIGH (0.70-1.00): Direct company news - earnings, lawsuits, product launches, exec changes, direct regulatory action
- MEDIUM (0.35-0.69): Competitor news, industry trends, supply chain, indirect regulatory
- LOW (0.00-0.34): Macro/political - Fed rates, geopolitics, broad market moves

For each event, respond with a JSON array of objects:
[
  {{"event_number": 1, "score": 0.85, "rationale": "One sentence explanation"}},
  ...
]

Only respond with the JSON array, no other text."""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response - handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            scores = json.loads(content)
            records = []

            for score_data in scores:
                event_num = score_data.get("event_number", 0) - 1
                if 0 <= event_num < len(batch):
                    event = batch[event_num]
                    score_value = float(score_data.get("score", 0))
                    rationale = score_data.get("rationale", "")

                    records.append({
                        "event_id": event.id,
                        "symbol": ticker,
                        "correlation_score": Decimal(str(round(score_value, 4))),
                        "correlation_tier": _get_tier_from_score(score_value),
                        "rationale": rationale[:500],
                        "confidence": Decimal("0.90"),
                        "scored_at": datetime.utcnow(),
                    })

            return records

        except json.JSONDecodeError as e:
            return [{"error": f"JSON parse error (batch {batch_index}): {str(e)}"}]
        except Exception as e:
            return [{"error": f"OpenAI error (batch {batch_index}): {str(e)}"}]

    # Create batches
    batches = [
        (i // batch_size, events_to_score[i : i + batch_size])
        for i in range(0, len(events_to_score), batch_size)
    ]

    # Process batches in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(score_batch, batch_idx, batch): batch_idx
            for batch_idx, batch in batches
        }

        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                results = future.result()
                for record in results:
                    if "error" in record:
                        errors.append(record["error"])
                    else:
                        all_score_records.append(record)
            except Exception as e:
                errors.append(f"Batch {batch_idx} failed: {str(e)}")

    # Insert all scores into database
    events_scored = 0
    for record in all_score_records:
        stmt = insert(EventSymbolScore).values(**record)
        stmt = stmt.on_conflict_do_nothing(index_elements=["event_id", "symbol"])
        db.execute(stmt)
        events_scored += 1

    db.commit()

    result = {"events_scored": events_scored}
    if errors:
        result["errors"] = errors

    return result


def create_movement_attributions(db: Session, ticker: str) -> dict:
    """
    Create movement-event attributions based on scores and temporal proximity.

    For each major movement:
    1. Find scored events from the same day
    2. Rank by correlation_score
    3. Label as primary (top 2), supporting (next 3), indirect (rest)
    """
    movements = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .all()
    )

    attributions_created = 0

    for movement in movements:
        # Use smart lookback that handles weekends
        from_dt = _get_news_lookback_start(movement.date)
        to_dt = datetime.combine(movement.date, datetime.max.time(), tzinfo=ET)

        scored_events = (
            db.query(NewsEvent, EventSymbolScore)
            .join(EventSymbolScore, EventSymbolScore.event_id == NewsEvent.id)
            .filter(EventSymbolScore.symbol == ticker)
            .filter(NewsEvent.published_at >= from_dt)
            .filter(NewsEvent.published_at <= to_dt)
            .order_by(EventSymbolScore.correlation_score.desc())
            .all()
        )

        for rank, (event, score) in enumerate(scored_events, 1):
            # Determine label based on rank and score
            if rank <= 2 and float(score.correlation_score) >= 0.70:
                label = "primary"
            elif rank <= 5 and float(score.correlation_score) >= 0.35:
                label = "supporting"
            else:
                label = "indirect"

            # Calculate temporal score with proper timezone handling
            temporal = _get_temporal_score(event.published_at)

            attr_data = {
                "movement_id": movement.id,
                "event_id": event.id,
                "symbol": ticker,
                "impact_rank": rank,
                "temporal_score": temporal,
                "attribution_label": label,
            }

            stmt = insert(MovementEventAttribution).values(**attr_data)
            stmt = stmt.on_conflict_do_nothing(index_elements=["movement_id", "event_id"])
            result = db.execute(stmt)

            if result.rowcount > 0:
                attributions_created += 1

    db.commit()

    return {"attributions_created": attributions_created}
