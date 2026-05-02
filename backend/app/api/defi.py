"""DeFi protocol TVL endpoints. Reads from protocol_tvl table populated by
the hourly DefiLlama sync."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DefiTvlAsset,
    DefiTvlLatestResponse,
    DefiTvlPoint,
    DefiTvlPointsResponse,
    DefiTvlProtocolSnapshot,
)
from app.core.db import get_session
from app.core.models import ProtocolTvl
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
