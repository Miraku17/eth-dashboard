from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    SmartMoneyEntry,
    SmartMoneyLeaderboardResponse,
)
from app.core.db import get_session
from app.core.models import SmartMoneyLeaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/smart-money", response_model=SmartMoneyLeaderboardResponse)
def smart_money_leaderboard(
    session: Annotated[Session, Depends(get_session)],
    window_days: int = Query(30, ge=30, le=30, description="v1 supports only 30d"),
    limit: int = Query(50, ge=1, le=50),
) -> SmartMoneyLeaderboardResponse:
    # Find the run_id of the most recent snapshot for this window.
    latest = session.execute(
        select(SmartMoneyLeaderboard.run_id, SmartMoneyLeaderboard.snapshot_at)
        .where(SmartMoneyLeaderboard.window_days == window_days)
        .order_by(SmartMoneyLeaderboard.snapshot_at.desc(), SmartMoneyLeaderboard.id.desc())
        .limit(1)
    ).first()

    if latest is None:
        return SmartMoneyLeaderboardResponse(
            snapshot_at=None, window_days=window_days, entries=[],
        )

    run_id, snapshot_at = latest
    rows = session.execute(
        select(SmartMoneyLeaderboard)
        .where(SmartMoneyLeaderboard.run_id == run_id)
        .order_by(SmartMoneyLeaderboard.rank)
        .limit(limit)
    ).scalars().all()

    entries = [
        SmartMoneyEntry(
            rank=r.rank,
            wallet=r.wallet_address,
            label=r.label,
            realized_pnl_usd=float(r.realized_pnl_usd),
            unrealized_pnl_usd=float(r.unrealized_pnl_usd) if r.unrealized_pnl_usd is not None else None,
            win_rate=float(r.win_rate) if r.win_rate is not None else None,
            trade_count=r.trade_count,
            volume_usd=float(r.volume_usd),
            weth_bought=str(r.weth_bought),
            weth_sold=str(r.weth_sold),
        )
        for r in rows
    ]
    return SmartMoneyLeaderboardResponse(
        snapshot_at=snapshot_at, window_days=window_days, entries=entries,
    )
