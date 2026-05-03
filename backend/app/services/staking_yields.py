"""Map LST symbols and LRT slugs to DefiLlama (project, symbol) pool keys.

DefiLlama's /yields/pools endpoint returns ~10k pools. We pick the single
canonical staking pool per issuer and store its APY in `staking_yield`.

Mappings verified against https://yields.llama.fi/pools on 2026-05-03.
Mantle Restaking has no DefiLlama yield pool exposed yet — its entry is
intentionally None so the cron skips it (panel renders "—" for that row).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class YieldPoolKey:
    """A (project, symbol) pair that uniquely identifies a pool in
    DefiLlama's /yields/pools dataset. Both fields are case-insensitive
    in DefiLlama's payload — we compare in lowercase / uppercase to
    match what the source actually emits."""
    project: str   # DefiLlama project slug
    symbol: str    # Pool symbol (uppercase in DefiLlama's payload)


# LST → its main staking pool. Symbols are uppercase to match DefiLlama.
LST_YIELD_KEYS: dict[str, YieldPoolKey] = {
    "stETH":   YieldPoolKey("lido",                          "STETH"),
    "rETH":    YieldPoolKey("rocket-pool",                   "RETH"),
    "cbETH":   YieldPoolKey("coinbase-wrapped-staked-eth",   "CBETH"),
    "sfrxETH": YieldPoolKey("frax-ether",                    "SFRXETH"),
    "mETH":    YieldPoolKey("meth-protocol",                 "METH"),
    "swETH":   YieldPoolKey("swell-liquid-staking",          "SWETH"),
    "ETHx":    YieldPoolKey("stader",                        "ETHX"),
}

# LRT → its main restaking pool. Slug keys here match LRT_PROTOCOLS slugs.
# Mantle Restaking has no exposed pool today, hence absent from this map.
LRT_YIELD_KEYS: dict[str, YieldPoolKey] = {
    "ether.fi-stake":         YieldPoolKey("ether.fi-stake",         "WEETH"),
    "kelp":                   YieldPoolKey("kelp",                   "RSETH"),
    "renzo":                  YieldPoolKey("renzo",                  "EZETH"),
    "puffer-stake":           YieldPoolKey("puffer-stake",           "PUFETH"),
    "swell-liquid-restaking": YieldPoolKey("swell-liquid-restaking", "RSWETH"),
}
