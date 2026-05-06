"""Orchestrate a smart-money leaderboard refresh.

Two source paths are supported:

1. **In-house (default, v5 — 2026-05-06)**: read top-N from the
   `wallet_score` table, which the daily `score_wallets` cron computes
   from `dex_swap` rows captured live by the realtime listener. Adds a
   small per-wallet `dex_swap` aggregation for `weth_bought` / `weth_sold`
   plus a label join. Zero external API spend.

2. **Dune (legacy)**: takes per-wallet aggregate Dune rows (list[dict])
   and runs the approximate PnL engine. Kept as a fallback for the
   `sync_smart_money_leaderboard` cron — useful if we ever need broader
   DEX coverage (Sushi, Maverick, etc.) than the curated 11-pool set
   `dex_swap` watches.

Either path produces a list[WalletPnL] which `persist_snapshot` then
ranks and writes as a single run_id snapshot. The whole persistence is
one transaction so readers never see partial snapshots.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.models import AddressLabel, DexSwap, SmartMoneyLeaderboard, WalletScore
from app.services.pnl_engine import WalletPnL, compute_aggregate_pnl

log = logging.getLogger(__name__)

TOP_N = 50
WALLET_SCORE_WINDOW_DAYS = 30


def compute_pnl_from_wallet_score(
    session: Session, *, top_n: int = TOP_N,
) -> list[WalletPnL]:
    """Build WalletPnL records from the in-house wallet_score table.

    One SQL pass picks the top-N wallets by score and joins them with:
      - dex_swap aggregates (weth_bought, weth_sold) over the same window
      - address_label for human-readable names

    Returns at most `top_n` records. The wallet_score scoring window
    (30d, set by the daily score_wallets cron) is the canonical "smart
    money" window — we don't recompute PnL here, we just reshape it.

    Reads only — caller commits or rolls back via persist_snapshot.
    """
    cutoff = datetime.now(UTC) - timedelta(days=WALLET_SCORE_WINDOW_DAYS)

    # Top-N wallets by score (= realized_pnl_30d in the v1 scoring formula).
    top_rows = session.execute(
        select(
            WalletScore.wallet,
            WalletScore.realized_pnl_30d,
            WalletScore.win_rate_30d,
            WalletScore.trades_30d,
            WalletScore.volume_usd_30d,
        )
        .order_by(WalletScore.score.desc())
        .limit(top_n)
    ).all()
    if not top_rows:
        return []

    top_addrs = [r.wallet for r in top_rows]

    # weth_bought / weth_sold per wallet from dex_swap. side='buy' means
    # user RECEIVED WETH from the pool (price up bet); 'sell' is the
    # mirror. Same convention the swap_decoder uses.
    weth_rows = session.execute(
        select(
            DexSwap.wallet,
            func.sum(case((DexSwap.side == "buy", DexSwap.weth_amount), else_=0))
                .label("weth_bought"),
            func.sum(case((DexSwap.side == "sell", DexSwap.weth_amount), else_=0))
                .label("weth_sold"),
        )
        .where(DexSwap.wallet.in_(top_addrs))
        .where(DexSwap.ts >= cutoff)
        .group_by(DexSwap.wallet)
    ).all()
    weth_by_wallet = {
        r.wallet: (Decimal(str(r.weth_bought or 0)), Decimal(str(r.weth_sold or 0)))
        for r in weth_rows
    }

    # Labels — single SELECT joining by address; absent labels stay None.
    label_rows = session.execute(
        select(AddressLabel.address, AddressLabel.label)
        .where(AddressLabel.address.in_(top_addrs))
    ).all()
    label_by_addr = {r.address: r.label for r in label_rows}

    out: list[WalletPnL] = []
    for r in top_rows:
        weth_bought, weth_sold = weth_by_wallet.get(r.wallet, (Decimal("0"), Decimal("0")))
        out.append(
            WalletPnL(
                wallet=r.wallet,
                label=label_by_addr.get(r.wallet),
                realized_pnl_usd=Decimal(str(r.realized_pnl_30d or 0)),
                # wallet_score doesn't carry unrealized; the rule-based
                # FIFO engine writes only realized. Set to None so the
                # API surfaces a "—" rather than a fake 0.
                unrealized_pnl_usd=None,
                win_rate=Decimal(str(r.win_rate_30d)) if r.win_rate_30d is not None else None,
                trade_count=int(r.trades_30d or 0),
                volume_usd=Decimal(str(r.volume_usd_30d or 0)),
                weth_bought=weth_bought,
                weth_sold=weth_sold,
            )
        )
    return out


def persist_snapshot(
    session: Session,
    *,
    rows: list[dict],
    window_days: int,
    window_end_eth_price: Decimal | None,
    snapshot_at: datetime,
    precomputed_pnls: list[WalletPnL] | None = None,
) -> uuid.UUID | None:
    """Compute ranking from `rows` (or use `precomputed_pnls`), insert a
    snapshot, return its run_id.

    The Dune path passes `rows` and we run `compute_aggregate_pnl` here.
    The in-house path (v5) passes `precomputed_pnls` from
    `compute_pnl_from_wallet_score` and skips the transformation. Either
    way, the result is ranked + persisted as one snapshot.

    Returns None when there's nothing to rank.
    """
    if precomputed_pnls is not None:
        pnls = precomputed_pnls
    else:
        if not rows:
            log.info("leaderboard sync: empty input, skipping persistence")
            return None
        pnls = compute_aggregate_pnl(rows, window_end_eth_price)
    if not pnls:
        log.info("leaderboard sync: no PnLs to rank, skipping persistence")
        return None
    ranked = sorted(pnls, key=lambda p: p.realized_pnl_usd, reverse=True)[:TOP_N]
    run_id = uuid.uuid4()
    session.add_all(
        SmartMoneyLeaderboard(
            run_id=run_id,
            snapshot_at=snapshot_at,
            window_days=window_days,
            rank=rank,
            wallet_address=p.wallet,
            label=p.label,
            realized_pnl_usd=p.realized_pnl_usd,
            unrealized_pnl_usd=p.unrealized_pnl_usd,
            win_rate=p.win_rate,
            trade_count=p.trade_count,
            volume_usd=p.volume_usd,
            weth_bought=p.weth_bought,
            weth_sold=p.weth_sold,
        )
        for rank, p in enumerate(ranked, start=1)
    )
    session.commit()
    log.info(
        "leaderboard sync: wrote %d rows for run_id=%s (top=%s @ $%s)",
        len(ranked), run_id,
        ranked[0].wallet if ranked else None,
        ranked[0].realized_pnl_usd if ranked else None,
    )
    return run_id
