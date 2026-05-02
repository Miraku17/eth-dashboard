"""Thin client over the Lighthouse beacon-node HTTP API.

Only exposes what the dashboard actually consumes. v1 = single endpoint:
active validator count.

Beacon HTTP spec: https://ethereum.github.io/beacon-APIs/
"""
import logging
import time

import httpx

log = logging.getLogger(__name__)


class BeaconClient:
    """Minimal Lighthouse beacon-API client. Caches the validator count
    in-process to avoid the ~1.5MB payload cost on repeat calls."""

    def __init__(self, http: httpx.AsyncClient, *, cache_ttl_s: int = 300) -> None:
        self._http = http
        self._cache_ttl_s = cache_ttl_s
        self._cached_count: int | None = None
        self._cached_at: float = 0.0

    async def active_validator_count(self) -> int | None:
        """Count of validators in 'active_ongoing' state at head.

        Returns None on any error so callers can degrade gracefully.
        """
        now = time.monotonic()
        if self._cached_count is not None and (now - self._cached_at) < self._cache_ttl_s:
            return self._cached_count
        try:
            resp = await self._http.get(
                "/eth/v1/beacon/states/head/validators",
                params={"status": "active_ongoing"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            count = len(data)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("beacon validator count failed: %s", e)
            return None
        self._cached_count = count
        self._cached_at = now
        return count
