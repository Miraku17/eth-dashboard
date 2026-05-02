"""Thin client over the DefiLlama public API (api.llama.fi).

No auth required. We only consume one endpoint:
    GET /protocol/{slug}  →  {chainTvls: {Ethereum: {tokensInUsd: [...]}}}

The response shape is large; we parse just the latest Ethereum snapshot's
per-token USD breakdown.
"""
import logging

import httpx

DEFILLAMA_BASE_URL = "https://api.llama.fi"
DEFILLAMA_YIELDS_BASE_URL = "https://yields.llama.fi"

log = logging.getLogger(__name__)


class DefiLlamaClient:
    """Minimal DefiLlama client. One method (per-protocol Ethereum TVL)."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_protocol_tvl(self, slug: str) -> dict[str, float]:
        """Return {asset_symbol: tvl_usd} for the latest Ethereum snapshot.

        Returns {} on any error (network, missing chain, malformed payload).
        Caller skips that protocol's row for this cron tick.
        """
        try:
            resp = await self._http.get(f"/protocol/{slug}", timeout=20.0)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("defillama %s fetch failed: %s", slug, e)
            return {}

        eth = body.get("chainTvls", {}).get("Ethereum")
        if not eth:
            return {}
        timeseries = eth.get("tokensInUsd") or []
        if not timeseries:
            return {}
        latest = timeseries[-1]
        tokens = latest.get("tokens") or {}
        # Defensive: ensure all values are coercible to float.
        out: dict[str, float] = {}
        for sym, val in tokens.items():
            try:
                out[sym] = float(val)
            except (TypeError, ValueError):
                continue
        return out

    async def fetch_yield_pools(self) -> list[dict]:
        """Return DefiLlama's /yields/pools 'data' array (~10k pools across all
        chains/protocols). Caller filters/sorts. Returns [] on any error.

        NOTE: this hits a DIFFERENT base host than /protocol/{slug}.
        DefiLlama serves yields at https://yields.llama.fi/, distinct from the
        api.llama.fi protocol endpoint. The httpx client passed in must already
        be configured with that base URL.
        """
        try:
            resp = await self._http.get("/pools", timeout=30.0)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("defillama yield pools fetch failed: %s", e)
            return []
        return body.get("data") or []
