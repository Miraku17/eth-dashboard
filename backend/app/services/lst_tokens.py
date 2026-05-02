"""Liquid-staking token registry. Single source of truth for the panel +
the hourly totalSupply() cron.

Note: wstETH is intentionally excluded. It's wrapped stETH and would
double-count Lido in the stacked-area chart.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LstToken:
    symbol: str          # display + DB key
    address: str         # lowercase 0x… contract address on mainnet
    decimals: int        # always 18 for the v1 set, kept explicit for safety


# Mainnet LST contracts. Verified via Etherscan + the issuers' docs.
LST_TOKENS: tuple[LstToken, ...] = (
    LstToken("stETH",   "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", 18),  # Lido
    LstToken("rETH",    "0xae78736cd615f374d3085123a210448e74fc6393", 18),  # Rocket Pool
    LstToken("cbETH",   "0xbe9895146f7af43049ca1c1ae358b0541ea49704", 18),  # Coinbase
    LstToken("sfrxETH", "0xac3e018457b222d93114458476f3e3416abbe38f", 18),  # Frax
    LstToken("mETH",    "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa", 18),  # Mantle
    LstToken("swETH",   "0xf951e335afb289353dc249e82926178eac7ded78", 18),  # Swell
    LstToken("ETHx",    "0xa35b1b31ce002fbf2058d22f30f95d405200a15b", 18),  # Stader
)

# ABI-encoded selector for `totalSupply()` (keccak256("totalSupply()")[0:4]).
TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
