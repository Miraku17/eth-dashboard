"""Hourly cron: read totalSupply() for each LST and upsert one row per token."""
import logging
from datetime import UTC, datetime

import httpx

from app.clients.eth_rpc import EthRpcClient, RpcError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.lst_sync import upsert_lst_supply
from app.services.lst_tokens import LST_TOKENS, TOTAL_SUPPLY_SELECTOR

log = logging.getLogger(__name__)


def _decode_uint256_to_supply(hex_value: str | None, decimals: int) -> float | None:
    """Convert a hex-encoded uint256 RPC return into a decimal-normalized float.

    Returns None for missing / malformed responses so the caller can skip the row.
    """
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
    return raw / (10 ** decimals)


def _build_rows_from_results(
    results: list[str | None], ts_bucket: str
) -> list[dict]:
    """Map (LST_TOKENS[i], results[i]) → row dicts. Skips None entries."""
    rows: list[dict] = []
    for token, raw in zip(LST_TOKENS, results):
        supply = _decode_uint256_to_supply(raw, token.decimals)
        if supply is None:
            log.warning("lst supply decode failed for %s", token.symbol)
            continue
        rows.append({"ts_bucket": ts_bucket, "token": token.symbol, "supply": supply})
    return rows


async def sync_lst_supply(ctx: dict) -> dict:
    """Read totalSupply() for each LST in a single batch call, upsert one row
    per token at the current top-of-hour bucket. No-op if ALCHEMY_HTTP_URL unset."""
    settings = get_settings()
    url = settings.effective_http_url
    if not url:
        log.info("ALCHEMY_HTTP_URL not set — skipping lst supply sync")
        return {"skipped": "no rpc url"}

    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
    calls = [(t.address, TOTAL_SUPPLY_SELECTOR) for t in LST_TOKENS]

    async with httpx.AsyncClient(timeout=20.0) as http:
        client = EthRpcClient(http, url=url)
        try:
            results = await client.batch_eth_call(calls)
        except (httpx.HTTPError, RpcError) as e:
            log.error("lst supply batch_eth_call failed: %s", e)
            return {"error": str(e)}

    rows = _build_rows_from_results(results, ts_bucket=ts_bucket)
    if not rows:
        log.warning("lst supply: no rows decoded — skipping write")
        return {"lst_supply": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_lst_supply(session, rows)
        session.commit()

    record_sync_ok("lst_supply")
    log.info("synced lst_supply: %d rows", n)
    return {"lst_supply": n}
