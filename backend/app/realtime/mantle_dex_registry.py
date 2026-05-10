"""Curated registry of Agni Finance MNT pools on Mantle.

Agni is a Uniswap V3 fork — the Swap event ABI matches V3 exactly,
so the only chain-specific detail is the per-pool config below.
Adding pools is a code change, not config: changes here ship via
the regular release path, not via env vars.

To extend: append a MantlePool entry, set token0_is_mnt by comparing
the pool's token0() address against the Mantle MNT (or wrapped-MNT)
contract address.

Research methodology (2026-05-10):
  1. Pool candidates sourced from GeckoTerminal /mantle/agni-finance/pools,
     sorted by 24h volume.
  2. For each candidate, on-chain calls confirmed token0/token1/fee:
       token0(): eth_call data=0x0dfe1681 → last 40 hex chars
       token1(): eth_call data=0xd21220a7
       fee():    eth_call data=0xddca3f43 → uint24 bps
  3. token0_is_mnt = (token0 == MANTLE_WMNT)
  All calls made against https://rpc.mantle.xyz at block height ~0x5ab9d4a.
"""
from __future__ import annotations

from typing import Final, NamedTuple

# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
UNISWAP_V3_SWAP_TOPIC: Final[str] = (
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
)

# Mantle native MNT (wrapped) contract. Used at registry-build time
# when verifying token0_is_mnt against on-chain pool config.
MANTLE_WMNT: Final[str] = "0x78c1b0c915c4faa5fffa6cabf0219da63d7f4cb8"


class MantlePool(NamedTuple):
    address: str          # lowercase pool contract address
    dex: str              # 'agni'
    token0_is_mnt: bool   # True iff pool.token0() == WMNT
    quote_symbol: str     # 'USDC' | 'USDT' | 'WETH' | 'mETH' | …
    fee_tier: int         # bps (500 = 0.05%, 3000 = 0.3%, etc.)


# v1: top-5 Agni MNT pools by 24h volume (sourced from GeckoTerminal 2026-05-10).
# Re-pin when one of these falls out of the top-5 (registry change ships
# via PR; not auto-rotating in v1).
#
# Verified on-chain (rpc.mantle.xyz):
#   Pool                                         token0                                       token1                                       fee
#   0xeafc...0dd5  USDe/WMNT   token0=0x5d3a..  (USDe)   token1=0x78c1.. (WMNT)  fee=2500
#   0x9ec3...0a2   WMNT/WETH   token0=0x78c1..  (WMNT)   token1=0xdead.. (WETH)  fee=2500
#   0x1858...44f   USDC/WMNT   token0=0x09bc..  (USDC)   token1=0x78c1.. (WMNT)  fee=500
#   0x7b3a...f85   USDC/WMNT   token0=0x09bc..  (USDC)   token1=0x78c1.. (WMNT)  fee=100
#   0xd08c...26a   USDT/WMNT   token0=0x201e..  (USDT)   token1=0x78c1.. (WMNT)  fee=500
AGNI_POOLS: Final[tuple[MantlePool, ...]] = (
    # USDe/WMNT — highest 24h volume ($170k). token0=USDe, token1=WMNT.
    MantlePool(
        address="0xeafc4d6d4c3391cd4fc10c85d2f5f972d58c0dd5",
        dex="agni",
        token0_is_mnt=False,
        quote_symbol="USDe",
        fee_tier=2500,
    ),
    # WMNT/WETH — token0=WMNT, token1=WETH. MNT is token0.
    MantlePool(
        address="0x9ec313ff05946b6f3860a99b470625abba7eb0a2",
        dex="agni",
        token0_is_mnt=True,
        quote_symbol="WETH",
        fee_tier=2500,
    ),
    # USDC/WMNT — 0.05% tier. token0=USDC, token1=WMNT.
    MantlePool(
        address="0x1858d52cf57c07a018171d7a1e68dc081f17144f",
        dex="agni",
        token0_is_mnt=False,
        quote_symbol="USDC",
        fee_tier=500,
    ),
    # USDC/WMNT — 0.01% tier (tightest spread, stable-like). token0=USDC, token1=WMNT.
    MantlePool(
        address="0x7b3a4b36b0c5c95142afcd1b883ed055aa166f85",
        dex="agni",
        token0_is_mnt=False,
        quote_symbol="USDC",
        fee_tier=100,
    ),
    # USDT/WMNT — 0.05% tier. token0=USDT, token1=WMNT.
    MantlePool(
        address="0xd08c50f7e69e9aeb2867deff4a8053d9a855e26a",
        dex="agni",
        token0_is_mnt=False,
        quote_symbol="USDT",
        fee_tier=500,
    ),
)


POOL_BY_ADDRESS: Final[dict[str, MantlePool]] = {p.address: p for p in AGNI_POOLS}


def pool_addresses() -> list[str]:
    """List of pool contract addresses for the listener's eth_getLogs filter."""
    return [p.address for p in AGNI_POOLS]
