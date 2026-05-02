"""Thin client over the Lighthouse beacon-node HTTP API.

Only exposes what the dashboard actually consumes:
  - active validator count (for the StakingFlowsPanel tile)
  - total ETH staked (sum of active validator balances)

Both come from the same /eth/v1/beacon/states/head/validators payload,
so we fetch once per cache window and derive both numbers.

Beacon HTTP spec: https://ethereum.github.io/beacon-APIs/
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

GWEI_PER_ETH = 1_000_000_000


@dataclass(frozen=True)
class ValidatorSummary:
    """Snapshot of the active validator set."""
    count: int
    total_balance_gwei: int

    @property
    def total_eth(self) -> float:
        return self.total_balance_gwei / GWEI_PER_ETH


class BeaconClient:
    """Minimal Lighthouse beacon-API client. Caches the validator summary
    in-process to avoid the ~1.5MB payload cost on repeat calls."""

    def __init__(self, http: httpx.AsyncClient, *, cache_ttl_s: int = 300) -> None:
        self._http = http
        self._cache_ttl_s = cache_ttl_s
        self._cached_summary: ValidatorSummary | None = None
        self._cached_at: float = 0.0

    async def active_validator_summary(self) -> ValidatorSummary | None:
        """Return active-validator count + total balance at head.

        Sums each validator's `balance` (gwei) from the response payload.
        Returns None on any error so callers can degrade gracefully.
        """
        now = time.monotonic()
        if self._cached_summary is not None and (now - self._cached_at) < self._cache_ttl_s:
            return self._cached_summary
        try:
            resp = await self._http.get(
                "/eth/v1/beacon/states/head/validators",
                params={"status": "active_ongoing"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            count = len(data)
            total_gwei = 0
            for v in data:
                bal = v.get("balance")
                if bal is None:
                    continue
                try:
                    total_gwei += int(bal)
                except (TypeError, ValueError):
                    continue
        except (httpx.HTTPError, ValueError) as e:
            log.warning("beacon validator summary failed: %s", e)
            return None
        summary = ValidatorSummary(count=count, total_balance_gwei=total_gwei)
        self._cached_summary = summary
        self._cached_at = now
        return summary

    async def active_validator_count(self) -> int | None:
        """Back-compat shim — returns just the count from active_validator_summary()."""
        s = await self.active_validator_summary()
        return s.count if s is not None else None
