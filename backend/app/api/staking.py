"""Staking layer endpoints — beacon-chain deposit/withdrawal flows
and a live active-validator-count summary tile."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    LstSupplyPoint,
    LstSupplyResponse,
    StakingFlowByEntityPoint,
    StakingFlowPoint,
    StakingFlowsByEntityResponse,
    StakingFlowsResponse,
    StakingSummary,
)
from app.clients.beacon import BeaconClient
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import LstSupply, StakingFlow, StakingFlowByEntity

router = APIRouter(prefix="/staking", tags=["staking"])

HoursParam = Annotated[int, Query(ge=1, le=24 * 60, description="look-back window in hours")]


@router.get("/flows", response_model=StakingFlowsResponse)
def staking_flows(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 48,
    limit: int = Query(5000, ge=1, le=20000),
) -> StakingFlowsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(StakingFlow)
        .where(StakingFlow.ts_bucket >= cutoff)
        .order_by(StakingFlow.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    return StakingFlowsResponse(
        points=[
            StakingFlowPoint(
                ts_bucket=r.ts_bucket,
                kind=r.kind,
                amount_eth=float(r.amount_eth),
                amount_usd=float(r.amount_usd) if r.amount_usd is not None else None,
            )
            for r in rows
        ]
    )


@router.get("/summary", response_model=StakingSummary)
async def staking_summary(
    session: Annotated[Session, Depends(get_session)],
) -> StakingSummary:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    rows = session.execute(
        select(StakingFlow).where(StakingFlow.ts_bucket >= cutoff)
    ).scalars().all()

    deposits = sum(float(r.amount_eth) for r in rows if r.kind == "deposit")
    full_w = sum(float(r.amount_eth) for r in rows if r.kind == "withdrawal_full")

    settings = get_settings()
    active_count: int | None = None
    if settings.beacon_http_url:
        async with httpx.AsyncClient(base_url=settings.beacon_http_url) as http:
            client = BeaconClient(http)
            active_count = await client.active_validator_count()

    return StakingSummary(
        active_validator_count=active_count,
        total_eth_staked_30d=deposits,
        net_eth_staked_30d=deposits - full_w,
    )


@router.get("/lst-supply", response_model=LstSupplyResponse)
def lst_supply(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 720,  # default 30 days for the panel
    limit: int = Query(20000, ge=1, le=200000),
) -> LstSupplyResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(LstSupply)
        .where(LstSupply.ts_bucket >= cutoff)
        .order_by(LstSupply.ts_bucket.asc(), LstSupply.token.asc())
        .limit(limit)
    ).scalars().all()
    return LstSupplyResponse(
        points=[
            LstSupplyPoint(
                ts_bucket=r.ts_bucket,
                token=r.token,
                supply=float(r.supply),
            )
            for r in rows
        ]
    )


@router.get("/flows/by-entity", response_model=StakingFlowsByEntityResponse)
def staking_flows_by_entity(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 720,  # default 30 days for the per-entity table
    limit: int = Query(20000, ge=1, le=200000),
) -> StakingFlowsByEntityResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(StakingFlowByEntity)
        .where(StakingFlowByEntity.ts_bucket >= cutoff)
        .order_by(StakingFlowByEntity.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    return StakingFlowsByEntityResponse(
        points=[
            StakingFlowByEntityPoint(
                ts_bucket=r.ts_bucket,
                kind=r.kind,
                entity=r.entity,
                amount_eth=float(r.amount_eth),
                amount_usd=float(r.amount_usd) if r.amount_usd is not None else None,
            )
            for r in rows
        ]
    )
