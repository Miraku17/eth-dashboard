"""Liquid-staking token registry. Single source of truth for the panel +
the hourly totalSupply() cron + ETH-equivalent normalization.

Note: wstETH is intentionally excluded. It's wrapped stETH and would
double-count Lido in the stacked-area chart.

Each token has a `rate_*` config that tells the cron how to fetch
"ETH per token" so the panel can show ETH-equivalent supply rather than
raw share-token totalSupply (the latter undercounts share-style tokens
like rETH / sfrxETH by ~10%).

`rate_address`  — contract to call (often the token itself, sometimes a
                  separate staking-pool contract: e.g. Mantle's mETHToETH
                  lives on the staking pool, not the mETH token).
`rate_calldata` — full hex calldata: 4-byte selector + ABI-encoded args.
                  None means "no normalization needed" (e.g. stETH is
                  rebasing — supply already equals ETH amount).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LstToken:
    symbol: str           # display + DB key
    address: str          # lowercase 0x… contract address on mainnet
    decimals: int         # always 18 for the v1 set, kept explicit for safety
    rate_address: str | None    # contract to eth_call for rate; None = no normalization
    rate_calldata: str | None   # full calldata (selector + args); None = no normalization
    rate_decimals: int = 18     # decimals of the returned rate value


# 4-byte selectors. Keccak256(signature)[:4]:
_SEL_GET_EXCHANGE_RATE = "0xe6aa216c"   # getExchangeRate()
_SEL_EXCHANGE_RATE     = "0x3ba0b9a9"   # exchangeRate()
_SEL_PRICE_PER_SHARE   = "0x99530b06"   # pricePerShare()
_SEL_SWETH_TO_ETH_RATE = "0xd68b2cb6"   # swETHToETHRate()
_SEL_METH_TO_ETH       = "0x025bb3b0"   # mETHToETH(uint256)

# 1e18 left-padded to 32 bytes — used as the amount param for mETHToETH.
_ONE_ETH_PARAM = hex(10**18)[2:].rjust(64, "0")

# Mantle staking pool address — owns mETHToETH. The mETH token contract
# itself doesn't expose a conversion method.
_MANTLE_STAKING_POOL = "0xe3cbd06d7dadb3f4e6557bab7edd924cd1489e8f"


# Mainnet LST contracts. Verified via Etherscan + the issuers' docs.
LST_TOKENS: tuple[LstToken, ...] = (
    # Lido stETH is rebasing — totalSupply IS the ETH amount, no rate call.
    LstToken("stETH",   "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", 18,
             rate_address=None, rate_calldata=None),

    # Rocket Pool rETH — getExchangeRate() returns ETH per rETH, 1e18-scaled.
    LstToken("rETH",    "0xae78736cd615f374d3085123a210448e74fc6393", 18,
             rate_address="0xae78736cd615f374d3085123a210448e74fc6393",
             rate_calldata=_SEL_GET_EXCHANGE_RATE),

    # Coinbase cbETH — exchangeRate() returns 1e18-scaled.
    LstToken("cbETH",   "0xbe9895146f7af43049ca1c1ae358b0541ea49704", 18,
             rate_address="0xbe9895146f7af43049ca1c1ae358b0541ea49704",
             rate_calldata=_SEL_EXCHANGE_RATE),

    # Frax sfrxETH (ERC4626) — pricePerShare() returns frxETH per sfrxETH,
    # 1e18-scaled. Approximates ETH per sfrxETH because frxETH ≈ ETH at peg.
    LstToken("sfrxETH", "0xac3e018457b222d93114458476f3e3416abbe38f", 18,
             rate_address="0xac3e018457b222d93114458476f3e3416abbe38f",
             rate_calldata=_SEL_PRICE_PER_SHARE),

    # Mantle mETH — conversion lives on the staking pool contract, not the
    # token. Calldata embeds 1e18 as the amount param so the call returns
    # the unit ratio.
    LstToken("mETH",    "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa", 18,
             rate_address=_MANTLE_STAKING_POOL,
             rate_calldata=_SEL_METH_TO_ETH + _ONE_ETH_PARAM),

    # Swell swETH — swETHToETHRate() returns 1e18-scaled.
    LstToken("swETH",   "0xf951e335afb289353dc249e82926178eac7ded78", 18,
             rate_address="0xf951e335afb289353dc249e82926178eac7ded78",
             rate_calldata=_SEL_SWETH_TO_ETH_RATE),

    # Stader ETHx — getExchangeRate() returns 1e18-scaled. (Note: Stader
    # exposes the rate on its oracle contract too; the token contract has
    # been confirmed working against the same selector.)
    LstToken("ETHx",    "0xa35b1b31ce002fbf2058d22f30f95d405200a15b", 18,
             rate_address="0xa35b1b31ce002fbf2058d22f30f95d405200a15b",
             rate_calldata=_SEL_GET_EXCHANGE_RATE),
)

# ABI-encoded selector for `totalSupply()` (keccak256("totalSupply()")[0:4]).
TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
