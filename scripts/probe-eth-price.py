"""Print the latest 1h ETH/USD candle close — diagnostic for the
volume-buckets aggregator's eth_usd path.

The realtime listener gates volume_bucket_agg.add(...) on
`eth_usd is not None`. If the 1h ETHUSDT candle table has no recent
row, every Swap event silently skips the volume_buckets aggregator.

Run via:
    docker compose exec -T worker python < scripts/probe-eth-price.py

Outputs:
  latest 1h ETH price: <number>     -> pricing OK, look elsewhere
  latest 1h ETH price: None         -> need to fall back to 5m/1m candles
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.models import PriceCandle


def main() -> None:
    s = get_sessionmaker()()
    for tf in ("1h", "5m", "1m"):
        row = s.execute(
            select(PriceCandle.ts, PriceCandle.close)
            .where(PriceCandle.symbol == "ETHUSDT", PriceCandle.timeframe == tf)
            .order_by(PriceCandle.ts.desc())
            .limit(1)
        ).first()
        if row is None:
            print(f"  {tf:<3}: (no rows)")
        else:
            ts, close = row
            age = datetime.now(UTC) - ts
            print(f"  {tf:<3}: {float(close):>10.2f} USD   ts={ts.isoformat()[:19]}   age={int(age.total_seconds())}s")
    # The listener calls the same SELECT path with timeframe='1h'. If 1h is
    # stale or empty but 1m is fresh, the price-sync cron is healthy and the
    # fix is to relax the listener's lookup to fall through to a smaller
    # timeframe.


if __name__ == "__main__":
    main()
