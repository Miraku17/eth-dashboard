"""sync_beacon_flows — replaces Dune staking_flows query.

Reads beacon blocks from Lighthouse directly, sums deposits + withdrawals,
classifies withdrawals as partial (rewards skim) vs full (validator exit),
and upserts hourly buckets into `staking_flows`.

Withdrawal classification heuristic: amount >= 32 ETH (32_000_000_000 gwei)
is a full exit (returns the validator's principal); anything smaller is a
partial reward skim. Slashed validators can technically full-exit with
< 32 ETH but those are rare; classifying them as 'partial' is harmless
(the panel's net-flow math still adds up).

Cron strategy:
  * Cursor (highest processed slot) lives in Redis under `beacon_flows:slot`.
  * Each tick: fetch finalized slot from Lighthouse, walk slots [cursor+1
    .. finalized] in chunks. Upsert hourly buckets additively, then advance
    the cursor.
  * On first run with no cursor, default to (finalized - 300) ≈ 1 hour back.
    Historical 30-day data already exists from the prior Dune-fed period;
    the live cron picks up from "now" forward.

Slots are fetched serially, but Lighthouse on the self-hosted node serves
each in single-digit ms, so a 5-minute cron tick (~25 slots) finishes in
well under a second.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.orm import Session

from app.clients.beacon import GWEI_PER_ETH, BeaconClient
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import AddressLabel, PriceCandle, StakingFlow, StakingFlowByEntity
from app.core.sync_status import record_sync_ok

log = logging.getLogger(__name__)

# Above this withdrawal amount, the validator has fully exited. Below, it's
# a routine partial skim of staking rewards. Mainnet validator MAX_EFFECTIVE_BALANCE
# = 32 ETH; anything that withdraws ≥32 ETH is necessarily an exit.
_FULL_EXIT_THRESHOLD_GWEI = 32 * GWEI_PER_ETH

# Per-tick slot ceiling. Bounds the worker's HTTP fan-out so a long-overdue
# run after a multi-hour outage doesn't try to pull thousands of blocks at
# once. The cron schedule (5 min) keeps us well under this in steady state.
_MAX_SLOTS_PER_TICK = 200

_REDIS_CURSOR_KEY = "beacon_flows:slot"


async def _get_cursor(redis, default: int) -> int:
    raw = await redis.get(_REDIS_CURSOR_KEY)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


async def _set_cursor(redis, slot: int) -> None:
    await redis.set(_REDIS_CURSOR_KEY, str(slot))


def _bucket_hour(ts_unix: int) -> datetime:
    """Round a unix-second timestamp down to the hour bucket."""
    return datetime.fromtimestamp(ts_unix, tz=UTC).replace(
        minute=0, second=0, microsecond=0
    )


def _latest_eth_price_at(session, ts_bucket: datetime) -> float | None:
    """Best-effort ETH/USD price near `ts_bucket`. Falls back to the most
    recent 1h candle when an exact match isn't available (e.g. if the
    price sync is briefly behind)."""
    row = session.execute(
        select(PriceCandle.close)
        .where(
            PriceCandle.symbol == "ETHUSDT",
            PriceCandle.timeframe == "1h",
            PriceCandle.ts <= ts_bucket,
        )
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar()
    return float(row) if row is not None else None


def _flush(buckets: dict[tuple[datetime, str], int], session) -> int:
    """Upsert accumulated (ts_bucket, kind) -> gwei totals into staking_flows
    with additive semantics (multiple flushes within the same hour compose).
    Returns the number of rows persisted."""
    if not buckets:
        return 0
    rows = []
    for (ts_bucket, kind), gwei in buckets.items():
        eth = Decimal(gwei) / Decimal(GWEI_PER_ETH)
        price = _latest_eth_price_at(session, ts_bucket)
        usd = float(eth) * price if price is not None else None
        rows.append(
            {
                "ts_bucket": ts_bucket,
                "kind": kind,
                "amount_eth": eth,
                "amount_usd": usd,
            }
        )
    stmt = pg_insert(StakingFlow).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "kind"],
        set_={
            "amount_eth": StakingFlow.amount_eth + stmt.excluded.amount_eth,
            "amount_usd": stmt.excluded.amount_usd,  # last-write-wins for USD; ETH is the source of truth
        },
    )
    session.execute(stmt)
    session.commit()
    return len(rows)


def _flush_by_entity(
    buckets: dict[tuple[datetime, str, str], int], session: Session
) -> int:
    """Upsert per-entity rollups into staking_flows_by_entity. Same additive
    semantics as _flush, just keyed by (ts_bucket, kind, entity)."""
    if not buckets:
        return 0
    rows = []
    for (ts_bucket, kind, entity), gwei in buckets.items():
        eth = Decimal(gwei) / Decimal(GWEI_PER_ETH)
        price = _latest_eth_price_at(session, ts_bucket)
        usd = float(eth) * price if price is not None else None
        rows.append(
            {
                "ts_bucket": ts_bucket,
                "kind": kind,
                "entity": entity,
                "amount_eth": eth,
                "amount_usd": usd,
            }
        )
    stmt = pg_insert(StakingFlowByEntity).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "kind", "entity"],
        set_={
            "amount_eth": StakingFlowByEntity.amount_eth + stmt.excluded.amount_eth,
            "amount_usd": stmt.excluded.amount_usd,
        },
    )
    session.execute(stmt)
    session.commit()
    return len(rows)


def _load_label_map(session: Session) -> dict[str, str]:
    """Load all curated 'staking' / 'lrt' labels into a {addr: entity} map.

    Restricted to those two categories because they're the only ones that
    can plausibly be the destination of a beacon-chain deposit / withdrawal.
    We use the human-readable `label` (e.g. 'Lido stETH', 'Coinbase: cbETH')
    as the entity, simplified to a top-level issuer name.
    """
    rows = session.execute(
        AddressLabel.__table__.select().where(
            AddressLabel.category.in_(["staking", "lrt"])
        )
    ).all()
    return {r.address: _entity_from_label(r.label) for r in rows}


def _entity_from_label(label: str) -> str:
    """Collapse multi-word labels to a clean issuer name. The address_label
    registry stores e.g. 'Lido stETH', 'Lido withdrawal queue', 'Rocket
    Pool: rETH' — we want a single 'Lido' / 'Rocket Pool' bucket per
    issuer in the staking_flows_by_entity table."""
    low = label.lower()
    if "lido" in low:
        return "Lido"
    if "rocket pool" in low or "rocket" in low:
        return "Rocket Pool"
    if "coinbase" in low:
        return "Coinbase"
    if "kraken" in low:
        return "Kraken"
    if "frax" in low:
        return "Frax"
    if "stakewise" in low:
        return "StakeWise"
    if "figment" in low:
        return "Figment"
    if "binance" in low:
        return "Binance Staking"
    if "bitcoin suisse" in low:
        return "Bitcoin Suisse"
    if "kelp" in low:
        return "Kelp DAO"
    if "ether.fi" in low or "etherfi" in low:
        return "ether.fi"
    if "renzo" in low:
        return "Renzo"
    if "puffer" in low:
        return "Puffer"
    if "swell" in low:
        return "Swell"
    if "stader" in low:
        return "Stader"
    if "mantle" in low:
        return "Mantle"
    if "eigenlayer" in low or "eigenpod" in low:
        return "EigenLayer"
    if "beacon deposit" in low:
        return "Beacon Deposit"
    return label  # fall through — e.g. for unmapped staking entries


async def sync_beacon_flows(ctx: dict) -> dict:
    """Walk new finalized slots, sum deposits + withdrawals, upsert
    hourly buckets. No-op if BEACON_HTTP_URL isn't set."""
    settings = get_settings()
    if not settings.beacon_http_url:
        log.info("BEACON_HTTP_URL not set -- skipping beacon flow sync")
        return {"skipped": "no beacon url"}

    redis = ctx.get("redis")
    SessionLocal = get_sessionmaker()

    # Load the address → entity map once per tick. Cheap (~few hundred rows)
    # and a stable snapshot for the duration of this run.
    with SessionLocal() as session:
        entity_map = _load_label_map(session)

    async with httpx.AsyncClient(
        base_url=settings.beacon_http_url, timeout=15.0
    ) as http:
        client = BeaconClient(http)
        finalized = await client.finalized_slot()
        if finalized is None:
            log.warning("beacon flows: finalized slot unknown -- skipping")
            return {"error": "no finalized head"}

        cursor = await _get_cursor(redis, default=max(0, finalized - 300))
        if cursor >= finalized:
            return {"action": "caught_up", "slot": finalized}

        end = min(finalized, cursor + _MAX_SLOTS_PER_TICK)

        # Accumulate in-memory; one PG round-trip at the end of the chunk.
        # Two parallel buckets — total flows + per-entity flows — populated
        # in a single pass so we don't re-walk the events.
        buckets: dict[tuple[datetime, str], int] = {}
        entity_buckets: dict[tuple[datetime, str, str], int] = {}
        seen_blocks = 0

        def _attribute(addr: str | None) -> str:
            if addr is None:
                return "Unattributed"
            return entity_map.get(addr.lower(), "Unattributed")

        for slot in range(cursor + 1, end + 1):
            block = await client.block_flows(slot)
            if block is None:
                continue  # missed slot
            seen_blocks += 1
            ts = block["ts"]
            if ts == 0:
                continue
            hour = _bucket_hour(ts)
            for amt_gwei, addr in block["deposits"]:
                key = (hour, "deposit")
                buckets[key] = buckets.get(key, 0) + amt_gwei
                ekey = (hour, "deposit", _attribute(addr))
                entity_buckets[ekey] = entity_buckets.get(ekey, 0) + amt_gwei
            for amt_gwei, _vi, addr in block["withdrawals"]:
                kind = (
                    "withdrawal_full"
                    if amt_gwei >= _FULL_EXIT_THRESHOLD_GWEI
                    else "withdrawal_partial"
                )
                key = (hour, kind)
                buckets[key] = buckets.get(key, 0) + amt_gwei
                ekey = (hour, kind, _attribute(addr))
                entity_buckets[ekey] = entity_buckets.get(ekey, 0) + amt_gwei

    with SessionLocal() as session:
        n_total = _flush(buckets, session)
        n_entity = _flush_by_entity(entity_buckets, session)

    await _set_cursor(redis, end)
    record_sync_ok("staking_flows")
    log.info(
        "synced beacon_flows: slots %d..%d (%d blocks, %d total + %d entity rows)",
        cursor + 1, end, seen_blocks, n_total, n_entity,
    )
    return {
        "slots_walked": end - cursor,
        "blocks_seen": seen_blocks,
        "rows_upserted": n_total,
        "entity_rows_upserted": n_entity,
        "cursor": end,
    }
