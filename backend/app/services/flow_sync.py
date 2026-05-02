from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import (
    ExchangeFlow,
    OnchainVolume,
    OrderFlow,
    StablecoinFlow,
    StakingFlow,
    VolumeBucket,
)

# Postgres caps each statement at 65,535 bound parameters. Each row above has
# 4–5 columns, so 1,000 rows per batch keeps us well under that limit even as
# the schema grows. We still commit once at the end so the whole sync is
# atomic from the caller's POV.
CHUNK_SIZE = 1000


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # Dune returns either ISO 8601 ("…Z") or space-separated with "UTC" suffix
    # (e.g. "2026-04-23 09:00:00.000 UTC"). Normalize to fromisoformat input.
    s = value.replace(" UTC", "+00:00").replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    return datetime.fromisoformat(s)


def _upsert_chunked(
    session: Session,
    table: Any,
    values: list[dict],
    *,
    index_elements: list[str],
    update_cols: list[str],
) -> int:
    """Batch an upsert so we don't trip Postgres's 65,535 param limit."""
    if not values:
        return 0
    for i in range(0, len(values), CHUNK_SIZE):
        chunk = values[i : i + CHUNK_SIZE]
        stmt = pg_insert(table).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={col: stmt.excluded[col] for col in update_cols},
        )
        session.execute(stmt)
    session.commit()
    return len(values)


def upsert_exchange_flows(session: Session, rows: list[dict]) -> int:
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
    return _upsert_chunked(
        session,
        ExchangeFlow,
        values,
        index_elements=["exchange", "direction", "asset", "ts_bucket"],
        update_cols=["usd_value"],
    )


def upsert_stablecoin_flows(session: Session, rows: list[dict]) -> int:
    values = [
        {
            "asset": r["asset"],
            "direction": r["direction"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    return _upsert_chunked(
        session,
        StablecoinFlow,
        values,
        index_elements=["asset", "direction", "ts_bucket"],
        update_cols=["usd_value"],
    )


def upsert_onchain_volume(session: Session, rows: list[dict]) -> int:
    values = [
        {
            "asset": r["asset"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "tx_count": r["tx_count"],
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    return _upsert_chunked(
        session,
        OnchainVolume,
        values,
        index_elements=["asset", "ts_bucket"],
        update_cols=["tx_count", "usd_value"],
    )


def upsert_order_flow(session: Session, rows: list[dict]) -> int:
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "side": r["side"],
            "usd_value": r["usd_value"],
            "trade_count": r["trade_count"],
        }
        for r in rows
        if r.get("side") in ("buy", "sell")
    ]
    return _upsert_chunked(
        session,
        OrderFlow,
        values,
        index_elements=["ts_bucket", "side"],
        update_cols=["usd_value", "trade_count"],
    )


_VOLUME_BUCKETS = ("retail", "mid", "large", "whale")


def upsert_volume_buckets(session: Session, rows: list[dict]) -> int:
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "bucket": r["bucket"],
            "usd_value": r["usd_value"],
            "trade_count": r["trade_count"],
        }
        for r in rows
        if r.get("bucket") in _VOLUME_BUCKETS
    ]
    return _upsert_chunked(
        session,
        VolumeBucket,
        values,
        index_elements=["ts_bucket", "bucket"],
        update_cols=["usd_value", "trade_count"],
    )


_STAKING_KINDS = ("deposit", "withdrawal_partial", "withdrawal_full")


def upsert_staking_flows(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, kind). Filters out rows whose kind isn't
    in _STAKING_KINDS as a defensive guard against schema drift on the Dune side.
    """
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "kind": r["kind"],
            "amount_eth": r["amount_eth"],
            "amount_usd": r.get("amount_usd"),
        }
        for r in rows
        if r.get("kind") in _STAKING_KINDS
    ]
    return _upsert_chunked(
        session,
        StakingFlow,
        values,
        index_elements=["ts_bucket", "kind"],
        update_cols=["amount_eth", "amount_usd"],
    )
