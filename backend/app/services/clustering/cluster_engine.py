"""Cluster engine orchestrator: address -> ClusterResult.

Synchronous, stateless. Caller is responsible for caching the result.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.api.schemas import (
    CexDepositInfo,
    ClusterResult,
    ClusterStats,
    GasFunderInfo,
    LinkedWallet,
)
from app.clients.etherscan import EtherscanClient
from app.realtime.labels import label_for
from app.services.clustering.cex_deposit import (
    find_co_depositors,
    find_deposit_addresses,
)
from app.services.clustering.gas_funder import (
    find_co_funded_wallets,
    find_first_funder,
)
from app.services.clustering.public_funders import (
    is_public_funder,
    public_funder_label,
)


def _to_int(v: str | int | None) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


async def compute(
    client: EtherscanClient,
    address: str,
    *,
    max_linked: int,
    max_deposit_candidates: int,
    funder_strong_threshold: int,
) -> ClusterResult:
    target = address.lower()

    # H1 + H2 lookups can run concurrently — funder-based and deposit-based
    # branches share no state until the merge step.
    funder, deposits = await asyncio.gather(
        find_first_funder(client, target),
        find_deposit_addresses(client, target, max_candidates=max_deposit_candidates),
    )

    gas_funder_info: GasFunderInfo | None = None
    co_funded: list[str] = []
    is_pub = False
    if funder is not None:
        is_pub = is_public_funder(funder.address)
        funder_label_entry = public_funder_label(funder.address)
        funder_label = (
            funder_label_entry["label"] if funder_label_entry else label_for(funder.address)
        )
        gas_funder_info = GasFunderInfo(
            address=funder.address,
            label=funder_label,
            is_public=is_pub,
            tx_hash=funder.tx_hash,
            block_number=funder.block_number,
        )
        if not is_pub:
            co_funded = await find_co_funded_wallets(
                client,
                funder.address,
                target=target,
                limit=funder_strong_threshold + 1,
            )

    # H2: co-depositors per deposit address.
    co_depositors_by_dep: dict[str, list[str]] = {}
    for dep in deposits:
        peers = await find_co_depositors(
            client,
            deposit_address=dep.deposit_address,
            target=target,
            limit=max_linked,
        )
        co_depositors_by_dep[dep.deposit_address] = peers

    # Merge: H2 always strong; H1 strong iff funder fan-out <= threshold.
    funder_strong = (
        funder is not None
        and not is_pub
        and len(co_funded) <= funder_strong_threshold
    )

    rows: dict[str, LinkedWallet] = {}

    for dep, peers in co_depositors_by_dep.items():
        for peer in peers:
            row = rows.get(peer) or LinkedWallet(
                address=peer, confidence="strong", reasons=[]
            )
            ex = next((d.exchange for d in deposits if d.deposit_address == dep), "")
            row.reasons.append(f"shared_cex_deposit:{ex}:{dep}")
            row.confidence = "strong"
            rows[peer] = row

    if funder is not None and not is_pub:
        for peer in co_funded[:max_linked]:
            row = rows.get(peer) or LinkedWallet(
                address=peer,
                confidence="strong" if funder_strong else "weak",
                reasons=[],
            )
            row.reasons.append(f"shared_gas_funder:{funder.address}")
            # Strong from H2 wins over weak from H1.
            if row.confidence != "strong" and funder_strong:
                row.confidence = "strong"
            rows[peer] = row

    # Label-enrich every linked wallet via local CEX label list (cheap, no I/O).
    for peer, row in rows.items():
        if row.label is None:
            row.label = label_for(peer)

    linked = list(rows.values())[:max_linked]

    # Stats: derived from a desc page of the target's normal txs (1 call).
    stats = await _compute_stats(client, target)

    labels = [lbl for lbl in [label_for(target)] if lbl]

    return ClusterResult(
        address=target,
        computed_at=datetime.now(UTC),
        stale=False,
        labels=labels,
        gas_funder=gas_funder_info,
        cex_deposits=[
            CexDepositInfo(address=d.deposit_address, exchange=d.exchange) for d in deposits
        ],
        linked_wallets=linked,
        stats=stats,
    )


async def _compute_stats(client: EtherscanClient, target: str) -> ClusterStats:
    desc = await client.txlist(target, sort="desc", page=1, offset=1)
    asc = await client.txlist(target, sort="asc", page=1, offset=1)
    last_seen = None
    first_seen = None
    if desc:
        ts = _to_int(desc[0].get("timeStamp"))
        if ts > 0:
            last_seen = datetime.fromtimestamp(ts, tz=UTC)
    if asc:
        ts = _to_int(asc[0].get("timeStamp"))
        if ts > 0:
            first_seen = datetime.fromtimestamp(ts, tz=UTC)
    bulk = await client.txlist(target, sort="desc", page=1, offset=100)
    return ClusterStats(first_seen=first_seen, last_seen=last_seen, tx_count=len(bulk))
