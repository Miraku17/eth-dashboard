from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ExchangeFlowPoint,
    ExchangeFlowsResponse,
    OnchainVolumePoint,
    OnchainVolumeResponse,
    StablecoinFlowPoint,
    StablecoinFlowsResponse,
)
from app.core.db import get_session
from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("/exchange", response_model=ExchangeFlowsResponse)
def exchange_flows(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> ExchangeFlowsResponse:
    rows = session.execute(
        select(ExchangeFlow).order_by(ExchangeFlow.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        ExchangeFlowPoint(
            ts_bucket=r.ts_bucket,
            exchange=r.exchange,
            direction=r.direction,
            asset=r.asset,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return ExchangeFlowsResponse(points=points)


@router.get("/stablecoins", response_model=StablecoinFlowsResponse)
def stablecoin_flows(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> StablecoinFlowsResponse:
    rows = session.execute(
        select(StablecoinFlow).order_by(StablecoinFlow.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        StablecoinFlowPoint(
            ts_bucket=r.ts_bucket,
            asset=r.asset,
            direction=r.direction,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return StablecoinFlowsResponse(points=points)


@router.get("/onchain-volume", response_model=OnchainVolumeResponse)
def onchain_volume(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> OnchainVolumeResponse:
    rows = session.execute(
        select(OnchainVolume).order_by(OnchainVolume.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        OnchainVolumePoint(
            ts_bucket=r.ts_bucket,
            asset=r.asset,
            tx_count=r.tx_count,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return OnchainVolumeResponse(points=points)
