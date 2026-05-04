"""Self-contained tests for the FIFO wallet-scoring engine.

Pure unit tests; no DB. Can run anywhere with the backend code on path.
Run: docker compose exec -T worker python < scripts/test-wallet-scoring.py
"""
from datetime import UTC, datetime, timedelta

from app.services.wallet_scoring import SwapRow, score_wallet


def _at(minutes: int) -> datetime:
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def test_simple_profitable_round_trip() -> None:
    swaps = [
        SwapRow(_at(0),  "buy",  weth_amount=1.0, usd_value=2000.0),  # cost 2000/WETH
        SwapRow(_at(60), "sell", weth_amount=1.0, usd_value=2500.0),  # proceeds 2500/WETH
    ]
    m = score_wallet(swaps)
    assert m.realized_pnl == 500.0, m.realized_pnl
    assert m.trades == 2, m.trades
    assert m.volume_usd == 4500.0, m.volume_usd
    assert m.sells_with_inventory == 1
    assert m.sells_profitable == 1
    print("PASS: simple profitable round trip")


def test_simple_losing_round_trip() -> None:
    swaps = [
        SwapRow(_at(0),  "buy",  1.0, 2500.0),
        SwapRow(_at(60), "sell", 1.0, 2000.0),
    ]
    m = score_wallet(swaps)
    assert m.realized_pnl == -500.0
    assert m.sells_with_inventory == 1
    assert m.sells_profitable == 0
    print("PASS: simple losing round trip")


def test_fifo_partial_fill() -> None:
    # Buy 2 ETH @ $1500, then 2 ETH @ $2500. Sell 3 ETH @ $3000.
    # Sell consumes lot1 (2 ETH @ $1500 cost) fully, then 1 ETH from lot2 (@ $2500 cost).
    # Proceeds per WETH on sell = 3000.
    # PnL = (3000 - 1500)*2 + (3000 - 2500)*1 = 3000 + 500 = 3500
    swaps = [
        SwapRow(_at(0),  "buy",  2.0, 3000.0),   # avg $1500/ETH
        SwapRow(_at(30), "buy",  2.0, 5000.0),   # avg $2500/ETH
        SwapRow(_at(60), "sell", 3.0, 9000.0),   # proceeds $3000/ETH
    ]
    m = score_wallet(swaps)
    assert abs(m.realized_pnl - 3500.0) < 0.01, m.realized_pnl
    assert m.sells_with_inventory == 1
    print(f"PASS: FIFO partial fill (PnL={m.realized_pnl:.2f})")


def test_sell_without_inventory_is_skipped() -> None:
    # Sell first (no buys yet) — doesn't blow up; just no PnL accounting.
    swaps = [
        SwapRow(_at(0),  "sell", 1.0, 2000.0),
        SwapRow(_at(60), "buy",  1.0, 2000.0),
        SwapRow(_at(120), "sell", 1.0, 2500.0),
    ]
    m = score_wallet(swaps)
    # Only second sell is matched: PnL = (2500 - 2000) * 1 = 500
    assert m.realized_pnl == 500.0
    assert m.trades == 3
    assert m.sells_with_inventory == 1  # only the matched sell
    assert m.sells_profitable == 1
    print("PASS: orphan sell is skipped")


def test_win_rate_requires_min_samples() -> None:
    # 2 round trips (both wins): below 3-sample threshold → win_rate=None
    swaps = [
        SwapRow(_at(0),   "buy",  1.0, 1000.0),
        SwapRow(_at(10),  "sell", 1.0, 1100.0),
        SwapRow(_at(20),  "buy",  1.0, 1000.0),
        SwapRow(_at(30),  "sell", 1.0, 1200.0),
    ]
    m = score_wallet(swaps)
    assert m.win_rate is None, m.win_rate
    assert m.sells_profitable == 2
    print("PASS: win_rate=None below sample threshold")


def test_win_rate_with_enough_samples() -> None:
    # 5 round trips, 3 wins → 60%
    swaps: list[SwapRow] = []
    for i in range(5):
        swaps.append(SwapRow(_at(i * 100), "buy", 1.0, 1000.0))
        proceeds = 1100.0 if i < 3 else 900.0
        swaps.append(SwapRow(_at(i * 100 + 50), "sell", 1.0, proceeds))
    m = score_wallet(swaps)
    assert m.sells_with_inventory == 5
    assert m.sells_profitable == 3
    assert abs(m.win_rate - 0.6) < 1e-6, m.win_rate
    print(f"PASS: win_rate={m.win_rate:.2f} (expected 0.60)")


for fn in [
    test_simple_profitable_round_trip,
    test_simple_losing_round_trip,
    test_fifo_partial_fill,
    test_sell_without_inventory_is_skipped,
    test_win_rate_requires_min_samples,
    test_win_rate_with_enough_samples,
]:
    fn()

print("\nAll wallet-scoring tests passed.")
