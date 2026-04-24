"""Pure FIFO realized-PnL engine.

Takes raw Dune trade rows for multiple wallets (already sorted by
(trader, block_time)) and produces a ranked list of per-wallet PnL records.
No I/O — fully deterministic given its inputs.
"""
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque


@dataclass(frozen=True)
class WalletPnL:
    wallet: str
    label: str | None
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal | None
    win_rate: Decimal | None
    trade_count: int
    volume_usd: Decimal
    weth_bought: Decimal
    weth_sold: Decimal


def _d(x) -> Decimal:
    """Safe conversion from Dune output (str/float/int) to Decimal."""
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def compute_aggregate_pnl(
    rows: list[dict],
    window_end_eth_price: Decimal | None,
) -> list[WalletPnL]:
    """Compute per-wallet approximate realized PnL from aggregate Dune rows.

    Each input row must have: trader, weth_bought, weth_sold, usd_spent,
    usd_received, trade_count, label.

    Formula: realized = min(weth_bought, weth_sold) * (avg_sell - avg_buy),
    where avg_buy = usd_spent / weth_bought and avg_sell = usd_received /
    weth_sold. Exact for wallets that fully closed their position in the
    window; directionally correct for partial closes. Win-rate is not
    computable from aggregates — always returned as None.

    Used when the Dune free-tier `/results` datapoint budget makes the
    per-trade FIFO path (see `compute_realized_pnl`) economically infeasible.
    """
    out: list[WalletPnL] = []
    for r in rows:
        trader = str(r["trader"]).lower()
        weth_bought = _d(r.get("weth_bought"))
        weth_sold = _d(r.get("weth_sold"))
        usd_spent = _d(r.get("usd_spent"))
        usd_received = _d(r.get("usd_received"))
        trade_count = int(r.get("trade_count") or 0)
        label = r.get("label")
        volume_usd = usd_spent + usd_received

        avg_buy = (usd_spent / weth_bought) if weth_bought > 0 else None
        avg_sell = (usd_received / weth_sold) if weth_sold > 0 else None

        if weth_bought > 0 and weth_sold > 0 and avg_buy is not None and avg_sell is not None:
            closed_weth = min(weth_bought, weth_sold)
            realized = closed_weth * (avg_sell - avg_buy)
        else:
            # Pre-window inventory (sell-only) or open position (buy-only):
            # no in-window round-trip to realize.
            realized = Decimal("0")

        unrealized: Decimal | None = None
        if weth_bought > weth_sold and avg_buy is not None and window_end_eth_price is not None:
            open_weth = weth_bought - weth_sold
            unrealized = open_weth * (window_end_eth_price - avg_buy)

        out.append(WalletPnL(
            wallet=trader,
            label=label,
            realized_pnl_usd=realized.quantize(Decimal("0.01")),
            unrealized_pnl_usd=unrealized.quantize(Decimal("0.01")) if unrealized is not None else None,
            win_rate=None,  # not derivable from aggregates
            trade_count=trade_count,
            volume_usd=volume_usd.quantize(Decimal("0.01")),
            weth_bought=weth_bought,
            weth_sold=weth_sold,
        ))
    return out


def _process_wallet(
    wallet: str,
    label: str | None,
    trades: list[dict],
    window_end_eth_price: Decimal | None,
) -> WalletPnL:
    lots: Deque[list[Decimal]] = deque()  # each lot is [weth_remaining, usd_cost_remaining]
    realized = Decimal("0")
    wins = 0
    losses = 0
    volume_usd = Decimal("0")
    weth_bought = Decimal("0")
    weth_sold = Decimal("0")

    for tr in trades:
        weth = _d(tr["weth_amount"])
        usd = _d(tr["amount_usd"])
        volume_usd += usd
        side = tr["side"]

        if side == "buy":
            weth_bought += weth
            lots.append([weth, usd])
        elif side == "sell":
            weth_sold += weth
            to_close = weth
            sell_price = usd / weth if weth > 0 else Decimal("0")
            sell_realized = Decimal("0")
            consumed_any = False
            while to_close > 0 and lots:
                lot_weth, lot_cost = lots[0]
                consumed = min(lot_weth, to_close)
                cost_basis = lot_cost * (consumed / lot_weth) if lot_weth > 0 else Decimal("0")
                proceeds = sell_price * consumed
                sell_realized += proceeds - cost_basis
                lot_weth -= consumed
                lot_cost -= cost_basis
                to_close -= consumed
                consumed_any = True
                if lot_weth == 0:
                    lots.popleft()
                else:
                    lots[0] = [lot_weth, lot_cost]
            # Any leftover `to_close` > 0 here is pre-window inventory: skip.
            if consumed_any:
                realized += sell_realized
                if sell_realized > 0:
                    wins += 1
                else:
                    losses += 1

    # Unrealized mark-to-market on any open position.
    unrealized: Decimal | None = None
    if lots and window_end_eth_price is not None:
        open_weth = sum((lot[0] for lot in lots), Decimal("0"))
        open_cost = sum((lot[1] for lot in lots), Decimal("0"))
        if open_weth > 0:
            avg_cost_per_weth = open_cost / open_weth
            unrealized = (window_end_eth_price - avg_cost_per_weth) * open_weth

    total_closed = wins + losses
    win_rate = (Decimal(wins) / Decimal(total_closed)) if total_closed > 0 else None

    return WalletPnL(
        wallet=wallet,
        label=label,
        realized_pnl_usd=realized.quantize(Decimal("0.01")),
        unrealized_pnl_usd=unrealized.quantize(Decimal("0.01")) if unrealized is not None else None,
        win_rate=win_rate.quantize(Decimal("0.0001")) if win_rate is not None else None,
        trade_count=len(trades),
        volume_usd=volume_usd.quantize(Decimal("0.01")),
        weth_bought=weth_bought,
        weth_sold=weth_sold,
    )


def compute_realized_pnl(
    rows: list[dict],
    window_end_eth_price: Decimal | None,
) -> list[WalletPnL]:
    """Group rows by wallet, compute FIFO PnL, return a list.

    Caller is responsible for sorting `rows` by (trader, block_time). The
    Dune query's `ORDER BY t.trader, t.block_time` clause handles this.
    """
    out: list[WalletPnL] = []
    if not rows:
        return out

    current_trader = rows[0]["trader"].lower()
    current_label = rows[0].get("label")
    buf: list[dict] = []
    for r in rows:
        trader = r["trader"].lower()
        if trader != current_trader:
            out.append(_process_wallet(current_trader, current_label, buf, window_end_eth_price))
            current_trader = trader
            current_label = r.get("label")
            buf = []
        buf.append(r)
    out.append(_process_wallet(current_trader, current_label, buf, window_end_eth_price))
    return out
