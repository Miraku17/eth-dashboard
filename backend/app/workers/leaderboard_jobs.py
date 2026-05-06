"""arq task entrypoint for the smart-money leaderboard sync.

v5 (2026-05-06): migrated off Dune. The default path now reads from
`wallet_score`, which the daily `score_wallets` cron populates from the
realtime listener's `dex_swap` capture. The Dune query ID is preserved
in `.env` (DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD) for rollback but no
longer executed.
"""
import logging
from datetime import UTC, datetime

from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.leaderboard_sync import (
    compute_pnl_from_wallet_score,
    persist_snapshot,
)

log = logging.getLogger(__name__)

WINDOW_DAYS = 30


async def sync_smart_money_leaderboard(ctx: dict) -> dict:
    """Recompute the smart-money leaderboard from wallet_score.

    Runs daily at 03:00 UTC, ~5h after `score_wallets` finishes (which
    runs at 04:13 UTC the day before — so the wallet_score table has
    yesterday's full-day picture by the time this fires). No external
    API spend.

    Window-end ETH price isn't needed for the in-house path; wallet_score
    already stores realized PnL in USD terms via dex_swap.usd_value, so
    the unrealized leg is omitted (set to None per WalletPnL).
    """
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        pnls = compute_pnl_from_wallet_score(session)
        if not pnls:
            log.warning(
                "smart-money sync: wallet_score is empty — score_wallets cron may "
                "not have run yet, or dex_swap captured no rows in the window",
            )
            return {"skipped": "wallet_score empty"}

        run_id = persist_snapshot(
            session,
            rows=[],  # unused on the in-house path
            window_days=WINDOW_DAYS,
            window_end_eth_price=None,
            snapshot_at=datetime.now(UTC),
            precomputed_pnls=pnls,
        )

    if run_id is None:
        return {"skipped": "no rows after ranking"}
    record_sync_ok("smart_money")
    return {"run_id": str(run_id), "rows": len(pnls)}
