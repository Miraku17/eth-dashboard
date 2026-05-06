"""On-chain perp endpoints (v5 — GMX V2 on Arbitrum).

Three reads against `onchain_perp_event`:
- /api/perps/events     — chronological feed, filterable by kind/min size
- /api/perps/summary    — headline tiles (24h count + USD totals + skew)
- /api/perps/largest-positions — currently-open positions, ranked by size

Open positions are reconstructed on read with a windowed aggregation
over the last 30 days — the latest event per (account, market, side)
wins, kept only if its `size_after_usd > 0`. v1 doesn't materialise an
"open positions" table; events ARE the source of truth and the index
on (account, ts DESC) keeps the reconstruction cheap.
"""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    PerpEvent,
    PerpEventsResponse,
    PerpPosition,
    PerpPositionsResponse,
    PerpSummary,
)
from app.core.db import get_session
from app.core.models import OnchainPerpEvent

router = APIRouter(prefix="/perps", tags=["perps"])

_OPEN_POSITIONS_WINDOW_DAYS = 30


@router.get("/events", response_model=PerpEventsResponse)
def events(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 30),
    kind: str | None = Query(
        None,
        description="filter by event_kind (open|increase|close|decrease|liquidation)",
    ),
    min_size_usd: float = Query(0.0, ge=0.0),
    limit: int = Query(500, ge=1, le=5000),
) -> PerpEventsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = select(OnchainPerpEvent).where(OnchainPerpEvent.ts >= cutoff)
    if kind:
        stmt = stmt.where(OnchainPerpEvent.event_kind == kind)
    if min_size_usd > 0:
        stmt = stmt.where(OnchainPerpEvent.size_usd >= min_size_usd)
    stmt = stmt.order_by(desc(OnchainPerpEvent.ts)).limit(limit)
    rows = session.execute(stmt).scalars().all()
    return PerpEventsResponse(
        events=[
            PerpEvent(
                ts=r.ts,
                venue=r.venue,
                account=r.account,
                market=r.market,
                event_kind=r.event_kind,
                side=r.side,
                size_usd=float(r.size_usd),
                size_after_usd=float(r.size_after_usd),
                collateral_usd=float(r.collateral_usd),
                leverage=float(r.leverage),
                price_usd=float(r.price_usd),
                pnl_usd=float(r.pnl_usd) if r.pnl_usd is not None else None,
                tx_hash=r.tx_hash,
            )
            for r in rows
        ]
    )


@router.get("/summary", response_model=PerpSummary)
def summary(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(24, ge=1, le=24 * 7),
) -> PerpSummary:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Headline counts within the window.
    counts_row = session.execute(
        select(
            func.coalesce(func.sum(
                case((OnchainPerpEvent.event_kind == "open", 1), else_=0)
            ), 0).label("opens"),
            func.coalesce(func.sum(
                case((OnchainPerpEvent.event_kind == "close", 1), else_=0)
            ), 0).label("closes"),
            func.coalesce(func.sum(
                case((OnchainPerpEvent.event_kind == "liquidation", 1), else_=0)
            ), 0).label("liqs"),
            func.coalesce(func.sum(
                case(
                    (
                        (OnchainPerpEvent.event_kind == "liquidation")
                        & (OnchainPerpEvent.side == "long"),
                        OnchainPerpEvent.size_usd,
                    ),
                    else_=0,
                )
            ), 0).label("long_liq_usd"),
            func.coalesce(func.sum(
                case(
                    (
                        (OnchainPerpEvent.event_kind == "liquidation")
                        & (OnchainPerpEvent.side == "short"),
                        OnchainPerpEvent.size_usd,
                    ),
                    else_=0,
                )
            ), 0).label("short_liq_usd"),
        ).where(OnchainPerpEvent.ts >= cutoff)
    ).one()

    # Biggest single liquidation in the window — separate query so we can
    # carry the originating account + market.
    biggest_row = session.execute(
        select(OnchainPerpEvent)
        .where(
            OnchainPerpEvent.ts >= cutoff,
            OnchainPerpEvent.event_kind == "liquidation",
        )
        .order_by(desc(OnchainPerpEvent.size_usd))
        .limit(1)
    ).scalar_one_or_none()

    # Currently-open size aggregate (reconstructed). Window-fn picks the
    # latest event per (account, market, side); we sum surviving size_after.
    open_long_usd, open_short_usd = _aggregate_open_sizes(session)

    skew_denom = open_long_usd + open_short_usd
    skew = ((open_long_usd - open_short_usd) / skew_denom) if skew_denom > 0 else 0.0

    return PerpSummary(
        hours=hours,
        opens_count=int(counts_row.opens),
        closes_count=int(counts_row.closes),
        liquidations_count=int(counts_row.liqs),
        total_long_liq_usd=float(counts_row.long_liq_usd),
        total_short_liq_usd=float(counts_row.short_liq_usd),
        biggest_liq_usd=float(biggest_row.size_usd) if biggest_row else 0.0,
        biggest_liq_account=biggest_row.account if biggest_row else None,
        biggest_liq_market=biggest_row.market if biggest_row else None,
        biggest_liq_ts=biggest_row.ts if biggest_row else None,
        open_long_size_usd=open_long_usd,
        open_short_size_usd=open_short_usd,
        long_short_skew=skew,
    )


