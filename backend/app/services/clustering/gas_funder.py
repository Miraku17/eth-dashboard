"""H1: shared gas funder.

Algorithm:
  - For wallet X, the *funder* is the `from` of the lowest-block inbound tx
    with non-zero value.
  - If no normal inbound exists, fall back to internal txs (contract payouts).
  - Co-funded wallets = unique `to` addresses across all txs sent FROM the
    funder (capped to limit).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.etherscan import EtherscanClient


@dataclass(frozen=True)
class FunderInfo:
    address: str
    tx_hash: str
    block_number: int


def _to_int(v: str | int | None) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


async def find_first_funder(client: EtherscanClient, target: str) -> FunderInfo | None:
    target_lc = target.lower()

    # Pass 1: normal external txs.
    rows = await client.txlist(target, sort="asc", page=1, offset=100)
    candidate = _earliest_inbound_with_value(rows, target_lc)
    if candidate is not None:
        return candidate

    # Pass 2: internal (contract-driven) txs.
    rows = await client.txlistinternal(target)
    candidate = _earliest_inbound_with_value(rows, target_lc)
    return candidate


def _earliest_inbound_with_value(rows: list[dict], target_lc: str) -> FunderInfo | None:
    best: FunderInfo | None = None
    best_block = 10**18
    for r in rows:
        if (r.get("to") or "").lower() != target_lc:
            continue
        if _to_int(r.get("value")) <= 0:
            continue
        bn = _to_int(r.get("blockNumber"))
        if bn < best_block:
            best_block = bn
            best = FunderInfo(
                address=(r.get("from") or "").lower(),
                tx_hash=r.get("hash") or "",
                block_number=bn,
            )
    return best


async def find_co_funded_wallets(
    client: EtherscanClient,
    funder: str,
    *,
    target: str | None,
    limit: int,
) -> list[str]:
    """Unique downstream recipients of `funder`, capped at `limit` (in iteration order).

    `target` is excluded so the target wallet doesn't appear as its own neighbor.
    """
    rows = await client.txlist(funder, sort="asc", page=1, offset=max(limit * 4, 100))
    target_lc = target.lower() if target else None
    seen: list[str] = []
    seen_set: set[str] = set()
    funder_lc = funder.lower()
    for r in rows:
        if (r.get("from") or "").lower() != funder_lc:
            continue
        to = (r.get("to") or "").lower()
        if not to or to == target_lc or to in seen_set:
            continue
        seen.append(to)
        seen_set.add(to)
        if len(seen) >= limit:
            break
    return seen
