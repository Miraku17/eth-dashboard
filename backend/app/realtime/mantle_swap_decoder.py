"""Decode Agni (Uniswap V3 fork) Swap events into MantleSwap tuples.

Pure functions — no DB, no network. The Mantle listener calls
`decode_mantle_swap()` per Swap log it pulls back from eth_getLogs;
the MantleOrderFlowAggregator accumulates the results into hourly
buckets.

V3 Swap event:
  Swap(address sender, address recipient, int256 amount0, int256 amount1,
       uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
  Non-indexed signed amounts in `data`, FROM THE POOL'S PERSPECTIVE:
    positive = pool received (user gave)
    negative = pool sent     (user got)
  MNT = token0, amount0 < 0 → user bought MNT (side='buy').
  MNT = token0, amount0 > 0 → user sold MNT   (side='sell').
  Mirror for token1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.realtime.mantle_dex_registry import MantlePool, UNISWAP_V3_SWAP_TOPIC

MNT_DECIMALS = 18
_WEI_PER_MNT = 10**MNT_DECIMALS


@dataclass(frozen=True)
class MantleSwap:
    dex: str            # 'agni'
    side: str           # 'buy' | 'sell'  (user perspective on MNT)
    mnt_amount: float   # positive MNT volume, in MNT units (not wei)
    ts: datetime


def _hex_to_int_signed(word: str) -> int:
    """Convert a 64-char hex word (no 0x prefix) to a signed int256."""
    n = int(word, 16)
    if n >= 1 << 255:
        n -= 1 << 256
    return n


def _slice_words(data_hex: str) -> list[str]:
    """Split `0x…` payload into 64-char hex words."""
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return [body[i : i + 64] for i in range(0, len(body), 64)]


def decode_mantle_swap(log: dict, pool: MantlePool, *, ts: datetime) -> MantleSwap | None:
    """Decode one V3 Swap log under the given pool's MNT side configuration.

    Returns None on:
      * topic mismatch
      * truncated payload (< 5 words)
      * zero MNT amount on the relevant side
    """
    topics = log.get("topics") or []
    if not topics or topics[0].lower() != UNISWAP_V3_SWAP_TOPIC:
        return None

    words = _slice_words(log.get("data", ""))
    if len(words) < 5:
        return None

    amount0 = _hex_to_int_signed(words[0])
    amount1 = _hex_to_int_signed(words[1])

    raw = amount0 if pool.token0_is_mnt else amount1
    if raw == 0:
        return None

    side = "buy" if raw < 0 else "sell"
    mnt_amount = abs(raw) / _WEI_PER_MNT

    return MantleSwap(dex=pool.dex, side=side, mnt_amount=mnt_amount, ts=ts)
