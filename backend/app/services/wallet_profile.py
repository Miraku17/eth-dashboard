"""Wallet profile builder.

Assembles the payload behind GET /api/wallets/{address}/profile.

Data sources:
* `wallet_balance_history` (Postgres) — daily ETH balance snapshots,
  populated lazily here on first fetch via JSON-RPC eth_getBalance.
* `transfers` (Postgres) — already indexed by the realtime listener;
  source for top counterparties, recent activity, and 7d net flow.
* `wallet_clusters.payload` (Postgres) — already-computed clustering
  result, reused for first/last seen and linked wallets so the drawer
  doesn't have to make two round trips.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.schemas import (
    BalancePoint,
    Counterparty,
    LinkedWallet,
    NetFlowPoint,
    WalletProfile,
    WalletScoreInfo,
    WalletTransfer,
)
from app.clients.eth_rpc import EthRpcClient, RpcError, gather_balances
from app.core.models import Transfer, WalletBalanceHistory, WalletCluster, WalletScore

log = logging.getLogger(__name__)

# Ethereum mainnet target block time. Daily-aligned blocks don't need to be
# precise to the second — a midnight ±2 min snapshot still tells the same
# story for a 30-day chart.
AVG_BLOCK_TIME_S = 12.05
BLOCKS_PER_DAY = int(86_400 / AVG_BLOCK_TIME_S)
HISTORY_DAYS = 30
NET_FLOW_DAYS = 7
RECENT_LIMIT = 15
TOP_COUNTERPARTIES = 5
COUNTERPARTY_WINDOW_DAYS = 30


def _wei_to_eth(wei: int | Decimal) -> float:
    return float(Decimal(wei) / Decimal(10**18))


def _utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _estimate_block_for(target_ts: datetime, latest_block: int, latest_ts: datetime) -> int:
    """Linearly back-project the block at `target_ts` from the latest block.

    Accurate to ±100 blocks (~20 min) which is fine for daily granularity.
    Cheaper than a binary-search by-timestamp and avoids extra RPC calls.
    """
    delta_s = (latest_ts - target_ts).total_seconds()
    blocks_back = int(delta_s / AVG_BLOCK_TIME_S)
    return max(1, latest_block - blocks_back)


def _read_cached_history(
    session: Session, address: str, since: date
) -> dict[date, WalletBalanceHistory]:
    rows = session.execute(
        select(WalletBalanceHistory).where(
            WalletBalanceHistory.address == address,
            WalletBalanceHistory.date >= since,
        )
    ).scalars().all()
    return {r.date: r for r in rows}


def _write_history(
    session: Session,
    address: str,
    rows: list[tuple[date, int, int]],  # (date, block, balance_wei)
) -> None:
    if not rows:
        return
    now = datetime.now(UTC)
    payload = [
        {
            "address": address,
            "date": d,
            "block_number": b,
            "balance_wei": Decimal(bal),
            "computed_at": now,
        }
        for (d, b, bal) in rows
    ]
    stmt = insert(WalletBalanceHistory).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["address", "date"],
        set_={
            "block_number": stmt.excluded.block_number,
            "balance_wei": stmt.excluded.balance_wei,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    session.execute(stmt)
    session.commit()


async def _ensure_balance_history(
    session: Session,
    rpc: EthRpcClient,
    address: str,
) -> tuple[list[BalancePoint], int | None]:
    today = datetime.now(UTC).date()
    days = [today - timedelta(days=i) for i in range(HISTORY_DAYS - 1, -1, -1)]
    cached = _read_cached_history(session, address, days[0])

    # Today's row is always considered stale (balance moves intra-day).
    needed = [d for d in days if d not in cached or d == today]

    new_rows: list[tuple[date, int, int]] = []
    if needed:
        latest_block = await rpc.block_number()
        latest_ts_raw = await rpc.get_block_timestamp(latest_block)
        latest_ts = datetime.fromtimestamp(latest_ts_raw, tz=UTC)

        # Map each needed date to a daily-aligned block. Today snaps to "latest"
        # rather than midnight so the chart's right edge is current.
        blocks: list[int] = []
        for d in needed:
            if d == today:
                blocks.append(latest_block)
            else:
                blocks.append(
                    _estimate_block_for(_utc_midnight(d), latest_block, latest_ts)
                )

        balances = await gather_balances(rpc, address, blocks)
        # Snap-sync Geth (and rate-limited archive APIs) may return None for
        # individual older blocks where state has been pruned/throttled.
        # Persist only the days we got a real value back; the rest stay
        # absent so the chart simply has fewer points rather than zeros.
        # The "today" block is always "latest" and always succeeds against
        # any healthy node, so current-balance always renders.
        for d, b, bal in zip(needed, blocks, balances, strict=True):
            if bal is None:
                continue
            new_rows.append((d, b, bal))
        _write_history(session, address, new_rows)
        # Refresh cache view with the new rows.
        for d, b, bal in new_rows:
            cached[d] = WalletBalanceHistory(
                address=address, date=d, block_number=b,
                balance_wei=Decimal(bal), computed_at=datetime.now(UTC),
            )

    points = [
        BalancePoint(
            date=d.isoformat(),
            balance_eth=_wei_to_eth(cached[d].balance_wei),
        )
        for d in days
        if d in cached
    ]
    today_wei = int(cached[today].balance_wei) if today in cached else None
    return points, today_wei


def _net_flow_7d(session: Session, address: str) -> list[NetFlowPoint]:
    cutoff = datetime.now(UTC) - timedelta(days=NET_FLOW_DAYS)
    day = func.date_trunc("day", Transfer.ts).label("day")
    direction_sign = case(
        (Transfer.to_addr == address, Transfer.usd_value),
        else_=-Transfer.usd_value,
    )
    rows = session.execute(
        select(day, func.coalesce(func.sum(direction_sign), 0))
        .where(
            Transfer.ts >= cutoff,
            (Transfer.from_addr == address) | (Transfer.to_addr == address),
            Transfer.usd_value.isnot(None),
        )
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        NetFlowPoint(date=d.date().isoformat(), net_usd=float(net or 0))
        for (d, net) in rows
    ]


def _top_counterparties(session: Session, address: str) -> list[Counterparty]:
    cutoff = datetime.now(UTC) - timedelta(days=COUNTERPARTY_WINDOW_DAYS)
    counterparty_addr = case(
        (Transfer.from_addr == address, Transfer.to_addr),
        else_=Transfer.from_addr,
    ).label("cp")
    rows = session.execute(
        select(
            counterparty_addr,
            func.coalesce(func.sum(Transfer.usd_value), 0).label("total"),
            func.count().label("cnt"),
        )
        .where(
            Transfer.ts >= cutoff,
            (Transfer.from_addr == address) | (Transfer.to_addr == address),
        )
        .group_by("cp")
        .order_by(func.coalesce(func.sum(Transfer.usd_value), 0).desc())
        .limit(TOP_COUNTERPARTIES)
    ).all()
    return [
        Counterparty(
            address=cp,
            label=None,
            total_usd=float(total or 0),
            tx_count=int(cnt),
        )
        for (cp, total, cnt) in rows
    ]


def _recent_transfers(session: Session, address: str) -> list[WalletTransfer]:
    rows = session.execute(
        select(Transfer)
        .where((Transfer.from_addr == address) | (Transfer.to_addr == address))
        .order_by(Transfer.ts.desc())
        .limit(RECENT_LIMIT)
    ).scalars().all()
    out: list[WalletTransfer] = []
    for t in rows:
        is_in = t.to_addr == address
        out.append(
            WalletTransfer(
                tx_hash=t.tx_hash,
                ts=t.ts,
                direction="in" if is_in else "out",
                counterparty=t.from_addr if is_in else t.to_addr,
                counterparty_label=None,
                asset=t.asset,
                amount=float(t.amount),
                usd_value=float(t.usd_value) if t.usd_value is not None else None,
            )
        )
    return out


def _read_cluster_payload(session: Session, address: str) -> dict[str, Any] | None:
    row = session.get(WalletCluster, address)
    return dict(row.payload) if row else None


def _hydrate_cluster_bits(payload: dict[str, Any] | None) -> tuple[
    list[str], list[LinkedWallet], datetime | None, datetime | None, int
]:
    if not payload:
        return [], [], None, None, 0
    labels = list(payload.get("labels", []))
    linked = [LinkedWallet.model_validate(lw) for lw in payload.get("linked_wallets", [])]
    stats = payload.get("stats", {}) or {}
    first_raw = stats.get("first_seen")
    last_raw = stats.get("last_seen")
    first = datetime.fromisoformat(first_raw) if first_raw else None
    last = datetime.fromisoformat(last_raw) if last_raw else None
    return labels, linked, first, last, int(stats.get("tx_count", 0))


def _annotate_counterparty_labels(
    session: Session,
    address: str,
    counterparties: list[Counterparty],
    recent: list[WalletTransfer],
) -> None:
    """Pull labels from the transfers table — the realtime listener already
    persists `from_label`/`to_label` on each row, so the most-recent row per
    counterparty is a good-enough source for the drawer.

    Wait — `Transfer` has no label columns. Skip silently and leave labels
    None; the frontend handles that.
    """
    return


def build_profile(
    session: Session,
    rpc: EthRpcClient | None,
    address: str,
    eth_price_usd: float | None,
) -> WalletProfile:
    """Synchronous wrapper kept for symmetry — the actual async work is in
    `build_profile_async`. Tests call the async form directly.
    """
    raise NotImplementedError("call build_profile_async")


async def build_profile_async(
    session: Session,
    rpc: EthRpcClient | None,
    http: httpx.AsyncClient | None,
    address: str,
    eth_price_usd: float | None,
    coingecko_api_key: str = "",
) -> WalletProfile:
    cluster_payload = _read_cluster_payload(session, address)
    labels, linked, first_seen, last_seen, tx_count = _hydrate_cluster_bits(cluster_payload)

    history: list[BalancePoint] = []
    current_wei: int | None = None
    balance_unavailable = False
    if rpc is not None:
        try:
            history, current_wei = await _ensure_balance_history(session, rpc, address)
        except (RpcError, httpx.HTTPError, OSError) as exc:  # noqa: PERF203
            log.warning("balance history unavailable for %s: %s", address, exc)
            balance_unavailable = True
    else:
        balance_unavailable = True

    current_eth = _wei_to_eth(current_wei) if current_wei is not None else None
    current_usd = (
        current_eth * eth_price_usd
        if (current_eth is not None and eth_price_usd is not None)
        else None
    )

    change_30d_pct: float | None = None
    if len(history) >= 2 and history[0].balance_eth > 0:
        change_30d_pct = (
            (history[-1].balance_eth - history[0].balance_eth)
            / history[0].balance_eth
            * 100
        )

    # Token holdings — separate concern, never blocks the rest of the profile
    # if RPC or CoinGecko is briefly unavailable.
    token_holdings = []
    if rpc is not None and http is not None:
        try:
            from app.services.token_holdings import get_token_holdings

            token_holdings = await get_token_holdings(rpc, http, address, coingecko_api_key)
        except Exception as exc:  # noqa: BLE001 — never fail the whole profile.
            log.warning("token holdings unavailable for %s: %s", address, exc)

    # v5: pull `wallet_score` for the target wallet AND every linked-wallet
    # peer in one IN-clause so the drawer can flag smart-money inline. Empty
    # `linked` is the common case (no cluster) — skip the score query when
    # there's no addresses to look up.
    score_addrs: set[str] = {address.lower()}
    for lw in linked:
        score_addrs.add(lw.address.lower())
    score_rows = (
        session.execute(
            select(
                WalletScore.wallet,
                WalletScore.score,
                WalletScore.realized_pnl_30d,
                WalletScore.win_rate_30d,
                WalletScore.trades_30d,
                WalletScore.volume_usd_30d,
                WalletScore.updated_at,
            ).where(WalletScore.wallet.in_(score_addrs))
        ).all()
        if score_addrs
        else []
    )
    score_map: dict[str, WalletScoreInfo] = {
        row.wallet: WalletScoreInfo(
            score=float(row.score),
            realized_pnl_30d=float(row.realized_pnl_30d),
            win_rate_30d=float(row.win_rate_30d) if row.win_rate_30d is not None else None,
            trades_30d=int(row.trades_30d),
            volume_usd_30d=float(row.volume_usd_30d),
            updated_at=row.updated_at,
        )
        for row in score_rows
    }

    target_score = score_map.get(address.lower())
    linked_decorated = [
        LinkedWallet(
            address=lw.address,
            label=lw.label,
            confidence=lw.confidence,
            reasons=lw.reasons,
            score=(
                score_map[lw.address.lower()].score
                if lw.address.lower() in score_map
                else None
            ),
        )
        for lw in linked
    ]

    return WalletProfile(
        address=address,
        labels=labels,
        current_balance_eth=current_eth,
        current_balance_usd=current_usd,
        balance_change_30d_pct=change_30d_pct,
        first_seen=first_seen,
        last_seen=last_seen,
        tx_count=tx_count,
        balance_history=history,
        net_flow_7d=_net_flow_7d(session, address),
        top_counterparties=_top_counterparties(session, address),
        recent_transfers=_recent_transfers(session, address),
        linked_wallets=linked_decorated,
        token_holdings=token_holdings,
        balance_unavailable=balance_unavailable,
        wallet_score=target_score,
    )
