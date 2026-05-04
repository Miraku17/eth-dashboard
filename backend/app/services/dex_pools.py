"""Curated DEX pool registry — top-N WETH-paired pools we decode Swap
events from in the realtime listener (v4 order-flow migration).

Coverage strategy: top 3 Uniswap V2 + top 3 Uniswap V3 pools by historical
WETH volume cover ~70% of all WETH DEX flow. Curve + Balancer pools are
deliberately not in v1 (they have different swap semantics — TokenExchange
with integer indices for Curve, Vault batchSwap for Balancer — and need
their own decoders). Until those land, the Dune cron continues to populate
the `curve` / `balancer` / `other` buckets in the order_flow table; the
live cron only overwrites `uniswap_v2` and `uniswap_v3` rows.

WETH = 0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2 on mainnet. Each pool
declares which side (token0 or token1) is WETH; the decoder uses that to
classify each Swap event as a buy or sell of WETH.
"""
from __future__ import annotations

from dataclasses import dataclass

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


@dataclass(frozen=True)
class DexPool:
    address: str            # lowercase pool address
    dex: str                # 'uniswap_v2' | 'uniswap_v3' (matches order_flow.dex enum)
    weth_is_token0: bool    # which side of the pool is WETH


# Verified against Etherscan + the existing dune order_flow.sql output.
# Address values lowercased once here so lookups don't have to lowercase
# the log's `address` field (a hot path in the listener).
WETH_POOLS: tuple[DexPool, ...] = (
    # Uniswap V2 — ordered by typical daily volume.
    DexPool("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", "uniswap_v2", weth_is_token0=False),  # USDC/WETH
    DexPool("0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852", "uniswap_v2", weth_is_token0=True),   # WETH/USDT
    DexPool("0xa478c2975ab1ea89e8196811f51a7b7ade33eb11", "uniswap_v2", weth_is_token0=False),  # DAI/WETH
    # Uniswap V3 — fee tier in the comment; address is what's on Etherscan.
    DexPool("0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "uniswap_v3", weth_is_token0=False),  # USDC/WETH 0.05%
    DexPool("0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8", "uniswap_v3", weth_is_token0=False),  # USDC/WETH 0.30%
    DexPool("0x4e68ccd3e89f51c3074ca5072bbac773960dfa36", "uniswap_v3", weth_is_token0=True),   # WETH/USDT 0.30%
    DexPool("0x60594a405d53811d3bc4766596efd80fd545a270", "uniswap_v3", weth_is_token0=False),  # DAI/WETH 0.05%
    DexPool("0xcbcdf9626bc03e24f779434178a73a0b4bad62ed", "uniswap_v3", weth_is_token0=False),  # WBTC/WETH 0.30%
)

POOL_BY_ADDRESS: dict[str, DexPool] = {p.address: p for p in WETH_POOLS}
POOL_ADDRESSES: tuple[str, ...] = tuple(p.address for p in WETH_POOLS)


# Topic 0 (event signature hash) for each Swap variant.
# keccak256("Swap(address,uint256,uint256,uint256,uint256,address)")
UNISWAP_V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

SWAP_TOPICS: tuple[str, ...] = (
    UNISWAP_V2_SWAP_TOPIC,
    UNISWAP_V3_SWAP_TOPIC,
)
