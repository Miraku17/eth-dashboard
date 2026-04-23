from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients.binance import Kline
from app.core.models import PriceCandle


def upsert_klines(
    session: Session,
    symbol: str,
    timeframe: str,
    klines: Iterable[Kline],
) -> int:
    """Upsert candles for (symbol, timeframe). Returns number of rows affected."""
    rows = [_kline_to_row(symbol, timeframe, k) for k in klines]
    if not rows:
        return 0

    stmt = pg_insert(PriceCandle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "timeframe", "ts"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    result = session.execute(stmt)
    session.commit()
    # PostgreSQL INSERT ON CONFLICT returns -1 for rowcount; count rows instead
    rowcount = result.rowcount
    return len(rows) if rowcount == -1 else (rowcount or 0)


def _kline_to_row(symbol: str, timeframe: str, k: Kline) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": datetime.fromtimestamp(k.open_time_ms / 1000, tz=UTC),
        "open": k.open,
        "high": k.high,
        "low": k.low,
        "close": k.close,
        "volume": k.volume,
    }


import httpx

from app.clients.binance import BinanceClient

SYNC_LATEST_LIMIT = 2


async def backfill_timeframe(
    http: httpx.AsyncClient,
    session: Session,
    *,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    page_size: int = 500,
) -> int:
    """Paginate klines from start_ms to end_ms and upsert them. Returns total rows."""
    client = BinanceClient(http)
    total = 0
    cursor = start_ms
    while cursor < end_ms:
        batch = await client.fetch_klines(
            symbol, timeframe, start_ms=cursor, end_ms=end_ms, limit=page_size
        )
        if not batch:
            break
        total += upsert_klines(session, symbol, timeframe, batch)
        cursor = batch[-1].open_time_ms + 1
    return total


async def sync_latest(
    http: httpx.AsyncClient,
    session: Session,
    *,
    symbol: str,
    timeframe: str,
) -> int:
    """Fetch the most recent few candles and upsert."""
    client = BinanceClient(http)
    batch = await client.fetch_klines(symbol, timeframe, limit=SYNC_LATEST_LIMIT)
    return upsert_klines(session, symbol, timeframe, batch)
