"""Per-wallet performance scoring engine.

Pure compute: takes a list of Swap rows and returns one set of metrics
per wallet. Run by the daily wallet-scoring cron over the last 30d of
`dex_swap` data.

Algorithm:
  * Buys add a lot to the wallet's WETH inventory ((qty, total_usd_cost)).
  * Sells consume earliest unmatched lots FIFO; each sell yields a
    realized PnL = (proceeds_per_weth - cost_per_weth) × qty_consumed.
  * win_rate = sells with positive realized PnL / total sells with
    matched inventory. Sells against empty inventory (short-style)
    skip the PnL accounting — we don't track shorts.
  * volume_usd = sum of |usd_value| across all swaps.
  * trades = total swap count.

Score: realized_pnl is the primary sort key in v1. The daily cron upserts
into `wallet_score`; the panel reads top-N by score for "smart money"
display.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class SwapRow:
    """Subset of dex_swap a scorer cares about. Constructed by the cron
    from the SQL result set so the compute is decoupled from the ORM."""
    ts: datetime
    side: str           # 'buy' | 'sell'
    weth_amount: float
    usd_value: float


@dataclass
class WalletMetrics:
    trades: int = 0
    volume_usd: float = 0.0
    realized_pnl: float = 0.0
    sells_with_inventory: int = 0
    sells_profitable: int = 0

    @property
    def win_rate(self) -> float | None:
        # Need a minimum sample size for a meaningful rate. <3 closed
        # round-trips and we report None — the panel renders that as
        # 'insufficient history' rather than misleading 100% / 0%.
        if self.sells_with_inventory < 3:
            return None
        return self.sells_profitable / self.sells_with_inventory


def score_wallet(swaps: Iterable[SwapRow]) -> WalletMetrics:
    """Run the FIFO matcher over a single wallet's chronological swaps.

    Caller is responsible for pre-sorting by `ts` ascending. Mixing wallets
    in the input would corrupt the inventory; the cron groups upstream.
    """
    metrics = WalletMetrics()
    # Each lot: [remaining_weth, remaining_usd_cost]. Lists (not tuples) so
    # we can mutate in place during partial fills.
    inventory: list[list[float]] = []

    for s in swaps:
        metrics.trades += 1
        metrics.volume_usd += abs(s.usd_value)

        if s.weth_amount <= 0 or s.usd_value <= 0:
            continue

        if s.side == "buy":
            inventory.append([s.weth_amount, s.usd_value])
            continue

        if s.side != "sell":
            continue

        # Sell — consume FIFO.
        if not inventory:
            # No prior buy to match against. Skip PnL accounting for this
            # sell rather than treat it as a short. Future revision could
            # track shorts; v1 doesn't.
            continue

        proceeds_per_weth = s.usd_value / s.weth_amount
        remaining = s.weth_amount
        round_trip_pnl = 0.0
        while remaining > 0 and inventory:
            held_qty, held_cost = inventory[0]
            cost_per_weth = held_cost / held_qty if held_qty > 0 else 0
            if held_qty <= remaining:
                # Fully consume this lot.
                round_trip_pnl += (proceeds_per_weth - cost_per_weth) * held_qty
                remaining -= held_qty
                inventory.pop(0)
            else:
                # Partial fill — split the lot.
                round_trip_pnl += (proceeds_per_weth - cost_per_weth) * remaining
                share_consumed = remaining / held_qty
                inventory[0][0] = held_qty - remaining
                inventory[0][1] = held_cost * (1 - share_consumed)
                remaining = 0

        metrics.realized_pnl += round_trip_pnl
        metrics.sells_with_inventory += 1
        if round_trip_pnl > 0:
            metrics.sells_profitable += 1

    return metrics


def score_all_wallets(
    swaps_by_wallet: dict[str, list[SwapRow]],
) -> dict[str, WalletMetrics]:
    """Convenience entrypoint — applies score_wallet to every wallet's
    pre-grouped chronological list. Returns a fresh dict; doesn't mutate
    the input."""
    out: dict[str, WalletMetrics] = {}
    for wallet, swaps in swaps_by_wallet.items():
        out[wallet] = score_wallet(swaps)
    return out


def group_swaps(swaps: Iterable[SwapRow], wallets: Iterable[str]) -> dict[str, list[SwapRow]]:
    """Bucket a flat (wallet, SwapRow) iterator into per-wallet lists,
    sorted ascending by ts. Caller passes a parallel `wallets` iterable.
    """
    buckets: dict[str, list[SwapRow]] = defaultdict(list)
    for w, s in zip(wallets, swaps, strict=True):
        buckets[w].append(s)
    for w, rows in buckets.items():
        rows.sort(key=lambda r: r.ts)
    return dict(buckets)