@router.get("/largest-positions", response_model=PerpPositionsResponse)
def largest_positions(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
) -> PerpPositionsResponse:
    """Top-N open positions by size_after_usd. Reconstructs from events."""
    positions = _open_positions(session)
    positions.sort(key=lambda p: p.size_usd, reverse=True)
    return PerpPositionsResponse(positions=positions[:limit])


# --- internal helpers ------------------------------------------------------


def _aggregate_open_sizes(session: Session) -> tuple[float, float]:
    """Returns (open_long_usd, open_short_usd) summed across all
    currently-open positions. Cheap: scans the same set _open_positions
    walks but doesn't materialise the per-row Python objects."""
    cutoff = datetime.now(UTC) - timedelta(days=_OPEN_POSITIONS_WINDOW_DAYS)
    # Latest ts per (account, market, side) within the window.
    latest = (
        select(
            OnchainPerpEvent.account,
            OnchainPerpEvent.market,
            OnchainPerpEvent.side,
            func.max(OnchainPerpEvent.ts).label("max_ts"),
        )
        .where(OnchainPerpEvent.ts >= cutoff)
        .group_by(
            OnchainPerpEvent.account,
            OnchainPerpEvent.market,
            OnchainPerpEvent.side,
        )
        .subquery()
    )
    rows = session.execute(
        select(OnchainPerpEvent.side, func.sum(OnchainPerpEvent.size_after_usd).label("size"))
        .join(
            latest,
            (OnchainPerpEvent.account == latest.c.account)
            & (OnchainPerpEvent.market == latest.c.market)
            & (OnchainPerpEvent.side == latest.c.side)
            & (OnchainPerpEvent.ts == latest.c.max_ts),
        )
        .where(OnchainPerpEvent.size_after_usd > 0)
        .group_by(OnchainPerpEvent.side)
    ).all()
    long_usd = 0.0
    short_usd = 0.0
    for side, size in rows:
        if side == "long":
            long_usd = float(size or 0)
        elif side == "short":
            short_usd = float(size or 0)
    return long_usd, short_usd


def _open_positions(session: Session) -> list[PerpPosition]:
    """Materialise currently-open positions. Used by /largest-positions.

    For each (account, market, side) with at least one event in the
    30-day window, the LATEST event tells us the current state — if its
    size_after_usd > 0, the position is open. We also need the FIRST
    event in the same group (`opened_at`).
    """
    cutoff = datetime.now(UTC) - timedelta(days=_OPEN_POSITIONS_WINDOW_DAYS)
    latest = (
        select(
            OnchainPerpEvent.account,
            OnchainPerpEvent.market,
            OnchainPerpEvent.side,
            func.max(OnchainPerpEvent.ts).label("max_ts"),
            func.min(OnchainPerpEvent.ts).label("opened_ts"),
        )
        .where(OnchainPerpEvent.ts >= cutoff)
        .group_by(
            OnchainPerpEvent.account,
            OnchainPerpEvent.market,
            OnchainPerpEvent.side,
        )
        .subquery()
    )
    rows = session.execute(
        select(
            OnchainPerpEvent.account,
            OnchainPerpEvent.market,
            OnchainPerpEvent.side,
            OnchainPerpEvent.size_after_usd,
            OnchainPerpEvent.collateral_usd,
            OnchainPerpEvent.leverage,
            OnchainPerpEvent.ts,
            latest.c.opened_ts,
        )
        .join(
            latest,
            (OnchainPerpEvent.account == latest.c.account)
            & (OnchainPerpEvent.market == latest.c.market)
            & (OnchainPerpEvent.side == latest.c.side)
            & (OnchainPerpEvent.ts == latest.c.max_ts),
        )
        .where(OnchainPerpEvent.size_after_usd > 0)
    ).all()

    return [
        PerpPosition(
            account=r.account,
            market=r.market,
            side=r.side,
            size_usd=float(r.size_after_usd),
            collateral_usd=float(r.collateral_usd),
            leverage=float(r.leverage),
            opened_at=r.opened_ts,
            last_event_at=r.ts,
        )
        for r in rows
    ]
