from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DerivativesLatest,
    DerivativesPoint,
    DerivativesSeriesResponse,
    DerivativesSummary,
)
from app.core.db import get_session
from app.core.models import DerivativesSnapshot

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
