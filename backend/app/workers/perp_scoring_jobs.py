"""Daily cron: replay last 90d of onchain_perp_event into perp_wallet_score."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import get_sessionmaker
from app.core.models import OnchainPerpEvent, PerpWalletScore
from app.services.perp_scoring import (
    LEADERBOARD_LOOKBACK_DAYS,
    PerpEvent,
    score_wallet,
)

log = logging.getLogger(__name__)


async def score_perp_wallets(ctx: dict) -> dict:
    """Rebuild perp_wallet_score from the last 90d of onchain_perp_event.

    Latest-only table — each run rewrites every wallet's row. Cheap because
    the working set is a few thousand rows max.
    """
    SessionLocal = get_sessionmaker()
    cutoff = datetime.now(timezone.utc) - timedelta(days=LEADERBOARD_LOOKBACK_DAYS)
    by_wallet: dict[str, list[PerpEvent]] = defaultdict(list)
    with SessionLocal() as session:
        rows = session.execute(
            select(OnchainPerpEvent).where(OnchainPerpEvent.ts >= cutoff)
        ).scalars()
        for r in rows:
            by_wallet[r.account.lower()].append(
                PerpEvent(
                    ts=r.ts,
                    market=r.market,
                    side=r.side,
                    event_kind=r.event_kind,
                    size_usd=r.size_usd,
                    price_usd=r.price_usd,
                    leverage=r.leverage,
                    pnl_usd=r.pnl_usd,
                )
            )

        written = 0
        for wallet, events in by_wallet.items():
            stats = score_wallet(events)
            if stats.trades_90d == 0:
                continue
            stmt = pg_insert(PerpWalletScore.__table__).values(
                wallet=wallet,
                trades_90d=stats.trades_90d,
                win_rate_90d=stats.win_rate_90d,
                win_rate_long_90d=stats.win_rate_long_90d,
                win_rate_short_90d=stats.win_rate_short_90d,
                realized_pnl_90d=stats.realized_pnl_90d,
                avg_hold_secs=stats.avg_hold_secs,
                avg_position_usd=stats.avg_position_usd,
                avg_leverage=stats.avg_leverage,
                updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["wallet"],
                set_={
                    "trades_90d": stats.trades_90d,
                    "win_rate_90d": stats.win_rate_90d,
                    "win_rate_long_90d": stats.win_rate_long_90d,
                    "win_rate_short_90d": stats.win_rate_short_90d,
                    "realized_pnl_90d": stats.realized_pnl_90d,
                    "avg_hold_secs": stats.avg_hold_secs,
                    "avg_position_usd": stats.avg_position_usd,
                    "avg_leverage": stats.avg_leverage,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            session.execute(stmt)
            written += 1
        session.commit()
    log.info("score_perp_wallets: wrote %d rows", written)
    return {"wallets_scored": written}
