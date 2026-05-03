"""Upsert path for hourly LST totalSupply() snapshots. One row per
(ts_bucket, token), Postgres on_conflict_do_update for idempotency."""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import LstSupply


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    cleaned = value.replace("Z", "+00:00").replace(" UTC", "+00:00")
    return datetime.fromisoformat(cleaned)


def upsert_lst_supply(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, token). Returns count of input rows."""
    if not rows:
        return 0
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "token": r["token"],
            "supply": r["supply"],
            "eth_supply": r.get("eth_supply"),
        }
        for r in rows
    ]
    stmt = pg_insert(LstSupply).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "token"],
        set_={
            "supply": stmt.excluded.supply,
            "eth_supply": stmt.excluded.eth_supply,
        },
    )
    session.execute(stmt)
    return len(values)
