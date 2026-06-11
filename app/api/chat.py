from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Symbol
from app.schemas import ChatRequest, ChatResponse
from app.services.chat import process_chat_message

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat about stock movements",
    description="""
Ask natural language questions about a stock's price movements and the news that may have caused them.

**Example questions:**
- "Why did AAPL drop on May 2, 2024?"
- "What major events affected the stock last quarter?"
- "Explain the biggest movements this year"

**How it works:**
1. Parses your question for intent (dates, direction)
2. Retrieves relevant movements and their news attributions from the database
3. Builds context from correlated events
4. Returns a grounded response with source citations

**Note:** Responses are grounded in stored data. Run `/symbols/{ticker}/refresh` first to ensure data is available.
    """,
    response_description="Chat response with sources",
)
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    ticker = request.ticker.upper()
    symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not symbol:
        raise HTTPException(status_code=404, detail=f"Symbol {ticker} not found")

    # Convert Pydantic model to dict for service
    filters_dict = request.filters.model_dump() if request.filters else None
    response = process_chat_message(db, ticker, request.message, filters_dict)
    return response
