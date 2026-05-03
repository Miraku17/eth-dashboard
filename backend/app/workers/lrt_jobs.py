"""Hourly cron: snapshot LRT issuer TVL on Ethereum mainnet.

Each LRT protocol's per-asset breakdown (from DefiLlama) gets summed into a
single USD figure per issuer. Persists one row per (ts_bucket, protocol).
Fan-out is concurrency-limited at 5 to stay polite to DefiLlama.
"""
import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.clients.defillama import DEFILLAMA_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.lrt_protocols import LRT_PROTOCOLS
from app.services.lrt_tvl_sync import upsert_lrt_tvl

log = logging.getLogger(__name__)

_CONCURRENCY = 5


async def _fetch_one(
    sem: asyncio.Semaphore, client: DefiLlamaClient, slug: str
) -> tuple[str, float]:
    """Returns (slug, total_usd_summed_across_assets). 0.0 on missing data."""
    async with sem:
        by_asset = await client.fetch_protocol_tvl(slug)
    total = 0.0
    for tvl in by_asset.values():
        if isinstance(tvl, (int, float)) and tvl > 0:
            total += float(tvl)
    return slug, total


def _build_rows(totals: dict[str, float], ts_bucket: str) -> list[dict]:
    rows: list[dict] = []
    for slug, total in totals.items():
        if total <= 0:
            continue
        rows.append({"ts_bucket": ts_bucket, "protocol": slug, "tvl_usd": total})
    return rows


async def sync_lrt_tvl(ctx: dict) -> dict:
    """Snapshot LRT issuer TVL at top-of-hour. Mirrors v3-defi-tvl shape but
    aggregates each protocol to a single USD total per row."""
    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(
        base_url=DEFILLAMA_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=20.0,
    ) as http:
        client = DefiLlamaClient(http)
        results = await asyncio.gather(
            *(_fetch_one(sem, client, p.slug) for p in LRT_PROTOCOLS)
        )

    totals = dict(results)
    rows = _build_rows(totals, ts_bucket=ts_bucket)
    if not rows:
        log.warning("lrt tvl: no rows after fetch -- skipping write")
        return {"lrt_tvl": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_lrt_tvl(session, rows)
        session.commit()

    record_sync_ok("lrt_tvl")
    log.info("synced lrt_tvl: %d rows across %d protocols", n, len(totals))
    return {"lrt_tvl": n}
