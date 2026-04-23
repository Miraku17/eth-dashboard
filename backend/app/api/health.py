from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import DataSourceStatus, HealthResponse
from app.core.db import get_session
from app.core.models import (
    ExchangeFlow,
    NetworkActivity,
    PriceCandle,
    Transfer,
)

router = APIRouter()

# Threshold (seconds) past which each source is flagged stale.
STALE_S: dict[str, int] = {
    "binance_1m": 120,           # 1m candle sync → stale after 2 min
    "dune_flows": 6 * 3600,      # 4h cadence default → stale after 6 h
    "alchemy_blocks": 180,       # ~12 s per block → stale after 3 min
    "whale_transfers": 6 * 3600, # whales can be quiet — stale after 6 h
}


def _age(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds()


def _status(name: str, ts: datetime | None) -> DataSourceStatus:
    lag = _age(ts)
    stale = lag is None or lag > STALE_S.get(name, 3600)
    return DataSourceStatus(name=name, last_update=ts, lag_seconds=lag, stale=stale)


@router.get("/health", response_model=HealthResponse)
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    last_candle = session.execute(
        select(func.max(PriceCandle.ts)).where(PriceCandle.timeframe == "1m")
    ).scalar_one()
    last_flow = session.execute(select(func.max(ExchangeFlow.ts_bucket))).scalar_one()
    last_block = session.execute(select(func.max(NetworkActivity.ts))).scalar_one()
    last_whale = session.execute(select(func.max(Transfer.ts))).scalar_one()

    sources = [
        _status("binance_1m", last_candle),
        _status("dune_flows", last_flow),
        _status("alchemy_blocks", last_block),
        _status("whale_transfers", last_whale),
    ]

    # Degraded if a critical source is stale — non-critical sources may
    # legitimately be cold (e.g. no whales in the last 6h).
    critical_names = {"binance_1m", "alchemy_blocks"}
    critical_stale = any(s.stale for s in sources if s.name in critical_names)
    status = "degraded" if critical_stale else "ok"
    return HealthResponse(status=status, version="0.1.0", sources=sources)
