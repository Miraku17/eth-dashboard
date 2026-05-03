"""LRT (Liquid Restaking Token) TVL endpoint. Reads from the lrt_tvl table
populated by the hourly DefiLlama sync."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import LrtTvlLatestResponse, LrtTvlPoint
from app.core.db import get_session
from app.core.models import LrtTvl
from app.services.lrt_protocols import LRT_PROTOCOLS_BY_SLUG

router = APIRouter(prefix="/restaking", tags=["restaking"])


@router.get("/lrt-tvl/latest", response_model=LrtTvlLatestResponse)
def lrt_tvl_latest(
    session: Annotated[Session, Depends(get_session)],
) -> LrtTvlLatestResponse:
    """Latest hourly snapshot, one row per LRT issuer, sorted desc by tvl_usd."""
    latest_ts = session.execute(
        select(LrtTvl.ts_bucket).order_by(LrtTvl.ts_bucket.desc()).limit(1)
    ).scalar()
    if latest_ts is None:
        return LrtTvlLatestResponse(ts_bucket=None, total_usd=0.0, protocols=[])
    rows = session.execute(
        select(LrtTvl)
        .where(LrtTvl.ts_bucket == latest_ts)
        .order_by(LrtTvl.tvl_usd.desc())
    ).scalars().all()

    points: list[LrtTvlPoint] = []
    total = 0.0
    for r in rows:
        meta = LRT_PROTOCOLS_BY_SLUG.get(r.protocol)
        display = meta.display_name if meta else r.protocol
        token = meta.token if meta else ""
        tvl = float(r.tvl_usd)
        total += tvl
        points.append(
            LrtTvlPoint(
                protocol=r.protocol,
                display_name=display,
                token=token,
                tvl_usd=tvl,
            )
        )
    return LrtTvlLatestResponse(ts_bucket=latest_ts, total_usd=total, protocols=points)
