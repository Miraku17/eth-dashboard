"""DeFi protocol TVL endpoints. Reads from protocol_tvl table populated by
the hourly DefiLlama sync."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DefiTvlAsset,
    DefiTvlLatestResponse,
    DefiTvlPoint,
    DefiTvlPointsResponse,
    DefiTvlProtocolSnapshot,
    DexPoolTvlLatestResponse,
    DexPoolTvlPoint,
    TvlSeriesPoint,
    TvlSeriesResponse,
    VolumeBucket,
)
from app.core.db import get_session
from app.core.models import DexPoolTvl, ProtocolTvl
from app.services.defi_protocols import DEFI_PROTOCOLS_BY_SLUG

router = APIRouter(prefix="/defi", tags=["defi"])

HoursParam = Annotated[int, Query(ge=1, le=24 * 60, description="look-back window in hours")]


@router.get("/tvl", response_model=DefiTvlPointsResponse)
def defi_tvl(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 168,
    limit: int = Query(20000, ge=1, le=200000),
) -> DefiTvlPointsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(ProtocolTvl)
        .where(ProtocolTvl.ts_bucket >= cutoff)
        .order_by(ProtocolTvl.ts_bucket.asc(), ProtocolTvl.protocol.asc(), ProtocolTvl.asset.asc())
        .limit(limit)
    ).scalars().all()
    return DefiTvlPointsResponse(
        points=[
            DefiTvlPoint(
                ts_bucket=r.ts_bucket,
                protocol=r.protocol,
                asset=r.asset,
                tvl_usd=float(r.tvl_usd),
            )
            for r in rows
        ]
    )


@router.get("/tvl/latest", response_model=DefiTvlLatestResponse)
def defi_tvl_latest(
    session: Annotated[Session, Depends(get_session)],
) -> DefiTvlLatestResponse:
    """Latest hourly snapshot, pre-aggregated per protocol with totals."""
    latest_ts = session.execute(select(ProtocolTvl.ts_bucket).order_by(ProtocolTvl.ts_bucket.desc()).limit(1)).scalar()
    if latest_ts is None:
        return DefiTvlLatestResponse(ts_bucket=None, protocols=[])
    rows = session.execute(
        select(ProtocolTvl).where(ProtocolTvl.ts_bucket == latest_ts)
    ).scalars().all()

    by_protocol: dict[str, list[ProtocolTvl]] = {}
    for r in rows:
        by_protocol.setdefault(r.protocol, []).append(r)

    snapshots: list[DefiTvlProtocolSnapshot] = []
    for slug, prot_rows in by_protocol.items():
        meta = DEFI_PROTOCOLS_BY_SLUG.get(slug)
        display = meta.display_name if meta else slug
        sorted_assets = sorted(prot_rows, key=lambda x: float(x.tvl_usd), reverse=True)
        snapshots.append(
            DefiTvlProtocolSnapshot(
                protocol=slug,
                display_name=display,
                total_usd=float(sum(float(r.tvl_usd) for r in prot_rows)),
                assets=[DefiTvlAsset(asset=r.asset, tvl_usd=float(r.tvl_usd)) for r in sorted_assets],
            )
        )
    snapshots.sort(key=lambda s: s.total_usd, reverse=True)
    return DefiTvlLatestResponse(ts_bucket=latest_ts, protocols=snapshots)


# Lookback per bucket — matches the volume / supply endpoints for a
# consistent feel across every curve panel.
_TVL_BUCKET_WINDOWS: dict[VolumeBucket, int] = {
    "1m": 60,
    "5m": 60 * 6,
    "15m": 60 * 18,
    "1h": 60 * 48,
    "4h": 60 * 24 * 7,
    "1d": 60 * 24 * 60,
    "1w": 60 * 24 * 365,
    "1M": 60 * 24 * 365 * 5,
}


def _tvl_bucket_expr(bucket: VolumeBucket):
    col = ProtocolTvl.ts_bucket
    if bucket == "1m":
        return col.label("ts_b")
    if bucket in ("1h", "1d", "1w", "1M"):
        unit = {"1h": "hour", "1d": "day", "1w": "week", "1M": "month"}[bucket]
        return func.date_trunc(unit, col).label("ts_b")
    width_seconds = {"5m": 300, "15m": 900, "4h": 14_400}[bucket]
    epoch = func.extract("epoch", col)
    snapped = func.floor(epoch / width_seconds) * width_seconds
    return func.to_timestamp(snapped).label("ts_b")


@router.get("/tvl-series", response_model=TvlSeriesResponse)
def tvl_series(
    session: Annotated[Session, Depends(get_session)],
    bucket: VolumeBucket = Query("1h"),
    minutes: int | None = Query(None, ge=1, le=60 * 24 * 365 * 5),
    protocol: list[str] | None = Query(None),
    limit: int = Query(20000, ge=1, le=200000),
) -> TvlSeriesResponse:
    """Per-protocol DeFi TVL curve, bucket-resampled from `protocol_tvl`.

    TVL is a stock, so we keep the LATEST row per (bucket, protocol)
    rather than averaging — same pattern as the stablecoin supply series.
    Asset breakdown is aggregated up to the protocol level so each line
    is a single curve per protocol regardless of how many underlying
    assets DefiLlama exposes.
    """
    if minutes is None:
        minutes = _TVL_BUCKET_WINDOWS[bucket]
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    ts_b = _tvl_bucket_expr(bucket)
    # Sum across assets first (one row per (ts_bucket, protocol, ts_b)),
    # then pick the latest snapshot in each (ts_b, protocol) bucket.
    asset_sum = (
        select(
            ProtocolTvl.ts_bucket.label("ts_inner"),
            ProtocolTvl.protocol,
            ts_b,
            func.coalesce(func.sum(ProtocolTvl.tvl_usd), 0).label("tvl_usd"),
        )
        .where(ProtocolTvl.ts_bucket >= cutoff)
        .group_by(ProtocolTvl.ts_bucket, ProtocolTvl.protocol, "ts_b")
    )
    if protocol:
        asset_sum = asset_sum.where(ProtocolTvl.protocol.in_(protocol))
    asset_sum = asset_sum.subquery()

    ranked = (
        select(
            asset_sum.c.ts_b,
            asset_sum.c.protocol,
            asset_sum.c.tvl_usd,
            func.row_number()
            .over(
                partition_by=(asset_sum.c.ts_b, asset_sum.c.protocol),
                order_by=asset_sum.c.ts_inner.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    rows = session.execute(
        select(ranked.c.ts_b, ranked.c.protocol, ranked.c.tvl_usd)
        .where(ranked.c.rn == 1)
        .order_by(ranked.c.ts_b, ranked.c.protocol)
        .limit(limit)
    ).all()
    if len(rows) == limit:
        raise HTTPException(status_code=400, detail="row limit exceeded")

    return TvlSeriesResponse(
        bucket=bucket,
        protocols=sorted({r.protocol for r in rows}),
        points=[
            TvlSeriesPoint(
                ts_bucket=r.ts_b,
                protocol=r.protocol,
                tvl_usd=float(r.tvl_usd),
            )
            for r in rows
        ],
    )


@router.get("/dex-pools/latest", response_model=DexPoolTvlLatestResponse)
def dex_pools_latest(
    session: Annotated[Session, Depends(get_session)],
) -> DexPoolTvlLatestResponse:
    """Latest hourly snapshot of top-N DEX pools, sorted desc by tvl_usd."""
    latest_ts = session.execute(
        select(DexPoolTvl.ts_bucket).order_by(DexPoolTvl.ts_bucket.desc()).limit(1)
    ).scalar()
    if latest_ts is None:
        return DexPoolTvlLatestResponse(ts_bucket=None, pools=[])
    rows = session.execute(
        select(DexPoolTvl)
        .where(DexPoolTvl.ts_bucket == latest_ts)
        .order_by(DexPoolTvl.tvl_usd.desc())
    ).scalars().all()
    return DexPoolTvlLatestResponse(
        ts_bucket=latest_ts,
        pools=[
            DexPoolTvlPoint(
                pool_id=r.pool_id,
                dex=r.dex,
                symbol=r.symbol,
                tvl_usd=float(r.tvl_usd),
            )
            for r in rows
        ],
    )
