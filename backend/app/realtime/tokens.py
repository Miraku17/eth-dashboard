"""Token metadata for whale-tracking. ERC-20 Transfer topic + contract addresses.

Three tracked sets:

- STABLES: pegged tokens (USD/EUR/CHF). Threshold compare uses
  amount × price_usd_approx so non-USD pegs surface at the right USD
  notional. price_usd_approx is a hand-curated rate; refresh
  periodically (whale-detection isn't sensitive to ±10% drift).
- VOLATILE_TOKENS: price-floating, threshold is hardcoded per-token in
  native units, sized to approximate ~$250k USD at the time of authoring.
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
class StableToken(Token):
    peg_currency: str         # "USD" | "EUR" | "CHF" (display only)
    price_usd_approx: float   # 1.0 for USD pegs; ~1.08 for EUR; ~1.10 for CHF


@dataclass(frozen=True)
class VolatileToken(Token):
    threshold_native: float
    price_usd_approx: float


STABLES: tuple[StableToken, ...] = (
    StableToken("USDT",  "0xdac17f958d2ee523a2206206994597c13d831ec7", 6,  "USD", 1.00),
    StableToken("USDC",  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6,  "USD", 1.00),
    StableToken("DAI",   "0x6b175474e89094c44da98b954eedeac495271d0f", 18, "USD", 1.00),
    StableToken("PYUSD", "0x6c3ea9036406852006290770bedfcaba0e23a0e8", 6,  "USD", 1.00),
    StableToken("FDUSD", "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409", 18, "USD", 1.00),
    StableToken("USDS",  "0xdc035d45d973e3ec169d2276ddab16f1e407384f", 18, "USD", 1.00),
    StableToken("GHO",   "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", 18, "USD", 1.00),
    StableToken("EUROC", "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c", 6,  "EUR", 1.08),
    StableToken("ZCHF",  "0xb58e61c3098d85632df34eecfb899a1ed80921cb", 18, "CHF", 1.10),
    StableToken("EURCV", "0x5f7827fdeb7c20b443265fc2f40845b715385ff2", 18, "EUR", 1.08),
    StableToken("EURe",  "0x39b8b6385416f4ca36a20319f70d28621895279d", 18, "EUR", 1.08),
    StableToken("tGBP",  "0x27f6c8289550fce67f6b50bed1f519966afe5287", 18, "GBP", 1.27),
    StableToken("USDe",  "0x4c9edd5852cd905f086c759e8383e09bff1e68b3", 18, "USD", 1.00),
    StableToken("XSGD",  "0x70e8de73ce538da2beed35d14187f6959a8eca96", 6,  "SGD", 0.74),
    StableToken("BRZ",   "0x01d33fd36ec67c6ada32cf36b31e88ee190b1839", 18, "BRL", 0.20),
)

STABLES_BY_ADDRESS: dict[str, StableToken] = {t.address: t for t in STABLES}


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
