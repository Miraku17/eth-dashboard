from collections.abc import Iterable
from datetime import datetime, timezone

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
    return result.rowcount or 0


def _kline_to_row(symbol: str, timeframe: str, k: Kline) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": datetime.fromtimestamp(k.open_time_ms / 1000, tz=timezone.utc),
        "open": k.open,
        "high": k.high,
        "low": k.low,
        "close": k.close,
        "volume": k.volume,
    }
