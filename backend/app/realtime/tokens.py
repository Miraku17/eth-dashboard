"""Token metadata for whale-tracking. ERC-20 Transfer topic + contract addresses.

Two tracked sets:

- STABLES: USD-pegged, threshold comes from runtime config (WHALE_STABLE_THRESHOLD_USD).
- VOLATILE_TOKENS: price-floating, threshold is hardcoded per-token in native units,
  sized to approximate ~$250k USD at the time of authoring. These will drift as
  prices move — refresh the numbers periodically. The approximation is fine for
  whale-detection purposes (a 30% price move changes an alert from "$250k whale"
  to "$175k whale", still whale-sized).
"""
from dataclasses import dataclass

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str  # lowercase 0x…
    decimals: int


@dataclass(frozen=True)
class VolatileToken(Token):
    # Native-unit threshold: transfers at or above this amount (in token units)
    # are considered whale-sized and get persisted.
    threshold_native: float
    # Approximate USD price per token, used for the persisted usd_value column.
    # Refresh periodically; intended as a display approximation, not truth.
    price_usd_approx: float


STABLES: tuple[Token, ...] = (
    Token("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    Token("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    Token("DAI", "0x6b175474e89094c44da98b954eedeac495271d0f", 18),
)

STABLES_BY_ADDRESS: dict[str, Token] = {t.address: t for t in STABLES}


# Thresholds each target ~$250k USD notional; refresh as prices drift.
VOLATILE_TOKENS: tuple[VolatileToken, ...] = (
    VolatileToken("WETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18, 70, 3500),
    VolatileToken("WBTC", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8, 3.5, 70000),
    VolatileToken("LINK", "0x514910771af9ca656af840dff83e8264ecf986ca", 18, 16000, 15),
    VolatileToken("UNI",  "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", 18, 30000, 8),
    VolatileToken("AAVE", "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", 18, 2500, 100),
    VolatileToken("MKR",  "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", 18, 165, 1500),
    VolatileToken("CRV",  "0xd533a949740bb3306d119cc777fa900ba034cd52", 18, 600000, 0.40),
    VolatileToken("LDO",  "0x5a98fcbea516cf06857215779fd812ca3bef1b32", 18, 125000, 2.0),
    VolatileToken("COMP", "0xc00e94cb662c3520282e6f5717214004a7f26888", 18, 5000, 50),
    VolatileToken("SUSHI", "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2", 18, 250000, 1.0),
    VolatileToken("PEPE", "0x6982508145454ce325ddbe47a25d4ec3d2311933", 18, 16_000_000_000, 0.000015),
    VolatileToken("SHIB", "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce", 18, 11_000_000_000, 0.000022),
)

VOLATILE_BY_ADDRESS: dict[str, VolatileToken] = {t.address: t for t in VOLATILE_TOKENS}


ALL_TRACKED_ADDRESSES: list[str] = [t.address for t in STABLES] + [t.address for t in VOLATILE_TOKENS]
