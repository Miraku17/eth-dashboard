from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Candle, CandlesResponse, Timeframe
from app.core.cache import cached_json_get, cached_json_set
from app.core.db import get_session
from app.core.models import PriceCandle

router = APIRouter(prefix="/price", tags=["price"])

DEFAULT_SYMBOL = "ETHUSDT"
CANDLES_CACHE_TTL_S = 60


@router.get("/candles", response_model=CandlesResponse)
def get_candles(
    session: Annotated[Session, Depends(get_session)],
    timeframe: Timeframe = "1h",
    limit: int = Query(500, ge=1, le=2000),
    symbol: str = DEFAULT_SYMBOL,
) -> CandlesResponse:
    cache_key = f"candles:{symbol}:{timeframe}:{limit}"
    cached = cached_json_get(cache_key)
    if cached is not None:
        return CandlesResponse.model_validate(cached)

    rows = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == symbol, PriceCandle.timeframe == timeframe)
        .order_by(PriceCandle.ts.desc())
        .limit(limit)
    ).scalars().all()

    rows = list(reversed(rows))

    response = CandlesResponse(
        symbol=symbol,
        timeframe=timeframe,
        candles=[
            Candle(
                time=int(r.ts.timestamp()),
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume),
            )
            for r in rows
        ],
    )
    cached_json_set(cache_key, response.model_dump(mode="json"), CANDLES_CACHE_TTL_S)
    return response
