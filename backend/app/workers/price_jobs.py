"""arq task entrypoints for price sync. Thin wrappers around services.price_sync."""
import logging
from datetime import UTC, datetime

import httpx

from app.core.db import get_sessionmaker
from app.services.price_sync import backfill_timeframe, sync_latest

log = logging.getLogger(__name__)

SYMBOL = "ETHUSDT"
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M")

BACKFILL_WINDOWS_DAYS = {
    "1m": 7,
    "5m": 30,
    "15m": 30,
    "1h": 30,
    "4h": 90,
    "1d": 365,
    # ~10y of weekly bars; ~30y of monthly bars. Binance caps `limit` at 1000
    # and these tables are tiny, so a generous window costs nothing.
    "1w": 365 * 10,
    "1M": 365 * 30,
}


async def backfill_price_history(ctx: dict) -> dict:
    """Run once: backfill configured windows for each timeframe. Idempotent via upsert."""
    http: httpx.AsyncClient = ctx["http"]
    SessionLocal = get_sessionmaker()
    results: dict[str, int] = {}
    end_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    with SessionLocal() as session:
        for tf in TIMEFRAMES:
            days = BACKFILL_WINDOWS_DAYS[tf]
            start_ms = end_ms - days * 24 * 60 * 60 * 1000
            n = await backfill_timeframe(
                http, session, symbol=SYMBOL, timeframe=tf,
                start_ms=start_ms, end_ms=end_ms,
            )
            log.info("backfilled %s: %d candles (%d days)", tf, n, days)
            results[tf] = n
    return results


async def sync_price_latest(ctx: dict) -> dict:
    """Forward sync: fetch the 2 most recent candles per timeframe and upsert."""
    http: httpx.AsyncClient = ctx["http"]
    SessionLocal = get_sessionmaker()
    results: dict[str, int] = {}
    with SessionLocal() as session:
        for tf in TIMEFRAMES:
            n = await sync_latest(http, session, symbol=SYMBOL, timeframe=tf)
            results[tf] = n
    return results
