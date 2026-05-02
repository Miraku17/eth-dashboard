"""Upsert path for hourly DEX pool TVL snapshots. One row per
(ts_bucket, pool_id). Postgres on_conflict_do_update for idempotency."""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import DexPoolTvl


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    cleaned = value.replace("Z", "+00:00").replace(" UTC", "+00:00")
    return datetime.fromisoformat(cleaned)


def upsert_dex_pool_tvl(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, pool_id)."""
    if not rows:
        return 0
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "pool_id": r["pool_id"],
            "dex": r["dex"],
            "symbol": r["symbol"],
            "tvl_usd": r["tvl_usd"],
        }
        for r in rows
    ]
    stmt = pg_insert(DexPoolTvl).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "pool_id"],
        set_={
            "dex": stmt.excluded.dex,
            "symbol": stmt.excluded.symbol,
            "tvl_usd": stmt.excluded.tvl_usd,
        },
    )
    session.execute(stmt)
    return len(values)
