"""Per-wallet 90d FIFO scoring of GMX V2 perp activity.

Pure compute. The cron in workers/perp_scoring_jobs.py is responsible for
loading events out of `onchain_perp_event` and persisting results to
`perp_wallet_score`. This module knows nothing about the DB.

FIFO model
----------
Per (market, side) we maintain a queue of lots, each a tuple of
(remaining_size_usd, open_ts). open + increase append to the queue;
close / decrease / liquidation pop lots from the head, partially or fully
consuming each. PnL is supplied by the event (decoded upstream) and
proportionally allocated when a close splits across lots.

Orphan closes (close with empty inventory) are silently dropped — the
wallet was already trading before the 90d window, so we cannot fairly
attribute a P/L outcome.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

LEADERBOARD_LOOKBACK_DAYS = 90
LEADERBOARD_MIN_TRADES = 30
LEADERBOARD_MIN_WIN_RATE = Decimal("0.60")
LEADERBOARD_MIN_PNL_USD = Decimal("10000")
DEFAULT_WATCH_NOTIONAL_USD = Decimal("25000")

OPEN_KINDS = {"open", "increase"}
CLOSE_KINDS = {"close", "decrease", "liquidation"}


@dataclass(frozen=True)
class PerpEvent:
    ts: datetime
    market: str
    side: str           # "long" | "short"
    event_kind: str     # open | increase | close | decrease | liquidation
    size_usd: Decimal
    price_usd: Decimal
    leverage: Decimal
    pnl_usd: Decimal | None  # NULL on opens/increases


@dataclass
class WalletStats:
    trades_90d: int = 0
    win_rate_90d: Decimal = Decimal("0.0000")
    win_rate_long_90d: Decimal | None = None
    win_rate_short_90d: Decimal | None = None
    realized_pnl_90d: Decimal = Decimal("0.00")
    avg_hold_secs: int = 0
    avg_position_usd: Decimal = Decimal("0.00")
    avg_leverage: Decimal = Decimal("0.00")


@dataclass
class _RoundTrip:
    side: str
    notional_usd: Decimal
    leverage: Decimal
    pnl_usd: Decimal
    hold_secs: int


def score_wallet(events: Iterable[PerpEvent]) -> WalletStats:
    events = sorted(events, key=lambda e: e.ts)
    # inventory: key = (market, side) → list of [remaining_size, open_ts, leverage]
    inventory: dict[tuple[str, str], list[list]] = defaultdict(list)
    trips: list[_RoundTrip] = []

    for ev in events:
        key = (ev.market, ev.side)
        if ev.event_kind in OPEN_KINDS:
            inventory[key].append([ev.size_usd, ev.ts, ev.leverage])
            continue
        if ev.event_kind not in CLOSE_KINDS:
            continue
        # Close path: pop FIFO until size_usd is consumed.
        remaining = ev.size_usd
        # PnL is reported on the whole close; allocate proportionally per lot.
        total_pnl = ev.pnl_usd or Decimal("0")
        consumed_total = ev.size_usd if ev.size_usd > 0 else Decimal("1")
        while remaining > 0 and inventory[key]:
            lot = inventory[key][0]
            take = min(remaining, lot[0])
            share = take / consumed_total
            trips.append(
                _RoundTrip(
                    side=ev.side,
                    notional_usd=take,
                    leverage=lot[2],
                    pnl_usd=(total_pnl * share).quantize(Decimal("0.01")),
                    hold_secs=int((ev.ts - lot[1]).total_seconds()),
                )
            )
            lot[0] -= take
            remaining -= take
            if lot[0] <= 0:
                inventory[key].pop(0)
        # remaining > 0 → orphan portion: silently drop.

    return _aggregate(trips)


def _aggregate(trips: list[_RoundTrip]) -> WalletStats:
    if not trips:
        return WalletStats()
    n = len(trips)
    wins = sum(1 for t in trips if t.pnl_usd > 0)
    longs = [t for t in trips if t.side == "long"]
    shorts = [t for t in trips if t.side == "short"]
    pnl = sum((t.pnl_usd for t in trips), Decimal("0"))
    hold_total = sum(t.hold_secs for t in trips)
    notional_total = sum((t.notional_usd for t in trips), Decimal("0"))
    leverage_total = sum((t.leverage for t in trips), Decimal("0"))

    def _wr(sub: list[_RoundTrip]) -> Decimal | None:
        if not sub:
            return None
        w = sum(1 for t in sub if t.pnl_usd > 0)
        return (Decimal(w) / Decimal(len(sub))).quantize(Decimal("0.0001"))

    return WalletStats(
        trades_90d=n,
        win_rate_90d=(Decimal(wins) / Decimal(n)).quantize(Decimal("0.0001")),
        win_rate_long_90d=_wr(longs),
        win_rate_short_90d=_wr(shorts),
        realized_pnl_90d=pnl.quantize(Decimal("0.01")),
        avg_hold_secs=int(hold_total / n),
        avg_position_usd=(notional_total / Decimal(n)).quantize(Decimal("0.01")),
        avg_leverage=(leverage_total / Decimal(n)).quantize(Decimal("0.01")),
    )
