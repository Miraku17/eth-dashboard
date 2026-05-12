"""Live on-chain volume endpoint. Reads from realtime_volume table populated
by the realtime listener's MinuteAggregator."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    RealtimeVolumePoint,
    RealtimeVolumeResponse,
    VolumeBucket,
    VolumeSeriesPoint,
    VolumeSeriesResponse,
)
from app.core.db import get_session
from app.core.models import RealtimeVolume

router = APIRouter(prefix="/volume", tags=["volume"])


# Bucket width → (window default minutes, expression-builder).
# The expression-builder takes a `RealtimeVolume.ts_minute` column and
# returns a SQL expression that snaps each minute timestamp to the start
# of its containing bucket. For widths Postgres' `date_trunc` covers
# natively (hour/day/week/month) we use that; the sub-hour widths use
# integer-divide arithmetic on the epoch.
_BUCKET_WINDOWS: dict[VolumeBucket, int] = {
    "1m": 60,
    "5m": 60 * 6,
    "15m": 60 * 18,
    "1h": 60 * 48,
    "4h": 60 * 24 * 7,
    "1d": 60 * 24 * 60,
    "1w": 60 * 24 * 365,
    "1M": 60 * 24 * 365 * 5,
}


def _bucket_expr(bucket: VolumeBucket):
    """Postgres expression that snaps a `realtime_volume.ts_minute` column
    onto the bucket's lower edge. Returned column is `timestamptz` named
    `ts_bucket`."""
    col = RealtimeVolume.ts_minute
    if bucket == "1m":
        return col.label("ts_bucket")
    if bucket in ("1h", "1d", "1w", "1M"):
        unit = {"1h": "hour", "1d": "day", "1w": "week", "1M": "month"}[bucket]
        return func.date_trunc(unit, col).label("ts_bucket")
    # 5m / 15m / 4h — floor the epoch to the bucket width.
    width_seconds = {"5m": 300, "15m": 900, "4h": 14_400}[bucket]
    epoch = func.extract("epoch", col)
    snapped = func.floor(epoch / width_seconds) * width_seconds
    return func.to_timestamp(snapped).label("ts_bucket")


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


@router.get("/series", response_model=VolumeSeriesResponse)
def volume_series(
    session: Annotated[Session, Depends(get_session)],
    bucket: VolumeBucket = Query("1h", description="bucket width"),
    minutes: int | None = Query(
        None,
        ge=1,
        le=60 * 24 * 365 * 5,
        description="look-back window in minutes; defaults to ~60 buckets",
    ),
    asset: list[str] | None = Query(
        None,
        description="restrict to one or more assets (case-sensitive symbol); omit for all stables",
    ),
    limit: int = Query(10000, ge=1, le=100000),
) -> VolumeSeriesResponse:
    """Resampled per-asset on-chain volume curve.

    Resolves the `realtime_volume` table (1-minute resolution stablecoin
    transfer volume populated by the listener's `MinuteAggregator`) into
    the requested bucket width. Designed to back a chart that supports
    1m through 1M timeframes from a single endpoint — bucket math is
    pushed into Postgres so the response stays small.
    """
    if minutes is None:
        minutes = _BUCKET_WINDOWS[bucket]
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    ts_bucket = _bucket_expr(bucket)
    stmt = (
        select(
            ts_bucket,
            RealtimeVolume.asset,
            func.coalesce(func.sum(RealtimeVolume.usd_volume), 0).label("usd_volume"),
            func.coalesce(func.sum(RealtimeVolume.transfer_count), 0).label("transfer_count"),
        )
        .where(RealtimeVolume.ts_minute >= cutoff)
        .group_by("ts_bucket", RealtimeVolume.asset)
        .order_by("ts_bucket", RealtimeVolume.asset)
        .limit(limit)
    )
    if asset:
        stmt = stmt.where(RealtimeVolume.asset.in_(asset))
    rows = session.execute(stmt).all()

    if len(rows) == limit:
        # Soft signal — a full-limit response could be silently truncated.
        raise HTTPException(status_code=400, detail="row limit exceeded; narrow the window")

    assets = sorted({r.asset for r in rows})
    return VolumeSeriesResponse(
        bucket=bucket,
        assets=assets,
        points=[
            VolumeSeriesPoint(
                ts_bucket=r.ts_bucket,
                asset=r.asset,
                usd_volume=float(r.usd_volume),
                transfer_count=int(r.transfer_count),
            )
            for r in rows
        ],
    )
