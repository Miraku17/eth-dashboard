"""Hourly cron: read totalSupply() + exchange-rate for each LST in a single
JSON-RPC batch, persist both raw supply AND ETH-equivalent supply.

ETH-equivalent normalization matters because share-style tokens like rETH
and sfrxETH have a totalSupply that is ~10% smaller than the ETH they back
(the rest is accumulated yield). Without this, the LST market-share panel
visually understates them. The eth_supply column is nullable: stETH skips
the rate call (rebasing token, supply already equals ETH amount) and any
per-token rate failure also leaves NULL so the panel can fall back to raw
supply rather than render nothing.
"""
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


def _decode_uint256(hex_value: str | None, decimals: int) -> float | None:
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


def _build_rows(
    supply_results: list[str | None],
    rate_results: list[str | None],
    rate_index_by_symbol: dict[str, int],
    ts_bucket: str,
) -> list[dict]:
    """Pair each token's supply hex + (optional) rate hex into a row dict.

    eth_supply is computed as supply × rate, or:
      - = supply when the token has no rate config (stETH, rebasing)
      - = None when a rate was configured but the call returned an error
        (so the panel falls back to raw supply rather than a wrong number)
    """
    rows: list[dict] = []
    for i, token in enumerate(LST_TOKENS):
        supply = _decode_uint256(supply_results[i], token.decimals)
        if supply is None:
            log.warning("lst supply decode failed for %s", token.symbol)
            continue

        eth_supply: float | None
        if token.rate_calldata is None:
            # Rebasing token: supply already denominated in ETH.
            eth_supply = supply
        else:
            rate_idx = rate_index_by_symbol.get(token.symbol)
            rate_hex = rate_results[rate_idx] if rate_idx is not None else None
            rate = _decode_uint256(rate_hex, token.rate_decimals)
            if rate is None or rate <= 0:
                log.warning(
                    "lst rate decode failed for %s — eth_supply left null", token.symbol
                )
                eth_supply = None
            else:
                eth_supply = supply * rate

        rows.append(
            {
                "ts_bucket": ts_bucket,
                "token": token.symbol,
                "supply": supply,
                "eth_supply": eth_supply,
            }
        )
    return rows


async def sync_lst_supply(ctx: dict) -> dict:
    """Read totalSupply() for each LST plus an exchange-rate call where
    configured (single combined batch, two calls per share-token), upsert
    one row per token at the current top-of-hour bucket. No-op if
    ALCHEMY_HTTP_URL unset."""
    settings = get_settings()
    url = settings.effective_http_url
    if not url:
        log.info("ALCHEMY_HTTP_URL not set -- skipping lst supply sync")
        return {"skipped": "no rpc url"}

    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()

    supply_calls = [(t.address, TOTAL_SUPPLY_SELECTOR) for t in LST_TOKENS]
    rate_calls: list[tuple[str, str]] = []
    rate_index_by_symbol: dict[str, int] = {}
    for t in LST_TOKENS:
        if t.rate_address and t.rate_calldata:
            rate_index_by_symbol[t.symbol] = len(rate_calls)
            rate_calls.append((t.rate_address, t.rate_calldata))

    async with httpx.AsyncClient(timeout=20.0) as http:
        client = EthRpcClient(http, url=url)
        try:
            supply_results = await client.batch_eth_call(supply_calls)
        except (httpx.HTTPError, RpcError) as e:
            log.error("lst supply batch_eth_call failed: %s", e)
            return {"error": str(e)}
        # Rate calls in a separate batch so a single bad rate selector
        # can't poison the supply batch's response IDs.
        try:
            rate_results = (
                await client.batch_eth_call(rate_calls) if rate_calls else []
            )
        except (httpx.HTTPError, RpcError) as e:
            log.warning("lst rate batch_eth_call failed (continuing without rates): %s", e)
            rate_results = [None] * len(rate_calls)

    rows = _build_rows(supply_results, rate_results, rate_index_by_symbol, ts_bucket)
    if not rows:
        log.warning("lst supply: no rows decoded -- skipping write")
        return {"lst_supply": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_lst_supply(session, rows)
        session.commit()

    record_sync_ok("lst_supply")
    log.info("synced lst_supply: %d rows", n)
    return {"lst_supply": n}
