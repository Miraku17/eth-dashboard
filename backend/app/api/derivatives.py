from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DerivativesLatest,
    DerivativesPoint,
    DerivativesSeriesResponse,
    DerivativesSummary,
    LiquidationBucket,
    LiquidationResponse,
    LiquidationSummary,
)
from app.core.db import get_session
from app.core.models import DerivativesSnapshot, PerpLiquidation

router = APIRouter(prefix="/derivatives", tags=["derivatives"])


@router.get("/summary", response_model=DerivativesSummary)
def summary(
    session: Annotated[Session, Depends(get_session)],
) -> DerivativesSummary:
    # Latest row per exchange (and symbol) — correlated subquery.
    latest_ts_sub = (
        select(
            DerivativesSnapshot.exchange,
            DerivativesSnapshot.symbol,
            func.max(DerivativesSnapshot.ts).label("max_ts"),
        )
        .group_by(DerivativesSnapshot.exchange, DerivativesSnapshot.symbol)
        .subquery()
    )
    rows = session.execute(
        select(DerivativesSnapshot).join(
            latest_ts_sub,
            (DerivativesSnapshot.exchange == latest_ts_sub.c.exchange)
            & (DerivativesSnapshot.symbol == latest_ts_sub.c.symbol)
            & (DerivativesSnapshot.ts == latest_ts_sub.c.max_ts),
        )
    ).scalars().all()

    latest = [
        DerivativesLatest(
            exchange=r.exchange,
            symbol=r.symbol,
            ts=r.ts,
            oi_usd=float(r.oi_usd) if r.oi_usd is not None else None,
            funding_rate=float(r.funding_rate) if r.funding_rate is not None else None,
            mark_price=float(r.mark_price) if r.mark_price is not None else None,
        )
        for r in rows
    ]

    ois = [l.oi_usd for l in latest if l.oi_usd is not None]
    frs = [l.funding_rate for l in latest if l.funding_rate is not None]
    return DerivativesSummary(
        latest=latest,
        total_oi_usd=sum(ois) if ois else None,
        avg_funding_rate=sum(frs) / len(frs) if frs else None,
    )


@router.get("/series", response_model=DerivativesSeriesResponse)
def series(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(72, ge=1, le=24 * 30),
    exchange: str | None = Query(None),
    limit: int = Query(5000, ge=1, le=20000),
) -> DerivativesSeriesResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = select(DerivativesSnapshot).where(DerivativesSnapshot.ts >= cutoff)
    if exchange:
        stmt = stmt.where(DerivativesSnapshot.exchange == exchange.lower())
    stmt = stmt.order_by(desc(DerivativesSnapshot.ts)).limit(limit)

    rows = list(reversed(session.execute(stmt).scalars().all()))
    points = [
        DerivativesPoint(
            ts=r.ts,
            exchange=r.exchange,
            symbol=r.symbol,
            oi_usd=float(r.oi_usd) if r.oi_usd is not None else None,
            funding_rate=float(r.funding_rate) if r.funding_rate is not None else None,
            mark_price=float(r.mark_price) if r.mark_price is not None else None,
        )
        for r in rows
    ]
    return DerivativesSeriesResponse(points=points)


@router.get("/liquidations", response_model=LiquidationResponse)
def liquidations(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 7,
                       description="look-back window in hours; default 24"),
) -> LiquidationResponse:
    """Hourly bucketed perp-futures liquidations + 24h-style summary headline.

    For v1 we serve Binance ETHUSDT only; the schema carries `venue` so
    additional venues slot in without API change. Buckets are computed
    in SQL with date_trunc; empty hours are simply absent (frontend
    fills gaps for the chart axis).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Listener health: the newest event in the entire table, regardless of
    # window. Used to flag a dead Binance forceOrder stream so the panel
    # can show "stream unavailable" rather than "quiet market window".
    # 6h covers the longest plausible quiet stretch on ETHUSDT perp.
    LIQUIDATION_STALE_HOURS = 6
    last_event_ts: datetime | None = session.execute(
        select(func.max(PerpLiquidation.ts))
    ).scalar_one()
    listener_stale = (
        last_event_ts is None
        or (datetime.now(UTC) - last_event_ts)
        > timedelta(hours=LIQUIDATION_STALE_HOURS)
    )

    # Headline tile: 24h totals + largest single liquidation. Window matches
    # `hours` rather than fixed 24h so the tile stays consistent with the chart.
    summary_row = session.execute(
        select(
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "long", PerpLiquidation.notional_usd),
                          else_=0)), 0).label("long_usd"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "short", PerpLiquidation.notional_usd),
                          else_=0)), 0).label("short_usd"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "long", 1),
                          else_=0)), 0).label("long_count"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "short", 1),
                          else_=0)), 0).label("short_count"),
            func.coalesce(func.max(PerpLiquidation.notional_usd), 0).label("largest_usd"),
        ).where(PerpLiquidation.ts >= cutoff)
    ).one()

    # Hourly buckets — pivot long/short into the same row via case-when.
    bucket_ts = func.date_trunc("hour", PerpLiquidation.ts).label("ts_bucket")
    bucket_rows = session.execute(
        select(
            bucket_ts,
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "long", PerpLiquidation.notional_usd),
                          else_=0)), 0).label("long_usd"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "short", PerpLiquidation.notional_usd),
                          else_=0)), 0).label("short_usd"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "long", 1),
                          else_=0)), 0).label("long_count"),
            func.coalesce(func.sum(
                case((PerpLiquidation.side == "short", 1),
                          else_=0)), 0).label("short_count"),
        )
        .where(PerpLiquidation.ts >= cutoff)
        .group_by(bucket_ts)
        .order_by(bucket_ts.asc())
    ).all()

    return LiquidationResponse(
        summary=LiquidationSummary(
            long_usd=float(summary_row.long_usd),
            short_usd=float(summary_row.short_usd),
            long_count=int(summary_row.long_count),
            short_count=int(summary_row.short_count),
            largest_usd=float(summary_row.largest_usd),
            venue="bybit",
            last_event_ts=last_event_ts,
            listener_stale=listener_stale,
        ),
        buckets=[
            LiquidationBucket(
                ts_bucket=r.ts_bucket,
                long_usd=float(r.long_usd),
                short_usd=float(r.short_usd),
                long_count=int(r.long_count),
                short_count=int(r.short_count),
            )
            for r in bucket_rows
        ],
    )
