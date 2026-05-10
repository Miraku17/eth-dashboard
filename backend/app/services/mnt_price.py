"""Redis-cached MNT/USD lookup via CoinGecko's free /simple/price endpoint.

Used at /api/flows/mantle-order-flow read time to convert raw mnt_amount
into usd_value. Returns None on HTTP error / rate limit; the endpoint
falls back to MNT-denominated bars in that case. Negative results are
NOT cached so the next request re-attempts immediately."""
from __future__ import annotations

import logging
from typing import Final

import httpx

from app.core.cache import cached_json_get, cached_json_set

log = logging.getLogger(__name__)

MNT_PRICE_CACHE_KEY: Final[str] = "mnt_usd:current"
_CACHE_TTL_S: Final[int] = 60
_COINGECKO_URL: Final[str] = (
    "https://api.coingecko.com/api/v3/simple/price?ids=mantle&vs_currencies=usd"
)
_REQUEST_TIMEOUT_S: Final[float] = 5.0


def get_mnt_usd() -> float | None:
    """Return current MNT/USD or None if upstream is unreachable."""
    cached = cached_json_get(MNT_PRICE_CACHE_KEY)
    if cached is not None:
        try:
            return float(cached)
        except (TypeError, ValueError):
            log.warning("corrupt mnt_usd cache value: %r", cached)
            # fall through to refresh

    try:
        resp = httpx.get(_COINGECKO_URL, timeout=_REQUEST_TIMEOUT_S)
    except httpx.RequestError as exc:
        log.warning("mnt_usd fetch failed: %s", exc)
        return None

    if resp.status_code != 200:
        log.warning("mnt_usd non-200: %s", resp.status_code)
        return None

    data = resp.json()
    price = data.get("mantle", {}).get("usd")
    if not isinstance(price, (int, float)):
        return None

    cached_json_set(MNT_PRICE_CACHE_KEY, float(price), _CACHE_TTL_S)
    return float(price)
