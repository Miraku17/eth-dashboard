"""Persist DerivSnap rows, bucketed to the hour for clean time-series."""
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients.derivatives import DerivSnap
from app.core.models import DerivativesSnapshot


def bucket_hour(ts: datetime) -> datetime:
    """Round down to the hour so re-syncing within the same hour upserts."""
    return ts.replace(minute=0, second=0, microsecond=0)


def upsert_snapshot(session: Session, snap: DerivSnap) -> None:
    stmt = pg_insert(DerivativesSnapshot).values(
        exchange=snap.exchange,
        symbol=snap.symbol,
        ts=bucket_hour(snap.ts),
        oi_usd=snap.oi_usd,
        funding_rate=snap.funding_rate,
        mark_price=snap.mark_price,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["exchange", "symbol", "ts"],
        set_={
            "oi_usd": stmt.excluded.oi_usd,
            "funding_rate": stmt.excluded.funding_rate,
            "mark_price": stmt.excluded.mark_price,
        },
    )
    session.execute(stmt)
    session.commit()


def prune_older_than(session: Session, days: int = 90) -> int:
    """Housekeeping — keep 90 days by default. Hourly × 4 exchanges × 90 days =
    ~8.6k rows, plenty for charts; anything older isn't useful."""
    cutoff = datetime.now(tz=None).astimezone() - timedelta(days=days)
    n = (
        session.query(DerivativesSnapshot)
        .filter(DerivativesSnapshot.ts < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    return n
