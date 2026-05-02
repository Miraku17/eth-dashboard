"""DeFi protocol registry. Single source of truth for the TVL cron + panel.

Each entry has a stable `slug` (matches DefiLlama's protocol slug used in
GET /protocol/{slug}) and a human-readable `display_name` used in the
panel's protocol picker.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DefiProtocol:
    slug: str          # DefiLlama slug, lowercase-kebab
    display_name: str  # shown in the panel picker


# 10 protocols on Ethereum mainnet. Slugs verified against
# https://api.llama.fi/v2/protocols on 2026-05-02.
DEFI_PROTOCOLS: tuple[DefiProtocol, ...] = (
    DefiProtocol("aave-v3",      "Aave v3"),
    DefiProtocol("sky-lending",  "Sky (Lending)"),
    DefiProtocol("morpho-blue",  "Morpho"),       # slug: morpho-blue (not "morpho")
    DefiProtocol("compound-v3",  "Compound v3"),
    DefiProtocol("compound-v2",  "Compound v2"),
    DefiProtocol("sparklend",    "Spark"),        # slug: sparklend (not "spark")
    DefiProtocol("lido",         "Lido"),
    DefiProtocol("eigenlayer",   "EigenLayer"),
    DefiProtocol("pendle",       "Pendle"),
    # Uniswap v3 omitted — DefiLlama doesn't expose per-asset Ethereum-mainnet
    # tokensInUsd for it (DEX LP TVL needs a different ingestion shape).
)

DEFI_PROTOCOLS_BY_SLUG: dict[str, DefiProtocol] = {p.slug: p for p in DEFI_PROTOCOLS}
