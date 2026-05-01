"""Static denylist of addresses that fund many unrelated wallets.

Without this list, the shared-gas-funder heuristic would falsely link any
two wallets that ever received ETH from a CEX, a bridge, or Tornado Cash.
The list is hand-curated; extend by editing public_funders.json.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_DATA_PATH = Path(__file__).parent / "public_funders.json"


class FunderEntry(TypedDict):
    label: str
    kind: str  # "cex" | "mixer" | "bridge" | "faucet" | "builder"


@lru_cache(maxsize=1)
def load_public_funders() -> dict[str, FunderEntry]:
    raw = json.loads(_DATA_PATH.read_text())
    out: dict[str, FunderEntry] = {}
    for row in raw["addresses"]:
        addr = row["address"].lower()
        out[addr] = {"label": row["label"], "kind": row["kind"]}
    return out


def is_public_funder(address: str) -> bool:
    return address.lower() in load_public_funders()


def public_funder_label(address: str) -> FunderEntry | None:
    return load_public_funders().get(address.lower())
