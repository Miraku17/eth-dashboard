"""H2: same CEX deposit address.

A CEX deposit address is unique per user: the exchange generates a fresh
forwarder per customer that empties into a known hot wallet within minutes.
If two wallets send funds to the same forwarder, they are with very high
probability the same CEX account holder.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.etherscan import EtherscanClient
from app.realtime.labels import _LABELS as HOT_WALLET_LABELS

# Map hot wallet -> exchange slug (binance/coinbase/kraken/...) used in our UI.
_HOT_WALLET_TO_EXCHANGE: dict[str, str] = {}
for _addr, _label in HOT_WALLET_LABELS.items():
    _HOT_WALLET_TO_EXCHANGE[_addr.lower()] = _label.split(" ")[0].lower()


@dataclass(frozen=True)
class DepositMatch:
    deposit_address: str
    exchange: str


def _to_int(v: str | int | None) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


async def find_deposit_addresses(
    client: EtherscanClient,
    target: str,
    *,
    max_candidates: int,
) -> list[DepositMatch]:
    target_lc = target.lower()

    # Aggregate outbound-by-recipient across normal txs and ERC-20 transfers.
    eth_rows = await client.txlist(target, sort="desc", page=1, offset=200)
    erc20_rows = await client.tokentx(target, sort="desc", page=1, offset=200)

    aggregate: dict[str, int] = {}
    for r in eth_rows + erc20_rows:
        if (r.get("from") or "").lower() != target_lc:
            continue
        to = (r.get("to") or "").lower()
        if not to or to in _HOT_WALLET_TO_EXCHANGE:
            # Direct sends to a hot wallet aren't deposits-via-forwarder.
            continue
        aggregate[to] = aggregate.get(to, 0) + _to_int(r.get("value"))

    candidates = sorted(aggregate.items(), key=lambda kv: kv[1], reverse=True)[:max_candidates]

    matches: list[DepositMatch] = []
    for addr, _ in candidates:
        forwarder_rows = await client.txlist(addr, sort="asc", page=1, offset=20)
        for fr in forwarder_rows:
            to = (fr.get("to") or "").lower()
            if (fr.get("from") or "").lower() != addr:
                continue
            ex = _HOT_WALLET_TO_EXCHANGE.get(to)
            if ex:
                matches.append(DepositMatch(deposit_address=addr, exchange=ex))
                break
    return matches


async def find_co_depositors(
    client: EtherscanClient,
    *,
    deposit_address: str,
    target: str,
    limit: int,
) -> list[str]:
    rows = await client.txlist(deposit_address, sort="desc", page=1, offset=max(limit * 4, 100))
    deposit_lc = deposit_address.lower()
    target_lc = target.lower()
    seen: list[str] = []
    seen_set: set[str] = set()
    for r in rows:
        if (r.get("to") or "").lower() != deposit_lc:
            continue  # we want INBOUND to the forwarder
        sender = (r.get("from") or "").lower()
        if not sender or sender == target_lc or sender in seen_set:
            continue
        seen.append(sender)
        seen_set.add(sender)
        if len(seen) >= limit:
            break
    return seen
