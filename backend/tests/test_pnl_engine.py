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


def test_single_round_trip_loss():
    rows = [
        _row("0xbbb", "buy",  Decimal("10"), Decimal("35000")),
        _row("0xbbb", "sell", Decimal("10"), Decimal("30000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3000"))
    assert result[0].realized_pnl_usd == Decimal("-5000.00")
    assert result[0].win_rate == Decimal("0.0000")


def test_partial_close_leaves_open_position():
    rows = [
        _row("0xccc", "buy",  Decimal("10"), Decimal("30000")),
        _row("0xccc", "sell", Decimal("4"),  Decimal("14000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3600"))
    r = result[0]
    # Cost basis of 4 WETH = 4/10 * 30000 = 12000. Proceeds = 14000. Realized = 2000.
    assert r.realized_pnl_usd == Decimal("2000.00")
    # 6 WETH open at avg cost 3000. Mark at 3600. Unrealized = 6 * 600 = 3600.
    assert r.unrealized_pnl_usd == Decimal("3600.00")
    assert r.weth_bought == Decimal("10")
    assert r.weth_sold == Decimal("4")


def test_multi_lot_fifo_order():
    rows = [
        _row("0xddd", "buy",  Decimal("5"), Decimal("10000"),  t="2026-04-01T00:00:00Z"),
        _row("0xddd", "buy",  Decimal("5"), Decimal("15000"),  t="2026-04-02T00:00:00Z"),
        _row("0xddd", "sell", Decimal("7"), Decimal("21000"),  t="2026-04-03T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3100"))
    r = result[0]
    # First lot fully consumed: cost=10000, proceeds=5/7*21000=15000, pnl=+5000.
    # Next 2 WETH from second lot: cost=2/5*15000=6000, proceeds=2/7*21000=6000, pnl=0.
    # Realized = 5000. Open = 3 WETH at cost 9000 (3/5*15000). Mark 3100 → 9300. Unrealized = 300.
    assert r.realized_pnl_usd == Decimal("5000.00")
    assert r.unrealized_pnl_usd == Decimal("300.00")


def test_sell_without_prior_buy_skipped():
    rows = [
        # This sell has no preceding buy in the window — pre-window inventory.
        _row("0xeee", "sell", Decimal("10"), Decimal("35000"), t="2026-04-01T00:00:00Z"),
        _row("0xeee", "buy",  Decimal("5"),  Decimal("15000"), t="2026-04-02T00:00:00Z"),
        _row("0xeee", "sell", Decimal("5"),  Decimal("17500"), t="2026-04-03T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    # Only the second round-trip counts: cost=15000, proceeds=17500 → 2500.
    # First sell hit empty deque, fully skipped, not counted toward win_rate.
    assert r.realized_pnl_usd == Decimal("2500.00")
    assert r.win_rate == Decimal("1.0000")  # 1 counted sell, 1 win
    assert r.trade_count == 3               # all rows counted as activity
    assert r.unrealized_pnl_usd is None     # no open position at end


def test_buy_only_wallet():
    rows = [
        _row("0xfff", "buy", Decimal("3"), Decimal("9000"), t="2026-04-01T00:00:00Z"),
        _row("0xfff", "buy", Decimal("2"), Decimal("6200"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3200"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.win_rate is None               # no closed round-trips
    # 5 WETH open at avg cost (9000+6200)/5 = 3040. Mark 3200 → 16000. Unrealized = 800.
    assert r.unrealized_pnl_usd == Decimal("800.00")


def test_sell_only_wallet():
    rows = [
        _row("0x111", "sell", Decimal("3"), Decimal("10500"), t="2026-04-01T00:00:00Z"),
        _row("0x111", "sell", Decimal("2"), Decimal("7000"),  t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.win_rate is None           # 0 counted closed round-trips
    assert r.unrealized_pnl_usd is None # nothing opened in window
    assert r.trade_count == 2
    assert r.weth_sold == Decimal("5")
    assert r.weth_bought == Decimal("0")


def test_flipper_win_rate_arithmetic():
    rows = [
        _row("0x222", "buy",  Decimal("1"), Decimal("3000"), t="2026-04-01T00:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3100"), t="2026-04-01T01:00:00Z"),  # +100
        _row("0x222", "buy",  Decimal("1"), Decimal("3100"), t="2026-04-01T02:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3050"), t="2026-04-01T03:00:00Z"),  # -50
        _row("0x222", "buy",  Decimal("1"), Decimal("3050"), t="2026-04-01T04:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3200"), t="2026-04-01T05:00:00Z"),  # +150
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3200"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("200.00")
    assert r.win_rate == Decimal("0.6667")  # 2 wins / 3 sells
    assert r.trade_count == 6
    assert r.unrealized_pnl_usd is None


def test_decimal_precision_preserved():
    rows = [
        _row("0x333", "buy",  Decimal("1.123456789012345678"), Decimal("3500.00")),
        _row("0x333", "sell", Decimal("1.123456789012345678"), Decimal("3600.00"),
             t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3600"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("100.00")
    # weth_bought/sold preserve 18-decimal precision unchanged
    assert r.weth_bought == Decimal("1.123456789012345678")
    assert r.weth_sold == Decimal("1.123456789012345678")


def test_multi_wallet_produces_one_record_per_wallet():
    rows = [
        _row("0xaaa", "buy",  Decimal("1"), Decimal("3000"), t="2026-04-01T00:00:00Z"),
        _row("0xaaa", "sell", Decimal("1"), Decimal("3100"), t="2026-04-02T00:00:00Z"),
        _row("0xbbb", "buy",  Decimal("2"), Decimal("6000"), t="2026-04-01T00:00:00Z"),
        _row("0xbbb", "sell", Decimal("2"), Decimal("5800"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3000"))
    by_wallet = {r.wallet: r for r in result}
    assert set(by_wallet) == {"0xaaa", "0xbbb"}
    assert by_wallet["0xaaa"].realized_pnl_usd == Decimal("100.00")
    assert by_wallet["0xbbb"].realized_pnl_usd == Decimal("-200.00")


def test_wallet_address_normalized_to_lowercase():
    """Wallet addresses from Dune may arrive in mixed case; engine stores lowercase."""
    rows = [
        _row("0xABC", "buy",  Decimal("1"), Decimal("3000"), t="2026-04-01T00:00:00Z"),
        _row("0xABC", "sell", Decimal("1"), Decimal("3100"), t="2026-04-02T00:00:00Z"),
        _row("0xDeF", "buy",  Decimal("2"), Decimal("6000"), t="2026-04-01T00:00:00Z"),
        _row("0xdEf", "sell", Decimal("2"), Decimal("6200"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3100"))
    wallets = {r.wallet for r in result}
    assert wallets == {"0xabc", "0xdef"}
    # Mixed-case duplicate 0xDeF / 0xdEf should be grouped as one wallet.
    by_wallet = {r.wallet: r for r in result}
    assert by_wallet["0xdef"].realized_pnl_usd == Decimal("200.00")
    assert by_wallet["0xdef"].trade_count == 2


# ---------- compute_aggregate_pnl ----------


def _agg(trader, *, weth_bought="0", weth_sold="0", usd_spent="0", usd_received="0",
         trade_count=0, label=None):
    return {
        "trader": trader,
        "weth_bought": weth_bought,
        "weth_sold": weth_sold,
        "usd_spent": usd_spent,
        "usd_received": usd_received,
        "trade_count": trade_count,
        "label": label,
    }


def test_aggregate_fully_closed_round_trip():
    from app.services.pnl_engine import compute_aggregate_pnl

    rows = [_agg("0xaaa", weth_bought="10", weth_sold="10",
                 usd_spent="30000", usd_received="35000", trade_count=42)]
    result = compute_aggregate_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    # avg_buy = 3000, avg_sell = 3500, closed = 10 → realized = 5000.
    assert r.realized_pnl_usd == Decimal("5000.00")
    assert r.unrealized_pnl_usd is None  # fully closed
    assert r.win_rate is None
    assert r.trade_count == 42
    assert r.volume_usd == Decimal("65000.00")


def test_aggregate_partial_close_with_open_position():
    from app.services.pnl_engine import compute_aggregate_pnl

    rows = [_agg("0xccc", weth_bought="10", weth_sold="4",
                 usd_spent="30000", usd_received="14000", trade_count=5)]
    result = compute_aggregate_pnl(rows, window_end_eth_price=Decimal("3600"))
    r = result[0]
    # avg_buy = 3000, avg_sell = 3500, closed = 4 → realized = 4 * 500 = 2000.
    # Open = 10 - 4 = 6 WETH at avg cost 3000, mark 3600 → 6 * 600 = 3600.
    assert r.realized_pnl_usd == Decimal("2000.00")
    assert r.unrealized_pnl_usd == Decimal("3600.00")


def test_aggregate_sell_only_has_no_realizable_pnl():
    from app.services.pnl_engine import compute_aggregate_pnl

    rows = [_agg("0xdead", weth_bought="0", weth_sold="5",
                 usd_spent="0", usd_received="17500", trade_count=2)]
    result = compute_aggregate_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    # No in-window buys → no cost basis → realized pins at 0.
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.unrealized_pnl_usd is None  # net short after window


def test_aggregate_buy_only_unrealized_only():
    from app.services.pnl_engine import compute_aggregate_pnl

    rows = [_agg("0xbull", weth_bought="5", weth_sold="0",
                 usd_spent="15200", usd_received="0", trade_count=3)]
    result = compute_aggregate_pnl(rows, window_end_eth_price=Decimal("3200"))
    r = result[0]
    # No sells → realized 0. avg_buy = 3040. Open 5 WETH × (3200 - 3040) = 800.
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.unrealized_pnl_usd == Decimal("800.00")


def test_aggregate_normalizes_wallet_lowercase():
    from app.services.pnl_engine import compute_aggregate_pnl

    rows = [_agg("0xABCdef", weth_bought="1", weth_sold="1",
                 usd_spent="3000", usd_received="3100", trade_count=2)]
    result = compute_aggregate_pnl(rows, window_end_eth_price=None)
    assert result[0].wallet == "0xabcdef"
