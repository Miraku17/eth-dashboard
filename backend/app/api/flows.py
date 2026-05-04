from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BridgeFlowPoint,
    BridgeFlowsResponse,
    CategoryNetFlowResponse,
    CategorySummary,
    CategoryWindow,
    CexNetFlowResponse,
    CexNetFlowWindow,
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
    Transfer,
    VolumeBucket,
)
from app.realtime.flow_classifier import FlowKind

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


_DEFAULT_CEX_WINDOWS = (1, 24)


@router.get("/cex-net-flow", response_model=CexNetFlowResponse)
def cex_net_flow(
    session: Annotated[Session, Depends(get_session)],
    windows: Annotated[
        list[int] | None,
        Query(
            description="Hour windows to compute (e.g. ?windows=1&windows=24). "
            "Default 1h + 24h.",
        ),
    ] = None,
) -> CexNetFlowResponse:
    """Live net-flow into / out of CEX hot wallets, computed from
    `transfers.flow_kind` (the v4 live classifier).

    Positive `net_usd` means more money moving ONTO exchanges (bearish
    signal). Negative means net WITHDRAWAL (bullish — accumulating
    wallets pulling off-exchange). Headline numbers refresh in real
    time as new whale transfers land in `transfers`.
    """
    win_list = sorted(set(windows or _DEFAULT_CEX_WINDOWS))
    now = datetime.now(UTC)

    # One pass per window over `transfers` filtered by flow_kind.
    out_windows: list[CexNetFlowWindow] = []
    longest_cutoff = now - timedelta(hours=max(win_list))

    for h in win_list:
        cutoff = now - timedelta(hours=h)
        agg = session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transfer.flow_kind == FlowKind.WALLET_TO_CEX, Transfer.usd_value),
                            else_=0,
                        )
                    ),
                    0,
                ).label("inflow_usd"),
                func.coalesce(
                    func.sum(
                        case(
                            (Transfer.flow_kind == FlowKind.CEX_TO_WALLET, Transfer.usd_value),
                            else_=0,
                        )
                    ),
                    0,
                ).label("outflow_usd"),
                func.coalesce(
                    func.sum(
                        case((Transfer.flow_kind == FlowKind.WALLET_TO_CEX, 1), else_=0)
                    ),
                    0,
                ).label("inflow_count"),
                func.coalesce(
                    func.sum(
                        case((Transfer.flow_kind == FlowKind.CEX_TO_WALLET, 1), else_=0)
                    ),
                    0,
                ).label("outflow_count"),
            ).where(
                Transfer.ts >= cutoff,
                Transfer.flow_kind.in_(
                    [FlowKind.WALLET_TO_CEX, FlowKind.CEX_TO_WALLET]
                ),
            )
        ).one()
        out_windows.append(
            CexNetFlowWindow(
                hours=h,
                inflow_usd=float(agg.inflow_usd),
                outflow_usd=float(agg.outflow_usd),
                net_usd=float(agg.inflow_usd) - float(agg.outflow_usd),
                inflow_count=int(agg.inflow_count),
                outflow_count=int(agg.outflow_count),
            )
        )

    # Recency + extremes computed across the longest window only.
    latest_in = session.execute(
        select(Transfer.ts)
        .where(
            Transfer.flow_kind == FlowKind.WALLET_TO_CEX,
            Transfer.ts >= longest_cutoff,
        )
        .order_by(Transfer.ts.desc())
        .limit(1)
    ).scalar()
    latest_out = session.execute(
        select(Transfer.ts)
        .where(
            Transfer.flow_kind == FlowKind.CEX_TO_WALLET,
            Transfer.ts >= longest_cutoff,
        )
        .order_by(Transfer.ts.desc())
        .limit(1)
    ).scalar()
    largest_in = session.execute(
        select(func.coalesce(func.max(Transfer.usd_value), 0)).where(
            Transfer.flow_kind == FlowKind.WALLET_TO_CEX,
            Transfer.ts >= longest_cutoff,
        )
    ).scalar() or 0
    largest_out = session.execute(
        select(func.coalesce(func.max(Transfer.usd_value), 0)).where(
            Transfer.flow_kind == FlowKind.CEX_TO_WALLET,
            Transfer.ts >= longest_cutoff,
        )
    ).scalar() or 0

    return CexNetFlowResponse(
        windows=out_windows,
        latest_inflow_ts=latest_in,
        latest_outflow_ts=latest_out,
        largest_inflow_usd=float(largest_in),
        largest_outflow_usd=float(largest_out),
    )


# Category → (label, inflow_kind, outflow_kind). Order matches priority.
_CATEGORY_KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("dex",     "DEX",     FlowKind.WALLET_TO_DEX,     FlowKind.DEX_TO_WALLET),
    ("lending", "Lending", FlowKind.LENDING_DEPOSIT,   FlowKind.LENDING_WITHDRAW),
    ("staking", "Staking", FlowKind.STAKING_DEPOSIT,   FlowKind.STAKING_UNSTAKE),
    ("bridge",  "Bridge",  FlowKind.BRIDGE_L2_DEPOSIT, FlowKind.BRIDGE_L2_WITHDRAW),
)


@router.get("/category-net-flow", response_model=CategoryNetFlowResponse)
def category_net_flow(
    session: Annotated[Session, Depends(get_session)],
    windows: Annotated[
        list[int] | None,
        Query(
            description="Hour windows to compute. Default 1h + 24h.",
        ),
    ] = None,
) -> CategoryNetFlowResponse:
    """Live net-flow per category (DEX / Lending / Staking / Bridge),
    computed from `transfers.flow_kind` (v4 classifier).

    Mirrors /flows/cex-net-flow but covers the four non-CEX categories
    in a single response so the frontend renders one panel with four
    tiles. Same case-when pattern, executes in <50ms per window.
    """
    win_list = sorted(set(windows or _DEFAULT_CEX_WINDOWS))
    now = datetime.now(UTC)

    summaries: list[CategorySummary] = []
    for cat, label, in_kind, out_kind in _CATEGORY_KINDS:
        cat_windows: list[CategoryWindow] = []
        for h in win_list:
            cutoff = now - timedelta(hours=h)
            agg = session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case((Transfer.flow_kind == in_kind, Transfer.usd_value), else_=0)
                        ),
                        0,
                    ).label("inflow_usd"),
                    func.coalesce(
                        func.sum(
                            case((Transfer.flow_kind == out_kind, Transfer.usd_value), else_=0)
                        ),
                        0,
                    ).label("outflow_usd"),
                    func.coalesce(
                        func.sum(case((Transfer.flow_kind == in_kind, 1), else_=0)),
                        0,
                    ).label("inflow_count"),
                    func.coalesce(
                        func.sum(case((Transfer.flow_kind == out_kind, 1), else_=0)),
                        0,
                    ).label("outflow_count"),
                ).where(
                    Transfer.ts >= cutoff,
                    Transfer.flow_kind.in_([in_kind, out_kind]),
                )
            ).one()
            cat_windows.append(
                CategoryWindow(
                    hours=h,
                    inflow_usd=float(agg.inflow_usd),
                    outflow_usd=float(agg.outflow_usd),
                    net_usd=float(agg.inflow_usd) - float(agg.outflow_usd),
                    inflow_count=int(agg.inflow_count),
                    outflow_count=int(agg.outflow_count),
                )
            )
        summaries.append(
            CategorySummary(category=cat, label=label, windows=cat_windows)
        )

    return CategoryNetFlowResponse(summaries=summaries)
