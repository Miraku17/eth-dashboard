"""Unit tests for the perp FIFO scoring kernel."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.perp_scoring import (
    PerpEvent,
    score_wallet,
)


def _ts(minutes: int) -> datetime:
    return datetime(2026, 5, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _ev(kind, side, size, price, leverage, mins, pnl=None):
    return PerpEvent(
        ts=_ts(mins),
        market="ETH-USD",
        side=side,
        event_kind=kind,
        size_usd=Decimal(size),
        price_usd=Decimal(price),
        leverage=Decimal(leverage),
        pnl_usd=None if pnl is None else Decimal(pnl),
    )


def test_profitable_long_round_trip():
    events = [
        _ev("open", "long", "50000", "3000", "10", 0),
        _ev("close", "long", "50000", "3100", "10", 15, pnl="1666"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.win_rate_90d == Decimal("1.0000")
    assert stats.win_rate_long_90d == Decimal("1.0000")
    assert stats.win_rate_short_90d is None
    assert stats.realized_pnl_90d == Decimal("1666.00")
    assert stats.avg_hold_secs == 15 * 60


def test_losing_short_round_trip():
    events = [
        _ev("open", "short", "30000", "3000", "5", 0),
        _ev("close", "short", "30000", "3100", "5", 8, pnl="-1000"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.win_rate_90d == Decimal("0.0000")
    assert stats.win_rate_short_90d == Decimal("0.0000")
    assert stats.win_rate_long_90d is None
    assert stats.realized_pnl_90d == Decimal("-1000.00")


def test_partial_close_realizes_half():
    events = [
        _ev("open", "long", "100000", "3000", "10", 0),
        _ev("decrease", "long", "50000", "3100", "10", 10, pnl="833"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.realized_pnl_90d == Decimal("833.00")
    assert stats.avg_hold_secs == 10 * 60


def test_multiple_opens_consumed_fifo_by_one_close():
    events = [
        _ev("open",     "long", "20000", "3000", "10", 0),
        _ev("increase", "long", "30000", "3050", "10", 5),
        _ev("close",    "long", "50000", "3100", "10", 20, pnl="1500"),
    ]
    stats = score_wallet(events)
    # Two round-trips because FIFO matches lot-by-lot.
    assert stats.trades_90d == 2
    assert stats.realized_pnl_90d == Decimal("1500.00")
    # Hold times: lot1 = 20m, lot2 = 15m → mean = 17.5m
    assert stats.avg_hold_secs == int((20 * 60 + 15 * 60) / 2)


def test_orphan_close_skipped():
    events = [_ev("close", "long", "10000", "3000", "5", 0, pnl="100")]
    stats = score_wallet(events)
    assert stats.trades_90d == 0
    assert stats.realized_pnl_90d == Decimal("0.00")
    assert stats.win_rate_90d == Decimal("0.0000")


def test_liquidation_treated_as_close():
    events = [
        _ev("open",        "long", "50000", "3000", "20", 0),
        _ev("liquidation", "long", "50000", "2900", "20", 5, pnl="-1666"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.realized_pnl_90d == Decimal("-1666.00")
    assert stats.win_rate_90d == Decimal("0.0000")


def test_side_split_long_only_keeps_short_null():
    events = [
        _ev("open",  "long", "10000", "3000", "5", 0),
        _ev("close", "long", "10000", "3100", "5", 5, pnl="333"),
    ]
    stats = score_wallet(events)
    assert stats.win_rate_long_90d == Decimal("1.0000")
    assert stats.win_rate_short_90d is None
