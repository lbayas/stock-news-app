from sqlalchemy.orm import Session
from datetime import date

from app.models import CompanyProfile, PriceBar, PriceMovement, MovementEventAttribution
from app.models import EventSymbolScore, NewsEvent
from app.schemas import (
    AnalysisResponse,
    CompanySummary,
    PriceSummary,
    MajorMovement,
    Explanations,
    EventExplanation,
)


def get_ticker_analysis(db: Session, ticker: str, filters: dict) -> AnalysisResponse:
    """
    Build analysis response for a ticker with applied filters.
    """
    # Get company profile
    profile = db.query(CompanyProfile).filter(CompanyProfile.symbol == ticker).first()
    company = None
    if profile:
        company = CompanySummary(
            name=profile.name,
            sector=profile.sector,
            industry=profile.industry,
        )

    # Get price summary if requested
    price_summary = None
    if filters.get("include_prices"):
        price_summary = _get_price_summary(
            db, ticker, filters["start_date"], filters["end_date"]
        )

    # Get major movements
    movements_query = (
        db.query(PriceMovement)
        .filter(PriceMovement.symbol == ticker)
        .filter(PriceMovement.is_major == True)
        .filter(PriceMovement.date >= filters["start_date"])
        .filter(PriceMovement.date <= filters["end_date"])
    )

    # Apply min_move_pct filter
    min_move = filters.get("min_move_pct", 2.0)
    movements_query = movements_query.filter(
        (PriceMovement.pct_change >= min_move) | (PriceMovement.pct_change <= -min_move)
    )

    # Apply direction filter
    if filters.get("direction"):
        movements_query = movements_query.filter(
            PriceMovement.direction == filters["direction"]
        )

    movements = movements_query.order_by(PriceMovement.date.desc()).all()

    # Build response
    major_movements = []
    for movement in movements:
        explanations = _get_movement_explanations(db, movement, filters)
        major_movements.append(
            MajorMovement(
                date=movement.date,
                pct_change=float(movement.pct_change),
                direction=movement.direction,
                volume=movement.volume,
                explanations=explanations,
            )
        )

    return AnalysisResponse(
        ticker=ticker,
        company=company,
        filters_applied={k: str(v) if isinstance(v, date) else v for k, v in filters.items()},
        price_summary=price_summary,
        major_movements=major_movements,
    )


def _get_price_summary(
    db: Session, ticker: str, start_date: date, end_date: date
) -> PriceSummary | None:
    """Get price summary for date range."""
    start_bar = (
        db.query(PriceBar)
        .filter(PriceBar.symbol == ticker)
        .filter(PriceBar.date >= start_date)
        .order_by(PriceBar.date)
        .first()
    )

    end_bar = (
        db.query(PriceBar)
        .filter(PriceBar.symbol == ticker)
        .filter(PriceBar.date <= end_date)
        .order_by(PriceBar.date.desc())
        .first()
    )

    if not start_bar or not end_bar:
        return None

    start_close = float(start_bar.close)
    end_close = float(end_bar.close)
    total_return = ((end_close - start_close) / start_close) * 100 if start_close else 0

    return PriceSummary(
        start_date=start_bar.date,
        end_date=end_bar.date,
        start_close=start_close,
        end_close=end_close,
        total_return_pct=round(total_return, 2),
    )


def _get_movement_explanations(
    db: Session, movement: PriceMovement, filters: dict
) -> Explanations:
    """Get explanations for a movement, grouped by tier."""
    # Query attributions for this movement
    attributions = (
        db.query(MovementEventAttribution, EventSymbolScore, NewsEvent)
        .join(NewsEvent, MovementEventAttribution.event_id == NewsEvent.id)
        .join(
            EventSymbolScore,
            (EventSymbolScore.event_id == NewsEvent.id)
            & (EventSymbolScore.symbol == movement.symbol),
        )
        .filter(MovementEventAttribution.movement_id == movement.id)
        .order_by(MovementEventAttribution.impact_rank)
        .all()
    )

    primary = []
    supporting = []
    indirect = []

    for attribution, score, event in attributions:
        # Apply correlation filters
        if filters.get("min_correlation_score"):
            if float(score.correlation_score) < filters["min_correlation_score"]:
                continue
        if filters.get("correlation_tier"):
            if score.correlation_tier != filters["correlation_tier"]:
                continue

        explanation = EventExplanation(
            title=event.title,
            url=event.url,
            source=event.source,
            published_at=event.published_at,
            correlation_score=float(score.correlation_score),
            correlation_tier=score.correlation_tier,
            rationale=score.rationale,
        )

        if attribution.attribution_label == "primary":
            primary.append(explanation)
        elif attribution.attribution_label == "supporting":
            supporting.append(explanation)
        else:
            indirect.append(explanation)

    return Explanations(
        primary=primary,
        supporting=supporting,
        indirect=indirect,
    )
