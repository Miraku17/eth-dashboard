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
    DefiProtocol("morpho",       "Morpho"),
    DefiProtocol("compound-v3",  "Compound v3"),
    DefiProtocol("compound-v2",  "Compound v2"),
    DefiProtocol("spark",        "Spark"),
    DefiProtocol("lido",         "Lido"),
    DefiProtocol("eigenlayer",   "EigenLayer"),
    DefiProtocol("pendle",       "Pendle"),
    DefiProtocol("uniswap-v3",   "Uniswap v3"),
)

DEFI_PROTOCOLS_BY_SLUG: dict[str, DefiProtocol] = {p.slug: p for p in DEFI_PROTOCOLS}
