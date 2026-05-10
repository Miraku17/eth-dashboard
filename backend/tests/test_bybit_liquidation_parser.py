"""Pure-compute tests for parse_bybit_liquidation.

Bybit V5 `allLiquidation.{symbol}` payload (per item in the `data` list):
    { "T": <unix_ms>, "s": "ETHUSDT", "S": "Buy" | "Sell",
      "v": "<qty_in_eth_string>", "p": "<price_usd_string>" }

Side inversion convention (matches the previous Binance forceOrder mapping):
    S="Buy"  → exchange BUYS to close a SHORT  → row.side = "short"
    S="Sell" → exchange SELLS to close a LONG  → row.side = "long"
"""
from datetime import datetime, timezone

import pytest

from app.realtime.liquidations import parse_bybit_liquidation


def _event(**overrides) -> dict:
    base = {
        "T": 1_715_339_000_000,
        "s": "ETHUSDT",
        "S": "Buy",
        "v": "0.5",
        "p": "3000.0",
    }
    base.update(overrides)
    return base


def test_buy_event_maps_to_short_liquidation():
    row = parse_bybit_liquidation(_event(S="Buy", v="0.5", p="3000"))
    assert row is not None
    assert row["venue"] == "bybit"
    assert row["symbol"] == "ETHUSDT"
    assert row["side"] == "short"
    assert row["price"] == pytest.approx(3000.0)
    assert row["qty"] == pytest.approx(0.5)
    assert row["notional_usd"] == pytest.approx(1500.0)
    assert isinstance(row["ts"], datetime)
    assert row["ts"].tzinfo == timezone.utc


def test_sell_event_maps_to_long_liquidation():
    row = parse_bybit_liquidation(_event(S="Sell"))
    assert row is not None
    assert row["side"] == "long"


def test_missing_timestamp_returns_none():
    bad = _event()
    bad.pop("T")
    assert parse_bybit_liquidation(bad) is None


def test_non_numeric_price_returns_none():
    assert parse_bybit_liquidation(_event(p="abc")) is None


def test_unknown_side_returns_none():
    assert parse_bybit_liquidation(_event(S="Hold")) is None


def test_zero_qty_returns_none():
    assert parse_bybit_liquidation(_event(v="0")) is None
