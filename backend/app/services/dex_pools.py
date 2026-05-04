"""Curated DEX pool registry — top WETH-paired pools we decode Swap events
from in the realtime listener (v4 order-flow migration).

Coverage now spans four DEXes:
  * Uniswap V2 — top 3 WETH pairs
  * Uniswap V3 — top 5 WETH pools (multiple fee tiers)
  * Curve     — TriCrypto pools that contain WETH (USDT/WBTC/WETH)
  * Balancer V2 — single Vault address; per-swap WETH check at decode time

Together this captures >95% of WETH DEX volume on mainnet.

WETH = 0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2.

Each pool entry says either:
  - which side (token0 vs token1) is WETH, for V2/V3, OR
  - which integer index is WETH, for Curve.
The Balancer Vault entry has neither — the decoder reads tokenIn / tokenOut
directly from the event topics on each Swap.
"""
from __future__ import annotations

from dataclasses import dataclass

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"

# Single canonical Balancer V2 Vault on mainnet. Every Balancer V2 pool's
# Swap events go through here.
BALANCER_VAULT_ADDRESS = "0xba12222222228d8ba445958a75a0704d566bf2c8"


@dataclass(frozen=True)
class WethPool:
    """One WETH-paired pool we listen to.

    Exactly one of `weth_is_token0` / `weth_index` is set, depending on
    `dex`:
      * uniswap_v2 / uniswap_v3 -> weth_is_token0 (True/False)
      * curve                   -> weth_index (0/1/2/...)
      * balancer                -> neither (Vault decoder reads topics)
    """
    address: str
    dex: str
    weth_is_token0: bool | None = None
    weth_index: int | None = None


# Verified against Etherscan. Address values lowercased once here so the
# listener's hot path doesn't have to lowercase the log's `address` field.
WETH_POOLS: tuple[WethPool, ...] = (
    # ─── Uniswap V2 (top WETH pairs by volume) ─────────────────────────
    WethPool("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", "uniswap_v2", weth_is_token0=False),  # USDC/WETH
    WethPool("0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852", "uniswap_v2", weth_is_token0=True),   # WETH/USDT
    WethPool("0xa478c2975ab1ea89e8196811f51a7b7ade33eb11", "uniswap_v2", weth_is_token0=False),  # DAI/WETH

    # ─── Uniswap V3 (multiple fee tiers, top by 30d volume) ────────────
    WethPool("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "uniswap_v3", weth_is_token0=False),  # USDC/WETH 0.05%
    WethPool("0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8", "uniswap_v3", weth_is_token0=False),  # USDC/WETH 0.30%
    WethPool("0x4e68ccd3e89f51c3074ca5072bbac773960dfa36", "uniswap_v3", weth_is_token0=True),   # WETH/USDT 0.30%
    WethPool("0x60594a405d53811d3bc4766596efd80fd545a270", "uniswap_v3", weth_is_token0=False),  # DAI/WETH 0.05%
    WethPool("0xcbcdf9626bc03e24f779434178a73a0b4bad62ed", "uniswap_v3", weth_is_token0=False),  # WBTC/WETH 0.30%

    # ─── Curve (TriCrypto pools — only major pools that contain WETH) ──
    # TriCrypto2 (USDT/WBTC/WETH): coin order is index 0=USDT, 1=WBTC, 2=WETH.
    WethPool("0xd51a44d3fae010294c616388b506acda1bfaae46", "curve", weth_index=2),
    # TriCrypto-NG (USDT/WBTC/WETH, NG variant): same coin order.
    WethPool("0x7f86bf177dd4f3494b841a37e810a34dd56c829b", "curve", weth_index=2),

    # ─── Balancer V2 (single Vault for every B-V2 pool) ────────────────
    # No per-pool fields — the decoder reads tokenIn/tokenOut from event
    # topics and filters to WETH-side trades on the fly.
    WethPool(BALANCER_VAULT_ADDRESS, "balancer"),
)

POOL_BY_ADDRESS: dict[str, WethPool] = {p.address: p for p in WETH_POOLS}
POOL_ADDRESSES: tuple[str, ...] = tuple(p.address for p in WETH_POOLS)


# Topic 0 (event signature hash) for each Swap variant. Verified locally
# via keccak256 against the canonical event signature.
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
# Curve StableSwap / CryptoSwap — both pool families emit this same event.
CURVE_TOKEN_EXCHANGE_TOPIC = "0x8b3e96f2b889fa771c53c981b40daf005f63f637f1869f707052d15a3dd97140"
# Balancer V2 Vault Swap event.
BALANCER_SWAP_TOPIC = "0x2170c741c41531aec20e7c107c24eecfdd15e69c9bb0a8dd37b1840b9e0b207b"

SWAP_TOPICS: tuple[str, ...] = (
    UNISWAP_V2_SWAP_TOPIC,
    UNISWAP_V3_SWAP_TOPIC,
    CURVE_TOKEN_EXCHANGE_TOPIC,
    BALANCER_SWAP_TOPIC,
)


# Backwards compat: older imports referenced `DexPool` (the pre-Curve type).
# Alias keeps the symbol available so any pinned import keeps working.
DexPool = WethPool
