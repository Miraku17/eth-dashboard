from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BridgeFlowPoint,
    BridgeFlowsResponse,
    ExchangeFlowPoint,
    ExchangeFlowsResponse,
    OnchainVolumePoint,
    OnchainVolumeResponse,
    OrderFlowPoint,
    OrderFlowResponse,
    StablecoinFlowPoint,
    StablecoinFlowsResponse,
    VolumeBucketPoint,
    VolumeBucketsResponse,
)
from app.core.db import get_session
from app.core.models import (
    BridgeFlow,
    ExchangeFlow,
    OnchainVolume,
    OrderFlow,
    StablecoinFlow,
    VolumeBucket,
)

router = APIRouter(prefix="/flows", tags=["flows"])

HoursParam = Annotated[int, Query(ge=1, le=24 * 60, description="look-back window in hours")]


@router.get("/exchange", response_model=ExchangeFlowsResponse)
def exchange_flows(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 48,
    limit: int = Query(5000, ge=1, le=20000),
) -> ExchangeFlowsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(ExchangeFlow)
        .where(ExchangeFlow.ts_bucket >= cutoff)
        .order_by(ExchangeFlow.ts_bucket.desc())
        .limit(limit)
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
    hours: HoursParam = 48,
    limit: int = Query(5000, ge=1, le=20000),
) -> StablecoinFlowsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(StablecoinFlow)
        .where(StablecoinFlow.ts_bucket >= cutoff)
        .order_by(StablecoinFlow.ts_bucket.desc())
        .limit(limit)
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
    hours: HoursParam = 24 * 30,
    limit: int = Query(5000, ge=1, le=20000),
) -> OnchainVolumeResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(OnchainVolume)
        .where(OnchainVolume.ts_bucket >= cutoff)
        .order_by(OnchainVolume.ts_bucket.desc())
        .limit(limit)
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


@router.get("/order-flow", response_model=OrderFlowResponse)
def order_flow(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 24 * 7,
    limit: int = Query(5000, ge=1, le=20000),
) -> OrderFlowResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(OrderFlow)
        .where(OrderFlow.ts_bucket >= cutoff)
        .order_by(OrderFlow.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    points = [
        OrderFlowPoint(
            ts_bucket=r.ts_bucket,
            dex=r.dex,
            side=r.side,  # type: ignore[arg-type]
            usd_value=float(r.usd_value),
            trade_count=r.trade_count,
        )
        for r in reversed(rows)
    ]
    return OrderFlowResponse(points=points)


@router.get("/volume-buckets", response_model=VolumeBucketsResponse)
def volume_buckets(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 24 * 7,
    limit: int = Query(20000, ge=1, le=50000),
) -> VolumeBucketsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(VolumeBucket)
        .where(VolumeBucket.ts_bucket >= cutoff)
        .order_by(VolumeBucket.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    points = [
        VolumeBucketPoint(
            ts_bucket=r.ts_bucket,
            bucket=r.bucket,  # type: ignore[arg-type]
            usd_value=float(r.usd_value),
            trade_count=r.trade_count,
        )
        for r in reversed(rows)
    ]
    return VolumeBucketsResponse(points=points)


@router.get("/bridge", response_model=BridgeFlowsResponse)
def bridge_flows(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 48,
    limit: int = Query(20000, ge=1, le=50000),
) -> BridgeFlowsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(BridgeFlow)
        .where(BridgeFlow.ts_bucket >= cutoff)
        .order_by(BridgeFlow.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    return BridgeFlowsResponse(
        points=[
            BridgeFlowPoint(
                ts_bucket=r.ts_bucket,
                bridge=r.bridge,
                direction=r.direction,  # type: ignore[arg-type]
                asset=r.asset,
                usd_value=float(r.usd_value),
            )
            for r in rows
        ]
    )
