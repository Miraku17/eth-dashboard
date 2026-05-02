"""Hourly cron: snapshot DeFi-protocol TVL on Ethereum mainnet.

Fan-out: one DefiLlama HTTP call per protocol (5 concurrent), parse latest
Ethereum chain TVL per asset, upsert one row per (ts_bucket, protocol, asset).
"""
import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.clients.defillama import DEFILLAMA_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.defi_protocols import DEFI_PROTOCOLS
from app.services.defi_tvl_sync import upsert_protocol_tvl

log = logging.getLogger(__name__)

_CONCURRENCY = 5


def _build_rows(fetched: dict[str, dict[str, float]], ts_bucket: str) -> list[dict]:
    """Flatten {protocol: {asset: tvl_usd}} into row dicts. Skips empty
    protocols and non-positive TVL values."""
    rows: list[dict] = []
    for protocol, by_asset in fetched.items():
        if not by_asset:
            continue
        for asset, tvl in by_asset.items():
            if not isinstance(tvl, (int, float)) or tvl <= 0:
                continue
            rows.append(
                {"ts_bucket": ts_bucket, "protocol": protocol, "asset": asset, "tvl_usd": float(tvl)}
            )
    return rows


async def _fetch_one(
    sem: asyncio.Semaphore, client: DefiLlamaClient, slug: str
) -> tuple[str, dict[str, float]]:
    async with sem:
        return slug, await client.fetch_protocol_tvl(slug)


async def sync_defi_tvl(ctx: dict) -> dict:
    """Snapshot DefiLlama TVL for the curated 10-protocol list at top-of-hour."""
    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(
        base_url=DEFILLAMA_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=20.0,
    ) as http:
        client = DefiLlamaClient(http)
        results = await asyncio.gather(
            *(_fetch_one(sem, client, p.slug) for p in DEFI_PROTOCOLS)
        )

    fetched = dict(results)
    rows = _build_rows(fetched, ts_bucket=ts_bucket)
    if not rows:
        log.warning("defi tvl: no rows after fetch — skipping write")
        return {"protocol_tvl": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_protocol_tvl(session, rows)
        session.commit()

    record_sync_ok("protocol_tvl")
    log.info("synced protocol_tvl: %d rows across %d protocols", n, len(fetched))
    return {"protocol_tvl": n}
