"""Unit tests for the FIFO realized-PnL engine (pure, no I/O)."""
from decimal import Decimal

import pytest

from app.services.pnl_engine import WalletPnL, compute_realized_pnl


def _row(trader, side, weth, usd, *, t="2026-04-01T00:00:00Z", label=None):
    return {
        "trader": trader,
        "block_time": t,
        "side": side,
        "weth_amount": str(weth),
        "amount_usd": str(usd),
        "label": label,
    }


def test_single_round_trip_profit():
    rows = [
        _row("0xaaa", "buy",  Decimal("10"), Decimal("30000"), t="2026-04-01T00:00:00Z"),
        _row("0xaaa", "sell", Decimal("10"), Decimal("35000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    assert len(result) == 1
    r = result[0]
    assert isinstance(r, WalletPnL)
    assert r.wallet == "0xaaa"
    assert r.realized_pnl_usd == Decimal("5000.00")
    assert r.unrealized_pnl_usd is None        # no open position
    assert r.win_rate == Decimal("1.0000")     # 1/1 winning sell
    assert r.trade_count == 2
    assert r.volume_usd == Decimal("65000.00")
    assert r.weth_bought == Decimal("10")
    assert r.weth_sold == Decimal("10")
