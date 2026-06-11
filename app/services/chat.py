"""
Chat service with OpenAI-powered natural language responses.
"""
from sqlalchemy.orm import Session
from datetime import date, timedelta
from openai import OpenAI

from app.models import CompanyProfile, PriceMovement, MovementEventAttribution
from app.models import EventSymbolScore, NewsEvent
from app.schemas import ChatResponse
from app.config import get_settings


def process_chat_message(
    db: Session, ticker: str, message: str, filters: dict | None
) -> ChatResponse:
    """
    Process a chat message about a ticker using OpenAI.

    Flow:
    1. Retrieve movements + top attributions from Postgres
    2. Build structured context
    3. Use OpenAI to generate natural language response
    4. Return response with source citations
    """
    settings = get_settings()

    # Default filters
    if filters is None:
        filters = {}

    end_date = filters.get("end_date") or date.today()
    start_date = filters.get("start_date") or (end_date - timedelta(days=365))

    # Get company context
    profile = db.query(CompanyProfile).filter(CompanyProfile.symbol == ticker).first()
    company_name = profile.name if profile else ticker

    # Get major movements in date range
    movements = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .filter(PriceMovement.date >= start_date)
        .filter(PriceMovement.date <= end_date)
        .order_by(PriceMovement.date.desc())
        .limit(10)
        .all()
    )

    # Build context from movements and their attributions
    context_parts = []
    sources = []

    for movement in movements:
        movement_info = {
            "date": str(movement.date),
            "pct_change": f"{float(movement.pct_change):+.2f}%",
            "direction": movement.direction,
            "volume": movement.volume,
            "events": [],
        }

        # Get top attributions
        attributions = (
            db.query(MovementEventAttribution, EventSymbolScore, NewsEvent)
            .join(NewsEvent, MovementEventAttribution.event_id == NewsEvent.id)
            .join(
                EventSymbolScore,
                (EventSymbolScore.event_id == NewsEvent.id)
                & (EventSymbolScore.symbol == movement.symbol),
            )
            .filter(MovementEventAttribution.movement_id == movement.id)
            .filter(MovementEventAttribution.attribution_label.in_(["primary", "supporting"]))
            .order_by(MovementEventAttribution.impact_rank)
            .limit(5)
            .all()
        )

        for attr, score, event in attributions:
            movement_info["events"].append({
                "title": event.title,
                "source": event.source,
                "score": float(score.correlation_score),
                "rationale": score.rationale,
                "published_at": event.published_at.strftime("%Y-%m-%d %H:%M"),
            })
            sources.append({
                "title": event.title,
                "url": event.url,
                "source": event.source,
                "published_at": event.published_at,
                "correlation_score": float(score.correlation_score),
                "correlation_tier": score.correlation_tier,
            })

        context_parts.append(movement_info)

    # If no data, return helpful message
    if not movements:
        response_text = (
            f"I don't have data about major movements for {company_name} ({ticker}) "
            f"in the specified date range ({start_date} to {end_date}). "
            f"Try running a refresh first with POST /api/v1/symbols/{ticker}/refresh"
        )
        return ChatResponse(
            ticker=ticker,
            message=message,
            response=response_text,
            sources=[],
        )

    # Use OpenAI for natural language response if API key is configured
    if settings.openai_api_key:
        response_text = _generate_llm_response(
            settings.openai_api_key,
            ticker,
            company_name,
            message,
            context_parts,
            start_date,
            end_date,
        )
    else:
        # Fallback to structured response
        response_text = _generate_structured_response(
            ticker, company_name, context_parts
        )

    return ChatResponse(
        ticker=ticker,
        message=message,
        response=response_text,
        sources=sources,
    )


def _generate_llm_response(
    api_key: str,
    ticker: str,
    company_name: str,
    user_message: str,
    context: list[dict],
    start_date: date,
    end_date: date,
) -> str:
    """Generate a natural language response using OpenAI."""
    client = OpenAI(api_key=api_key)

    # Build context string
    context_str = ""
    for m in context:
        context_str += f"\n{m['date']}: {ticker} moved {m['pct_change']} ({m['direction']})"
        if m["events"]:
            context_str += "\n  Related news:"
            for e in m["events"]:
                context_str += f"\n  - {e['title']} (Source: {e['source']}, Score: {e['score']:.2f})"
                if e["rationale"]:
                    context_str += f"\n    Rationale: {e['rationale']}"

    system_prompt = f"""You are a financial analyst assistant helping users understand stock price movements.

You have access to data about {company_name} ({ticker}) major price movements from {start_date} to {end_date}.

AVAILABLE DATA:
{context_str}

INSTRUCTIONS:
1. Answer the user's question based ONLY on the provided data
2. If the data doesn't contain relevant information, say so honestly
3. Always cite specific dates and news events when explaining movements
4. Be concise but informative
5. If asked about something outside your data, explain what data you do have
6. Never make up information not in the provided context"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        # Fallback to structured response on error
        return f"Error generating response: {str(e)}\n\n" + _generate_structured_response(
            ticker, company_name, context
        )


def _generate_structured_response(
    ticker: str, company_name: str, context: list[dict]
) -> str:
    """Generate a structured response without LLM."""
    parts = [f"Here's what I found about {company_name} ({ticker}):\n"]

    for m in context:
        parts.append(f"\n**{m['date']}**: {ticker} moved {m['pct_change']} ({m['direction']})")
        if m["events"]:
            parts.append("\nRelated news:")
            for e in m["events"]:
                parts.append(f"- {e['title']} (Score: {e['score']:.2f})")

    if not any(m["events"] for m in context):
        parts.append(
            "\n\nNote: No news attributions found yet. "
            "Run a refresh to fetch and correlate news events."
        )

    return "".join(parts)
