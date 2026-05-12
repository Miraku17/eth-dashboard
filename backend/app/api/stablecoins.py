"""Stablecoin supply / marketcap series.

Reads from `stable_supply` populated by the per-minute `sync_stable_supply`
cron. Resamples to the requested bucket width using the same SQL pattern
as `/api/volume/series` — date_trunc for hour/day/week/month, FLOOR(epoch
/ width) for sub-hour widths.

Per-asset "current" stats compare the most-recent row in the window to
the first row, returning absolute + percent delta — used to populate the
"cap Δ window" tile on the marketcap panel.
"""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    StableSupplySeriesResponse,
    SupplyCurrent,
    SupplyPoint,
    VolumeBucket,
)
from app.core.db import get_session
from app.core.models import StableSupply

router = APIRouter(prefix="/stablecoins", tags=["stablecoins"])


# Lookback window (in minutes) per bucket width, picked so each timeframe
# returns ~60 buckets — gives a chart-shaped curve without an oversized
# response.
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
    col = StableSupply.ts
    if bucket == "1m":
        return col.label("ts_bucket")
    if bucket in ("1h", "1d", "1w", "1M"):
        unit = {"1h": "hour", "1d": "day", "1w": "week", "1M": "month"}[bucket]
        return func.date_trunc(unit, col).label("ts_bucket")
    width_seconds = {"5m": 300, "15m": 900, "4h": 14_400}[bucket]
    epoch = func.extract("epoch", col)
    snapped = func.floor(epoch / width_seconds) * width_seconds
    return func.to_timestamp(snapped).label("ts_bucket")


@router.get("/supply-series", response_model=StableSupplySeriesResponse)
def supply_series(
    session: Annotated[Session, Depends(get_session)],
    bucket: VolumeBucket = Query("1h"),
    minutes: int | None = Query(None, ge=1, le=60 * 24 * 365 * 5),
    asset: list[str] | None = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
) -> StableSupplySeriesResponse:
    """Per-asset stablecoin supply curve plus current-vs-window-start delta."""
    if minutes is None:
        minutes = _BUCKET_WINDOWS[bucket]
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    # For each (bucket, asset) keep the LATEST sample inside the bucket —
    # supply is a stock, not a flow, so averaging would understate. We use
    # MAX(ts) per group to identify the latest row, then a second pass to
    # extract its value. Simpler equivalent: pick the row with the largest
    # ts inside each (bucket, asset), which is what DISTINCT ON gives.
    ts_bucket = _bucket_expr(bucket)
    inner = (
        select(
            ts_bucket,
            StableSupply.asset,
            StableSupply.supply_usd,
            func.row_number()
            .over(
                partition_by=(ts_bucket, StableSupply.asset),
                order_by=StableSupply.ts.desc(),
            )
            .label("rn"),
        )
        .where(StableSupply.ts >= cutoff)
    )
    if asset:
        inner = inner.where(StableSupply.asset.in_(asset))
    sub = inner.subquery()
    stmt = (
        select(sub.c.ts_bucket, sub.c.asset, sub.c.supply_usd)
        .where(sub.c.rn == 1)
        .order_by(sub.c.ts_bucket, sub.c.asset)
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    if len(rows) == limit:
        raise HTTPException(status_code=400, detail="row limit exceeded")

    # Build current / delta-Δ stats per asset.
    by_asset: dict[str, list[tuple[datetime, float]]] = {}
    for r in rows:
        by_asset.setdefault(r.asset, []).append((r.ts_bucket, float(r.supply_usd)))

    current_rows: list[SupplyCurrent] = []
    for sym, series in by_asset.items():
        first_val = series[0][1]
        last_val = series[-1][1]
        delta = last_val - first_val
        pct = (delta / first_val * 100) if first_val > 0 else 0.0
        current_rows.append(
            SupplyCurrent(
                asset=sym,
                supply_usd=last_val,
                delta_usd=delta,
                delta_pct=pct,
            )
        )
    current_rows.sort(key=lambda c: c.supply_usd, reverse=True)

    return StableSupplySeriesResponse(
        bucket=bucket,
        assets=sorted(by_asset.keys()),
        points=[
            SupplyPoint(ts_bucket=r.ts_bucket, asset=r.asset, supply_usd=float(r.supply_usd))
            for r in rows
        ],
        current=current_rows,
        window_label=bucket,
    )
