"""GMX V2 market registry — Arbitrum mainnet.

Maps the GMX market token address (the Long-Short-Index "GM token" address
that uniquely identifies a market) to a display symbol. v1 covers the
eight markets that account for ~99% of GMX V2 OI.

The decoder uses this to translate the `market` topic in EventEmitter logs
into a human-readable string before persisting. Markets we don't recognise
are dropped — adding a new one is a one-line addition here, no migration.

Addresses are lowercase 0x… for direct comparison against decoded payloads.
Source: gmx-synthetics deployment on Arbitrum (verified on Arbiscan).
"""

# Map: market_token_address (lowercase) -> display symbol "<INDEX>-USD"
GMX_V2_MARKETS: dict[str, str] = {
    "0x70d95587d40a2caf56bd97485ab3eec10bee6336": "ETH-USD",
    "0x47c031236e19d024b42f8ae6780e44a573170703": "BTC-USD",
    "0x09400d9db990d5ed3f35d7be61dfaeb900af03c9": "SOL-USD",
    "0x7bbbf946883a5701350007320f525c5379b8178a": "AVAX-USD",
    "0xc25cef6061cf5de5eb761b50e4743c1f5d7e5407": "ARB-USD",
    "0x7f1fa204bb700853d36994da19f830b6ad18455c": "LINK-USD",
    "0x6853ea96ff216fab11d2d930ce3c508556a4bdc4": "DOGE-USD",
    "0x63dafb2ca71767129ab8d0a0909383023c4aff6e": "NEAR-USD",
}


def market_for(address: str) -> str | None:
    """Look up a GMX market by its market-token address.

    Returns the display symbol or None for unknown markets. Caller decides
    whether to drop or to record as 'OTHER' — v1 drops.
    """
    return GMX_V2_MARKETS.get((address or "").lower())
