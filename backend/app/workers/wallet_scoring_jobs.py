"""score_wallets — daily cron that recomputes wallet_score from dex_swap.

Reads the last 30d of swap rows, groups by wallet, runs the FIFO scorer
per wallet, upserts results into wallet_score. Latest-only — no history
table — because the panel reads top-N by current score.

Cron schedule: daily at 04:13 UTC. Offset from the smart_money_leaderboard
cron at 03:00 UTC so the two heavy daily jobs don't overlap on the worker.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import get_sessionmaker
from app.core.models import DexSwap, WalletScore
from app.core.sync_status import record_sync_ok
from app.services.wallet_scoring import SwapRow, group_swaps, score_all_wallets

log = logging.getLogger(__name__)

_WINDOW_DAYS = 30
# Wallets below this trade count are excluded from wallet_score entirely —
# noise filter. The panel doesn't care about a wallet that did one swap
# and stopped.
_MIN_TRADES_FOR_SCORING = 5


async def score_wallets(ctx: dict) -> dict:
    """Recompute wallet_score from the last 30d of dex_swap rows."""
    SessionLocal = get_sessionmaker()
    cutoff = datetime.now(UTC) - timedelta(days=_WINDOW_DAYS)

    with SessionLocal() as session:
        rows = session.execute(
            select(
                DexSwap.wallet,
                DexSwap.ts,
                DexSwap.side,
                DexSwap.weth_amount,
                DexSwap.usd_value,
            )
            .where(DexSwap.ts >= cutoff)
            .order_by(DexSwap.wallet, DexSwap.ts)
        ).all()

    if not rows:
        log.warning("score_wallets: no dex_swap rows in last %dd — skipping", _WINDOW_DAYS)
        return {"action": "skipped", "reason": "no swap rows", "rows": 0}

    # Build the (wallet -> ordered swap list) map. The query already
    # ordered by (wallet, ts) so we can do this in a single pass without
    # the group_swaps helper, but using the helper keeps the compute
    # decoupled from query ordering.
    wallets = [r.wallet for r in rows]
    swaps = [
        SwapRow(
            ts=r.ts,
            side=r.side,
            weth_amount=float(r.weth_amount),
            usd_value=float(r.usd_value),
        )
        for r in rows
    ]
    by_wallet = group_swaps(swaps, wallets)

    # Filter out low-activity wallets BEFORE scoring; cuts compute on the
    # long tail of one-swap wallets that won't show up in any panel.
    by_wallet = {w: s for w, s in by_wallet.items() if len(s) >= _MIN_TRADES_FOR_SCORING}
    if not by_wallet:
        return {"action": "skipped", "reason": "no wallets above min trades"}

    metrics = score_all_wallets(by_wallet)

    now = datetime.now(UTC)
    score_rows = [
        {
            "wallet": wallet,
            "trades_30d": m.trades,
            "volume_usd_30d": round(m.volume_usd, 2),
            "realized_pnl_30d": round(m.realized_pnl, 2),
            "win_rate_30d": m.win_rate,
            # v1 score == realized PnL. Future: blend in win_rate × log(volume).
            "score": float(m.realized_pnl),
            "updated_at": now,
        }
        for wallet, m in metrics.items()
    ]

    with SessionLocal() as session:
        # Bulk upsert — replace all metrics for each wallet that had
        # activity in the window.
        stmt = pg_insert(WalletScore).values(score_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["wallet"],
            set_={
                "trades_30d": stmt.excluded.trades_30d,
                "volume_usd_30d": stmt.excluded.volume_usd_30d,
                "realized_pnl_30d": stmt.excluded.realized_pnl_30d,
                "win_rate_30d": stmt.excluded.win_rate_30d,
                "score": stmt.excluded.score,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        session.execute(stmt)
        session.commit()

    record_sync_ok("wallet_score")
    log.info(
        "scored %d wallets from %d swap rows (window=%dd)",
        len(score_rows), len(rows), _WINDOW_DAYS,
    )
    return {
        "scored": len(score_rows),
        "swap_rows": len(rows),
        "window_days": _WINDOW_DAYS,
    }
