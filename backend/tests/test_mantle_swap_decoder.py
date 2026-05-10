"""Pure-compute tests for the Mantle V3 swap decoder.

V3 Swap event payload (non-indexed, in `data`):
  amount0:        int256, signed
  amount1:        int256, signed
  sqrtPriceX96:   uint160 (we ignore)
  liquidity:      uint128 (we ignore)
  tick:           int24   (we ignore)

Sign convention (FROM POOL'S PERSPECTIVE):
  positive = pool received (user gave)
  negative = pool sent (user got)

So if MNT is token0:
  amount0 < 0  →  user got MNT     →  side = 'buy'
  amount0 > 0  →  user gave MNT    →  side = 'sell'
"""
from datetime import datetime, timezone
from typing import Final

import pytest

from app.realtime.mantle_dex_registry import MantlePool
from app.realtime.mantle_swap_decoder import decode_mantle_swap


# 18-decimal MNT amount, encoded as a signed 256-bit two's-complement word.
ONE_MNT: Final[int] = 10**18

POOL_MNT_TOKEN0 = MantlePool(
    address="0x" + "a" * 40,
    dex="agni",
    token0_is_mnt=True,
    quote_symbol="USDC",
    fee_tier=500,
)

POOL_MNT_TOKEN1 = MantlePool(
    address="0x" + "b" * 40,
    dex="agni",
    token0_is_mnt=False,
    quote_symbol="WETH",
    fee_tier=3000,
)

UNKNOWN_POOL_ADDR = "0x" + "c" * 40

V3_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


def _to_word(n: int) -> str:
    """Encode a signed int256 as a 64-char hex word (no 0x prefix)."""
    if n < 0:
        n += 1 << 256
    return f"{n:064x}"


def _make_log(*, pool: str, amount0: int, amount1: int) -> dict:
    """Build a minimal V3 Swap log fixture."""
    data = "0x" + _to_word(amount0) + _to_word(amount1) + _to_word(0) + _to_word(0) + _to_word(0)
    return {
        "address": pool,
        "topics": [V3_TOPIC, "0x" + "0" * 64, "0x" + "0" * 64],
        "data": data,
    }


def test_buy_when_mnt_is_token0():
    # User receives 5 MNT (amount0 = -5 MNT)
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=-5 * ONE_MNT, amount1=100 * 10**6)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "buy"
    assert result.mnt_amount == pytest.approx(5.0)
    assert result.dex == "agni"


def test_sell_when_mnt_is_token0():
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=3 * ONE_MNT, amount1=-50 * 10**6)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "sell"
    assert result.mnt_amount == pytest.approx(3.0)


def test_buy_when_mnt_is_token1():
    # User receives 7 MNT (amount1 = -7 MNT)
    log = _make_log(pool=POOL_MNT_TOKEN1.address, amount0=2 * 10**18, amount1=-7 * ONE_MNT)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN1, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "buy"
    assert result.mnt_amount == pytest.approx(7.0)


def test_sell_when_mnt_is_token1():
    log = _make_log(pool=POOL_MNT_TOKEN1.address, amount0=-1 * 10**18, amount1=4 * ONE_MNT)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN1, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "sell"
    assert result.mnt_amount == pytest.approx(4.0)


def test_truncated_data_returns_none():
    log = {"address": POOL_MNT_TOKEN0.address, "topics": [V3_TOPIC], "data": "0xdead"}
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None


def test_wrong_topic_returns_none():
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=-ONE_MNT, amount1=ONE_MNT)
    log["topics"] = ["0x" + "f" * 64]
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None


def test_zero_mnt_amount_returns_none():
    # Some V3 pools emit Swap with one side zero (degenerate edge case).
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=0, amount1=ONE_MNT)
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None
