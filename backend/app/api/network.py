from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.schemas import NetworkPointOut, NetworkSeriesResponse, NetworkSummary
from app.core.db import get_session
from app.core.models import NetworkActivity

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/summary", response_model=NetworkSummary)
def network_summary(
    session: Annotated[Session, Depends(get_session)],
) -> NetworkSummary:
    """Return the latest block stats + short-window rolling averages."""
    latest = session.execute(
        select(NetworkActivity).order_by(desc(NetworkActivity.ts)).limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return NetworkSummary(
            latest_ts=None,
            gas_price_gwei=None,
            base_fee_gwei=None,
            tx_count=None,
            avg_block_seconds=None,
            avg_tx_per_block=None,
        )

    cutoff = latest.ts - timedelta(minutes=15)
    recent = session.execute(
        select(NetworkActivity)
        .where(NetworkActivity.ts >= cutoff)
        .order_by(NetworkActivity.ts.asc())
    ).scalars().all()

    if len(recent) >= 2:
        span = (recent[-1].ts - recent[0].ts).total_seconds()
        avg_block = span / max(1, len(recent) - 1)
        avg_tx = sum(r.tx_count for r in recent) / len(recent)
    else:
        avg_block = None
        avg_tx = float(latest.tx_count)

    return NetworkSummary(
        latest_ts=latest.ts,
        gas_price_gwei=float(latest.gas_price_gwei),
        base_fee_gwei=float(latest.base_fee),
        tx_count=latest.tx_count,
        avg_block_seconds=avg_block,
        avg_tx_per_block=avg_tx,
    )


@router.get("/series", response_model=NetworkSeriesResponse)
def network_series(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 7),
    limit: int = Query(2000, ge=1, le=20000),
) -> NetworkSeriesResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(NetworkActivity)
        .where(NetworkActivity.ts >= cutoff)
        .order_by(NetworkActivity.ts.desc())
        .limit(limit)
    ).scalars().all()
    points = [
        NetworkPointOut(
            ts=r.ts,
            tx_count=r.tx_count,
            gas_price_gwei=float(r.gas_price_gwei),
            base_fee_gwei=float(r.base_fee),
        )
        for r in reversed(rows)
    ]
    return NetworkSeriesResponse(points=points)
