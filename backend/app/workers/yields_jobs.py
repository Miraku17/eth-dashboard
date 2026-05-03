"""Hourly cron: snapshot LST + LRT staking APY from DefiLlama /yields/pools.

For each LST symbol / LRT slug we have a curated (project, symbol) pool key
(see app.services.staking_yields). The cron pulls the full pool list once,
filters to our target keys, and upserts a row per (kind, key) into
`staking_yield`. Missing pools (e.g. Mantle Restaking has none exposed
today) leave NULL apy so the panel renders "—" rather than 0.
"""
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.clients.defillama import DEFILLAMA_YIELDS_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.models import StakingYield
from app.core.sync_status import record_sync_ok
from app.services.staking_yields import LRT_YIELD_KEYS, LST_YIELD_KEYS, YieldPoolKey

log = logging.getLogger(__name__)


def _index_pools(pools: list[dict]) -> dict[tuple[str, str], dict]:
    """Build a lookup table of (project, SYMBOL) -> pool dict for Ethereum pools.

    For protocols that expose multiple pools under one project (ether.fi
    has WEETH and EBTC; pendle has many SWETH variants), we keep the
    HIGHEST-TVL match — that's the canonical staking pool.
    """
    out: dict[tuple[str, str], dict] = {}
    for p in pools:
        if p.get("chain") != "Ethereum":
            continue
        proj = p.get("project")
        sym = (p.get("symbol") or "").upper()
        if not proj or not sym:
            continue
        key = (proj, sym)
        prev = out.get(key)
        if prev is None or (p.get("tvlUsd") or 0) > (prev.get("tvlUsd") or 0):
            out[key] = p
    return out


def _resolve_apy(index: dict[tuple[str, str], dict], k: YieldPoolKey) -> float | None:
    pool = index.get((k.project, k.symbol))
    if pool is None:
        return None
    apy = pool.get("apy")
    if not isinstance(apy, (int, float)):
        return None
    return float(apy)


async def sync_staking_yields(ctx: dict) -> dict:
    """Refresh `staking_yield` for every LST + LRT key. Single round-trip."""
    async with httpx.AsyncClient(
        base_url=DEFILLAMA_YIELDS_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=30.0,
    ) as http:
        client = DefiLlamaClient(http)
        all_pools = await client.fetch_yield_pools()

    if not all_pools:
        log.warning("staking yields: no pools fetched -- skipping write")
        return {"staking_yield": 0}

    index = _index_pools(all_pools)
    now = datetime.now(UTC)

    rows: list[dict] = []
    for symbol, key in LST_YIELD_KEYS.items():
        rows.append(
            {
                "kind": "lst",
                "key": symbol,
                "apy": _resolve_apy(index, key),
                "updated_at": now,
            }
        )
    for slug, key in LRT_YIELD_KEYS.items():
        rows.append(
            {
                "kind": "lrt",
                "key": slug,
                "apy": _resolve_apy(index, key),
                "updated_at": now,
            }
        )

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        stmt = pg_insert(StakingYield).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["kind", "key"],
            set_={"apy": stmt.excluded.apy, "updated_at": stmt.excluded.updated_at},
        )
        session.execute(stmt)
        session.commit()

    record_sync_ok("staking_yield")
    resolved = sum(1 for r in rows if r["apy"] is not None)
    log.info("synced staking_yield: %d rows (%d resolved, %d null)",
             len(rows), resolved, len(rows) - resolved)
    return {"staking_yield": len(rows), "resolved": resolved}
