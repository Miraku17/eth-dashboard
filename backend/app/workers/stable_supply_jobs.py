"""Cron: read `totalSupply()` for each tracked stable, persist to stable_supply.

Runs every minute. 16 stables in a single JSON-RPC batch = one round-trip
to the (self-hosted) Geth node. Decode each return as an unsigned 256-bit
integer scaled by the token's `decimals`, multiply by the curated
`price_usd_approx` to derive `supply_usd`, and upsert.

Idempotent: PK is (ts, asset) and upsert is on_conflict_do_update on the
two value columns so a backfill or retry won't double-count.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.clients.eth_rpc import EthRpcClient, RpcError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import StableSupply
from app.core.sync_status import record_sync_ok
from app.realtime.tokens import STABLES
from app.services.lst_tokens import TOTAL_SUPPLY_SELECTOR

log = logging.getLogger(__name__)


def _decode_uint256(hex_value: str | None, decimals: int) -> float | None:
    """Hex-encoded uint256 RPC return → float scaled by `decimals`. None on
    missing or malformed input so the caller can skip the row."""
    if not hex_value or not isinstance(hex_value, str):
        return None
    if not hex_value.startswith("0x"):
        return None
    body = hex_value[2:]
    if not body:
        return None
    try:
        raw = int(body, 16)
    except ValueError:
        return None
    return raw / (10**decimals)


async def sync_stable_supply(ctx: dict) -> dict:
    """Read totalSupply() for each tracked stable in one JSON-RPC batch and
    upsert one (ts, asset) row per token. No-op if RPC URL unset."""
    settings = get_settings()
    url = settings.effective_http_url
    if not url:
        log.info("stable supply: no RPC url -- skipping")
        return {"skipped": "no rpc url"}

    ts = datetime.now(UTC).replace(second=0, microsecond=0)

    calls = [(t.address, TOTAL_SUPPLY_SELECTOR) for t in STABLES]
    async with httpx.AsyncClient(timeout=20.0) as http:
        client = EthRpcClient(http, url=url)
        try:
            results = await client.batch_eth_call(calls)
        except (httpx.HTTPError, RpcError) as e:
            log.error("stable supply batch_eth_call failed: %s", e)
            return {"error": str(e)}

    rows: list[dict] = []
    for token, hex_val in zip(STABLES, results, strict=True):
        supply = _decode_uint256(hex_val, token.decimals)
        if supply is None:
            log.warning("stable supply decode failed for %s", token.symbol)
            continue
        supply_usd = supply * token.price_usd_approx
        rows.append(
            {
                "ts": ts,
                "asset": token.symbol,
                "supply": supply,
                "supply_usd": supply_usd,
            }
        )

    if not rows:
        return {"stable_supply": 0}

    stmt = pg_insert(StableSupply).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts", "asset"],
        set_={
            "supply": stmt.excluded.supply,
            "supply_usd": stmt.excluded.supply_usd,
        },
    )
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        session.execute(stmt)
        session.commit()

    record_sync_ok("stable_supply")
    return {"stable_supply": len(rows)}
