"""Liquid Restaking Token (LRT) registry.

LRTs are tokens issued by restaking protocols on top of EigenLayer (and a
handful of native-restaking variants). Each entry maps a stable DefiLlama
slug to the human-readable issuer name shown in the panel.

Slugs are the protocol slug used in DefiLlama's GET /protocol/{slug}.
EigenLayer itself is intentionally NOT included here — it sits in the
DeFi-TVL panel as the underlying restaking layer; this panel tracks the
*issuer* protocols sitting on top of it.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LrtProtocol:
    slug: str
    display_name: str
    token: str  # The headline LRT ticker (eETH, ezETH, ...) shown next to the row


# Top issuers by ETH-mainnet TVL. Slugs verified against
# https://api.llama.fi/protocols (category="Liquid Restaking") on 2026-05-03.
# Several slugs are non-obvious (DefiLlama uses "ether.fi-stake" not
# "ether.fi", "kelp" not "kelp-dao", "puffer-stake" not "puffer-finance",
# "swell-liquid-restaking" not "swell"); each one was a 400 from the API
# until the slug was looked up directly.
LRT_PROTOCOLS: tuple[LrtProtocol, ...] = (
    LrtProtocol("ether.fi-stake",         "ether.fi",         "eETH"),
    LrtProtocol("kelp",                   "Kelp DAO",         "rsETH"),
    LrtProtocol("renzo",                  "Renzo",            "ezETH"),
    LrtProtocol("mantle-restaking",       "Mantle Restaking", "cmETH"),
    LrtProtocol("puffer-stake",           "Puffer",           "pufETH"),
    LrtProtocol("swell-liquid-restaking", "Swell",            "rswETH"),
)

LRT_PROTOCOLS_BY_SLUG: dict[str, LrtProtocol] = {p.slug: p for p in LRT_PROTOCOLS}
