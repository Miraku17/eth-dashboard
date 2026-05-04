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

    # ─── v4 beacon-flows: block-level reads (replaces Dune staking_flows) ───

    async def finalized_slot(self) -> int | None:
        """Return the slot number of the finalized head, or None on error."""
        try:
            resp = await self._http.get(
                "/eth/v1/beacon/headers/finalized", timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            slot = data.get("header", {}).get("message", {}).get("slot")
            return int(slot) if slot is not None else None
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.warning("beacon finalized_slot failed: %s", e)
            return None

    async def block_flows(self, slot: int) -> dict | None:
        """Return a slim summary of value flows in the beacon block at `slot`:

            {
                "ts": <execution payload timestamp, unix seconds>,
                "deposits": [(amount_gwei, withdrawal_address | None), ...],
                "withdrawals": [(amount_gwei, validator_index, address | None), ...],
            }

        Each deposit / withdrawal carries the ETH address it ultimately
        credits (deposit credential's last 20 bytes for type-01 creds;
        withdrawal `address` field directly). The v4 entity-attribution
        path joins those addresses against `address_label`.

        Skipped slots (no block proposed) return None. Caller handles None
        by advancing the cursor without writing.

        Lighthouse's /eth/v2/beacon/blocks/{slot} returns either:
          - 200 with the block body
          - 404 when the slot was missed (no proposer signed a block)
        Both are normal on mainnet (~5% missed-slot rate).
        """
        try:
            resp = await self._http.get(
                f"/eth/v2/beacon/blocks/{slot}", timeout=15.0
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            body = resp.json().get("data", {}).get("message", {}).get("body", {}) or {}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("beacon block %d fetch failed: %s", slot, e)
            return None

        deposits: list[tuple[int, str | None]] = []
        for d in body.get("deposits") or []:
            data = d.get("data") or {}
            amount = data.get("amount")
            wc = data.get("withdrawal_credentials") or ""
            if amount is None:
                continue
            try:
                amt_gwei = int(amount)
            except (TypeError, ValueError):
                continue
            if amt_gwei <= 0:
                continue
            # Type-01 credentials: 0x01 + 11 zero bytes + 20-byte address.
            # Type-00 credentials (legacy BLS) carry no ETH address — we
            # leave addr=None and the cron buckets those as "Unattributed".
            addr: str | None = None
            if isinstance(wc, str) and wc.startswith("0x") and len(wc) == 66:
                if wc[2:4].lower() == "01":
                    addr = "0x" + wc[26:].lower()
            deposits.append((amt_gwei, addr))

        ep = body.get("execution_payload") or {}
        withdrawals: list[tuple[int, int, str | None]] = []
        for w in ep.get("withdrawals") or []:
            try:
                amt = int(w.get("amount") or 0)
                vi = int(w.get("validator_index") or 0)
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            wa = w.get("address")
            addr = (
                wa.lower() if isinstance(wa, str) and wa.startswith("0x") else None
            )
            withdrawals.append((amt, vi, addr))

        ts = ep.get("timestamp")
        try:
            ts_int = int(ts) if ts is not None else 0
        except (TypeError, ValueError):
            ts_int = 0

        return {
            "ts": ts_int,
            "deposits": deposits,
            "withdrawals": withdrawals,
        }
