"""Hourly cron: snapshot top-N Ethereum-mainnet DEX pools by TVL.

DefiLlama /yields/pools returns ~10k pools across all chains/protocols.
We filter to Ethereum + Uniswap V2/V3 + Curve + Balancer, sort by tvlUsd
desc, take top 100, upsert.
"""
import logging
from datetime import UTC, datetime

import httpx

from app.clients.defillama import DEFILLAMA_YIELDS_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.dex_pool_sync import upsert_dex_pool_tvl

log = logging.getLogger(__name__)

ALLOWED_DEXES: frozenset[str] = frozenset(
    {"uniswap-v3", "uniswap-v2", "curve-dex", "balancer-v2"}
)
TOP_N = 100


def _filter_and_top_n(pools: list[dict]) -> list[dict]:
    """Keep Ethereum + allowed-DEX pools with positive TVL, sort desc, cap top 100."""
    filtered: list[dict] = []
    for p in pools:
        if p.get("chain") != "Ethereum":
            continue
        if p.get("project") not in ALLOWED_DEXES:
            continue
        tvl = p.get("tvlUsd")
        if not isinstance(tvl, (int, float)) or tvl <= 0:
            continue
        filtered.append(p)
    filtered.sort(key=lambda p: p["tvlUsd"], reverse=True)
    return filtered[:TOP_N]


async def sync_dex_pool_tvl(ctx: dict) -> dict:
    """Snapshot top-100 Ethereum DEX pools by TVL at top-of-hour."""
    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()

    async with httpx.AsyncClient(
        base_url=DEFILLAMA_YIELDS_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=30.0,
    ) as http:
        client = DefiLlamaClient(http)
        all_pools = await client.fetch_yield_pools()

    if not all_pools:
        log.warning("dex pool tvl: no pools fetched — skipping write")
        return {"dex_pool_tvl": 0}

    top = _filter_and_top_n(all_pools)
    rows = [
        {
            "ts_bucket": ts_bucket,
            "pool_id": p["pool"],
            "dex": p["project"],
            "symbol": p.get("symbol") or "",
            "tvl_usd": float(p["tvlUsd"]),
        }
        for p in top
    ]

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_dex_pool_tvl(session, rows)
        session.commit()

    record_sync_ok("dex_pool_tvl")
    log.info("synced dex_pool_tvl: %d pools (top of %d Ethereum pools)", n, len(all_pools))
    return {"dex_pool_tvl": n}
