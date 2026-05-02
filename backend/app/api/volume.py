"""Live on-chain volume endpoint. Reads from realtime_volume table populated
by the realtime listener's MinuteAggregator."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import RealtimeVolumePoint, RealtimeVolumeResponse
from app.core.db import get_session
from app.core.models import RealtimeVolume

router = APIRouter(prefix="/volume", tags=["volume"])


@router.get("/realtime", response_model=RealtimeVolumeResponse)
def realtime_volume(
    session: Annotated[Session, Depends(get_session)],
    minutes: int = Query(60, ge=1, le=24 * 60, description="look-back window in minutes"),
    limit: int = Query(20000, ge=1, le=200000),
) -> RealtimeVolumeResponse:
    """Per-minute on-chain volume per stable asset, ordered ts asc."""
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = session.execute(
        select(RealtimeVolume)
        .where(RealtimeVolume.ts_minute >= cutoff)
        .order_by(RealtimeVolume.ts_minute.asc(), RealtimeVolume.asset.asc())
        .limit(limit)
    ).scalars().all()
    return RealtimeVolumeResponse(
        points=[
            RealtimeVolumePoint(
                ts_minute=r.ts_minute,
                asset=r.asset,
                transfer_count=r.transfer_count,
                usd_volume=float(r.usd_volume),
            )
            for r in rows
        ]
    )
