"""Decode Uniswap V2 + V3 Swap events into (dex, side, weth_amount) tuples.

Pure functions. The realtime listener calls `decode()` per Swap log; the
SwapAggregator (next module) accumulates the results into hourly buckets.

Side semantics:
  * The user perspective. 'buy' = user RECEIVED WETH from the pool.
    'sell' = user GAVE WETH to the pool. From the panel's standpoint
    these flip the price-impact direction the same way the Dune query
    classified them.

V2 event:
  Swap(address sender, uint256 amount0In, uint256 amount1In,
       uint256 amount0Out, uint256 amount1Out, address to)
  Non-indexed amounts → all four uint256 sit in `data` (4×32 bytes).
  If WETH = token0: amount0Out>0 means the pool sent WETH (user bought).
                    amount0In >0 means the pool received WETH (user sold).
  Mirror for token1.

V3 event:
  Swap(address sender, address recipient, int256 amount0, int256 amount1,
       uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
  Signed deltas FROM THE POOL'S PERSPECTIVE: positive = pool received
  (user gave), negative = pool sent (user got).
  WETH = token0: amount0 < 0 → user got WETH (buy). > 0 → sold.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.dex_pools import (
    BALANCER_SWAP_TOPIC,
    BALANCER_VAULT_ADDRESS,
    CURVE_TOKEN_EXCHANGE_TOPIC,
    POOL_BY_ADDRESS,
    UNISWAP_V2_SWAP_TOPIC,
    UNISWAP_V3_SWAP_TOPIC,
    WETH,
)

WETH_DECIMALS = 18
_WEI_PER_ETH = 10**WETH_DECIMALS


@dataclass(frozen=True)
class SwapEvent:
    dex: str            # 'uniswap_v2' | 'uniswap_v3'
    side: str           # 'buy' | 'sell' (user's perspective on WETH)
    weth_amount: float  # positive WETH amount, in ETH units (not wei)


def _hex_to_uint(s: str) -> int:
    """Parse a 32-byte hex slice as an unsigned integer."""
    return int(s, 16)


def _hex_to_int(s: str) -> int:
    """Parse a 32-byte hex slice as a SIGNED int256 (two's complement)."""
    n = int(s, 16)
    # 256-bit sign bit
    if n >= 1 << 255:
        n -= 1 << 256
    return n


def _slice_words(data_hex: str) -> list[str]:
    """Split a 0x… hex string into 64-char (32-byte) words."""
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return [body[i : i + 64] for i in range(0, len(body), 64)]


def decode(log: dict) -> SwapEvent | None:
    """Return a SwapEvent for a Swap log we recognize, else None.

    Recognition: log.address must be in POOL_BY_ADDRESS, AND topics[0]
    must match the Swap signature for that pool's DEX. Anything else
    (e.g. Mint / Burn events on the same pool) returns None.
    """
    addr = (log.get("address") or "").lower()
    pool = POOL_BY_ADDRESS.get(addr)
    if pool is None:
        return None
    topics = log.get("topics") or []
    if not topics:
        return None
    topic0 = topics[0].lower()

    if pool.dex == "uniswap_v2" and topic0 == UNISWAP_V2_SWAP_TOPIC:
        return _decode_v2(log, bool(pool.weth_is_token0))
    if pool.dex == "uniswap_v3" and topic0 == UNISWAP_V3_SWAP_TOPIC:
        return _decode_v3(log, bool(pool.weth_is_token0))
    if pool.dex == "curve" and topic0 == CURVE_TOKEN_EXCHANGE_TOPIC:
        return _decode_curve(log, pool.weth_index)
    if pool.dex == "balancer" and topic0 == BALANCER_SWAP_TOPIC:
        return _decode_balancer(log)
    return None


def _decode_v2(log: dict, weth_is_token0: bool) -> SwapEvent | None:
    data = log.get("data") or "0x"
    words = _slice_words(data)
    if len(words) < 4:
        return None
    try:
        a0_in = _hex_to_uint(words[0])
        a1_in = _hex_to_uint(words[1])
        a0_out = _hex_to_uint(words[2])
        a1_out = _hex_to_uint(words[3])
    except ValueError:
        return None
    if weth_is_token0:
        weth_in, weth_out = a0_in, a0_out
    else:
        weth_in, weth_out = a1_in, a1_out
    if weth_out > 0 and weth_in == 0:
        amt = weth_out / _WEI_PER_ETH
        side = "buy"
    elif weth_in > 0 and weth_out == 0:
        amt = weth_in / _WEI_PER_ETH
        side = "sell"
    else:
        # Pathological / liquidity-add edge case where both sides are non-
        # zero or both zero — skip rather than mis-classify.
        return None
    if amt <= 0:
        return None
    return SwapEvent(dex="uniswap_v2", side=side, weth_amount=amt)


def _decode_v3(log: dict, weth_is_token0: bool) -> SwapEvent | None:
    data = log.get("data") or "0x"
    words = _slice_words(data)
    # V3 data layout: amount0, amount1, sqrtPriceX96, liquidity, tick (5 words).
    if len(words) < 2:
        return None
    try:
        a0 = _hex_to_int(words[0])
        a1 = _hex_to_int(words[1])
    except ValueError:
        return None
    weth_delta = a0 if weth_is_token0 else a1
    # Pool's perspective: weth_delta < 0 means the pool SENT WETH out =>
    # the user RECEIVED WETH (buy). Symmetric for sell.
    if weth_delta < 0:
        amt = -weth_delta / _WEI_PER_ETH
        side = "buy"
    elif weth_delta > 0:
        amt = weth_delta / _WEI_PER_ETH
        side = "sell"
    else:
        return None
    if amt <= 0:
        return None
    return SwapEvent(dex="uniswap_v3", side=side, weth_amount=amt)


def _decode_curve(log: dict, weth_index: int | None) -> SwapEvent | None:
    """Curve TokenExchange:
        TokenExchange(buyer indexed, sold_id int128, tokens_sold uint256,
                      bought_id int128, tokens_bought uint256)
    Non-indexed fields → 4 words (128 bytes) in `data`.

    Direction: if sold_id == weth_index, the user GAVE WETH to the pool
    (sell). If bought_id == weth_index, the user RECEIVED WETH (buy).
    Anything else means the swap didn't involve WETH in this pool — None.
    """
    if weth_index is None:
        return None
    data = log.get("data") or "0x"
    words = _slice_words(data)
    if len(words) < 4:
        return None
    try:
        sold_id = _hex_to_int(words[0])
        tokens_sold = _hex_to_uint(words[1])
        bought_id = _hex_to_int(words[2])
        tokens_bought = _hex_to_uint(words[3])
    except ValueError:
        return None
    if sold_id == weth_index:
        amt = tokens_sold / _WEI_PER_ETH
        side = "sell"
    elif bought_id == weth_index:
        amt = tokens_bought / _WEI_PER_ETH
        side = "buy"
    else:
        return None
    if amt <= 0:
        return None
    return SwapEvent(dex="curve", side=side, weth_amount=amt)


def _decode_balancer(log: dict) -> SwapEvent | None:
    """Balancer V2 Vault Swap:
        Swap(poolId bytes32 indexed, tokenIn address indexed,
             tokenOut address indexed, amountIn uint256, amountOut uint256)
    3 indexed → topics[0..3]. Non-indexed → 2 words in `data`
    (amountIn, amountOut).

    The Vault emits a Swap for EVERY swap across all Balancer V2 pools;
    most don't involve WETH. We filter at decode time by checking
    tokenIn (topics[2]) and tokenOut (topics[3]) against the WETH
    address. Non-WETH swaps return None — the listener buckets them as
    'no event found' which is correct.
    """
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    token_in = "0x" + topics[2][-40:].lower()
    token_out = "0x" + topics[3][-40:].lower()
    data = log.get("data") or "0x"
    words = _slice_words(data)
    if len(words) < 2:
        return None
    try:
        amount_in = _hex_to_uint(words[0])
        amount_out = _hex_to_uint(words[1])
    except ValueError:
        return None
    if token_in == WETH:
        amt = amount_in / _WEI_PER_ETH
        side = "sell"
    elif token_out == WETH:
        amt = amount_out / _WEI_PER_ETH
        side = "buy"
    else:
        return None
    if amt <= 0:
        return None
    return SwapEvent(dex="balancer", side=side, weth_amount=amt)
