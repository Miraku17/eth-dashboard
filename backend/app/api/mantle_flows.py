"""GET /api/flows/mantle-order-flow — Mantle DEX MNT buy/sell pressure.

Reads `mantle_order_flow` rows over the requested window, multiplies the
raw mnt_amount by a Redis-cached MNT/USD snapshot to produce usd_value,
and aggregates a summary tile. The writer (mantle_realtime) stores raw
MNT only, so a CoinGecko outage degrades gracefully here (null usd_value,
price_unavailable=True) without dropping any swap data."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    MantleOrderFlowResponse,
    MantleOrderFlowRow,
    MantleOrderFlowSummary,
)
from app.core.db import get_session
from app.core.models import MantleOrderFlow
from app.services.mnt_price import get_mnt_usd

router = APIRouter(prefix="/flows", tags=["mantle-flows"])


@router.get("/mantle-order-flow", response_model=MantleOrderFlowResponse)
def mantle_order_flow(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(default=24, ge=1, le=168),
) -> MantleOrderFlowResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(session.scalars(
        select(MantleOrderFlow)
        .where(MantleOrderFlow.ts_bucket >= cutoff)
        .order_by(MantleOrderFlow.ts_bucket, MantleOrderFlow.dex, MantleOrderFlow.side)
    ))

    mnt_usd = get_mnt_usd()
    price_unavailable = mnt_usd is None

    out_rows: list[MantleOrderFlowRow] = []
    buy_usd_total = 0.0
    sell_usd_total = 0.0
    active_dexes: set[str] = set()

    for r in rows:
        active_dexes.add(r.dex)
        usd_value = float(r.mnt_amount) * mnt_usd if mnt_usd is not None else None
        if usd_value is not None:
            if r.side == "buy":
                buy_usd_total += usd_value
            elif r.side == "sell":
                sell_usd_total += usd_value
        out_rows.append(MantleOrderFlowRow(
            ts_bucket=r.ts_bucket,
            dex=r.dex,
            side=r.side,
            count=r.count,
            mnt_amount=float(r.mnt_amount),
            usd_value=usd_value,
        ))

    summary = MantleOrderFlowSummary(
        buy_usd=None  if price_unavailable else buy_usd_total,
        sell_usd=None if price_unavailable else sell_usd_total,
        net_usd=None  if price_unavailable else (buy_usd_total - sell_usd_total),
        active_dexes=sorted(active_dexes),
        mnt_usd=mnt_usd,
        price_unavailable=price_unavailable,
    )
    return MantleOrderFlowResponse(rows=out_rows, summary=summary)
