from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # Dune returns either ISO 8601 ("…Z") or space-separated with "UTC" suffix
    # (e.g. "2026-04-23 09:00:00.000 UTC"). Normalize to fromisoformat input.
    s = value.replace(" UTC", "+00:00").replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    return datetime.fromisoformat(s)


def upsert_exchange_flows(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "exchange": r["exchange"],
            "direction": r["direction"],
            "asset": r["asset"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(ExchangeFlow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["exchange", "direction", "asset", "ts_bucket"],
        set_={"usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)


def upsert_stablecoin_flows(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "asset": r["asset"],
            "direction": r["direction"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(StablecoinFlow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "direction", "ts_bucket"],
        set_={"usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)


def upsert_onchain_volume(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "asset": r["asset"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "tx_count": r["tx_count"],
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(OnchainVolume).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "ts_bucket"],
        set_={"tx_count": stmt.excluded.tx_count, "usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)
