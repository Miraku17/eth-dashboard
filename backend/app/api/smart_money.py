"""GET /api/smart-money/direction — net WETH bought vs sold by smart-money
wallets over the last 24h, with a 7-day daily sparkline.

A "smart-money wallet" is any address with a `wallet_score.score >=
SMART_FLOOR_USD` (default $100k 30d realized PnL — same threshold the
WhaleTransfersPanel and `/api/whales/transfers?smart_only=true` use, so
the three surfaces stay aligned). Net positive = the cohort is
accumulating ETH on-chain in aggregate.

Read-only; aggregates `dex_swap` × `wallet_score` in two queries and
caches the result for 5 minutes — the swap stream is high-volume and
this endpoint is meant to be a passive Overview tile, not a real-time
read.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import SmartMoneyDirectionPoint, SmartMoneyDirectionResponse
from app.api.whales import SMART_FLOOR_USD
from app.core.cache import cached_json_get, cached_json_set
from app.core.db import get_session
from app.core.models import DexSwap, WalletScore

router = APIRouter(prefix="/smart-money", tags=["smart-money"])

CACHE_KEY = "smart_money_direction:current"
CACHE_TTL_S = 300


@router.get("/direction", response_model=SmartMoneyDirectionResponse)
def smart_money_direction(
    session: Annotated[Session, Depends(get_session)],
) -> SmartMoneyDirectionResponse:
    cached = cached_json_get(CACHE_KEY)
    if cached is not None:
        return SmartMoneyDirectionResponse.model_validate(cached)

    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    # Smart-money wallet set — same SQL shape as `/api/whales/transfers
    # ?smart_only=true` so behaviour stays identical across the three
    # surfaces (panel filter / alert rule / this tile).
    smart_wallets = select(WalletScore.wallet).where(WalletScore.score >= SMART_FLOOR_USD)

    # 24h headline: one query, group by side. COUNT(DISTINCT wallet) gives
    # the active-wallet badge underneath.
    headline_rows = session.execute(
        select(
            DexSwap.side,
            func.coalesce(func.sum(DexSwap.usd_value), 0),
            func.count(func.distinct(DexSwap.wallet)),
        )
        .where(DexSwap.ts >= cutoff_24h, DexSwap.wallet.in_(smart_wallets))
        .group_by(DexSwap.side)
    ).all()

    bought = sold = 0.0
    active_wallets = 0
    for side, total, distinct_wallets in headline_rows:
        if side == "buy":
            bought = float(total or 0)
        elif side == "sell":
            sold = float(total or 0)
        # Two side-rows can return overlapping wallet sets; take the max so
        # the count is bounded by the larger leg rather than double-counted.
        active_wallets = max(active_wallets, int(distinct_wallets or 0))

    # 7-day daily series. Truncate to UTC midnight so the buckets line up
    # with calendar days; the frontend formats dates without timezone.
    daily_rows = session.execute(
        select(
            func.date_trunc("day", DexSwap.ts).label("day"),
            DexSwap.side,
            func.coalesce(func.sum(DexSwap.usd_value), 0),
        )
        .where(DexSwap.ts >= cutoff_7d, DexSwap.wallet.in_(smart_wallets))
        .group_by("day", DexSwap.side)
        .order_by("day")
    ).all()

    by_day: dict[str, dict[str, float]] = {}
    for day, side, total in daily_rows:
        # date_trunc returns a timestamp; format to YYYY-MM-DD for the wire.
        day_key = day.date().isoformat() if hasattr(day, "date") else str(day)
        bucket = by_day.setdefault(day_key, {"bought_usd": 0.0, "sold_usd": 0.0})
        if side == "buy":
            bucket["bought_usd"] = float(total or 0)
        elif side == "sell":
            bucket["sold_usd"] = float(total or 0)

    # Backfill missing days with zeros so the sparkline has a stable
    # 7-bar shape rather than collapsing on quiet days.
    sparkline: list[SmartMoneyDirectionPoint] = []
    for offset in range(6, -1, -1):
        d = (now - timedelta(days=offset)).date().isoformat()
        leg = by_day.get(d, {"bought_usd": 0.0, "sold_usd": 0.0})
        sparkline.append(
            SmartMoneyDirectionPoint(
                date=d,
                bought_usd=leg["bought_usd"],
                sold_usd=leg["sold_usd"],
                net_usd=leg["bought_usd"] - leg["sold_usd"],
            )
        )

    response = SmartMoneyDirectionResponse(
        bought_usd_24h=bought,
        sold_usd_24h=sold,
        net_usd_24h=bought - sold,
        smart_wallets_active_24h=active_wallets,
        min_score=SMART_FLOOR_USD,
        sparkline_7d=sparkline,
        computed_at=now,
    )
    cached_json_set(CACHE_KEY, response.model_dump(mode="json"), CACHE_TTL_S)
    return response
