"""Async wrapper around Etherscan's REST API. Used by wallet clustering.

Etherscan free tier: 5 req/s, 100k req/day. We cap concurrency at 4 via an
internal semaphore (see EtherscanClient.__init__). Soft-fail with typed
exceptions so callers can serve stale cache during outages.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

ETHERSCAN_BASE_URL = "https://api.etherscan.io"

log = logging.getLogger(__name__)


class EtherscanRateLimited(RuntimeError):
    pass


class EtherscanUnavailable(RuntimeError):
    pass


class EtherscanClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str, *, max_concurrency: int = 4) -> None:
        self._http = http
        self._api_key = api_key
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _get(
        self,
        params: dict[str, Any],
        *,
        _max_attempts: int = 3,
        _backoff_s: float = 0.5,
    ) -> list[dict] | dict:
        params = {**params, "apikey": self._api_key}
        attempt = 0
        async with self._sem:
            while True:
                attempt += 1
                try:
                    r = await self._http.get("/api", params=params)
                except httpx.HTTPError as e:
                    if attempt >= _max_attempts:
                        raise EtherscanUnavailable(str(e)) from e
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                if r.status_code >= 500:
                    if attempt >= _max_attempts:
                        raise EtherscanUnavailable(f"HTTP {r.status_code}")
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                if r.status_code == 429:
                    if attempt >= _max_attempts:
                        raise EtherscanRateLimited("HTTP 429")
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                r.raise_for_status()
                body = r.json()

                # Etherscan returns 200 with status "0" for both "no results" and rate limits.
                if body.get("status") == "0":
                    msg = str(body.get("message", "")).lower()
                    res = body.get("result")
                    if msg == "no transactions found":
                        return []
                    if isinstance(res, str) and "rate limit" in res.lower():
                        if attempt >= _max_attempts:
                            raise EtherscanRateLimited(res)
                        await asyncio.sleep(_backoff_s * attempt)
                        continue
                    # Other "0" with empty result list — treat as empty.
                    if isinstance(res, list):
                        return res
                    raise EtherscanUnavailable(f"unexpected response: {body!r}")

                return body.get("result", [])

    async def txlist(
        self,
        address: str,
        *,
        startblock: int = 0,
        endblock: int = 99_999_999,
        sort: str = "asc",
        page: int = 1,
        offset: int = 100,
        **kwargs: Any,
    ) -> list[dict]:
        return await self._get(
            {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": startblock,
                "endblock": endblock,
                "sort": sort,
                "page": page,
                "offset": offset,
            },
            **kwargs,
        )

    async def txlistinternal(self, address: str, **kwargs: Any) -> list[dict]:
        return await self._get(
            {
                "module": "account",
                "action": "txlistinternal",
                "address": address,
                "sort": "asc",
                "page": 1,
                "offset": 50,
            },
            **kwargs,
        )

    async def tokentx(
        self,
        address: str,
        *,
        contract_address: str | None = None,
        sort: str = "desc",
        page: int = 1,
        offset: int = 100,
        **kwargs: Any,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "sort": sort,
            "page": page,
            "offset": offset,
        }
        if contract_address:
            params["contractaddress"] = contract_address
        return await self._get(params, **kwargs)
