"""Orchestrate a Dune-backed smart-money leaderboard refresh.

- Takes per-wallet aggregate Dune rows (list[dict]).
- Runs the approximate PnL engine (`compute_aggregate_pnl`).
- Persists the top 50 wallets as a single snapshot (one run_id).

The whole persistence is one transaction — either all rows for a run_id land or
none do. That keeps readers from observing partial snapshots.

The SQL feed is aggregated at the wallet level on Dune's side so the
`/results` payload stays within the free-tier datapoint budget. The more
accurate per-trade FIFO path (`compute_realized_pnl`) remains available for
future use when we move off free tier.
"""
import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.models import SmartMoneyLeaderboard
from app.services.pnl_engine import WalletPnL, compute_aggregate_pnl

log = logging.getLogger(__name__)

TOP_N = 50


def persist_snapshot(
    session: Session,
    *,
    rows: list[dict],
    window_days: int,
    window_end_eth_price: Decimal | None,
    snapshot_at: datetime,
) -> uuid.UUID | None:
    """Compute ranking from `rows`, insert a snapshot, return its run_id.

    Returns None when `rows` is empty (so the caller can leave the previous
    snapshot in place and flag the sync as a no-op).
    """
    if not rows:
        log.info("leaderboard sync: empty input, skipping persistence")
        return None

    pnls: list[WalletPnL] = compute_aggregate_pnl(rows, window_end_eth_price)
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
