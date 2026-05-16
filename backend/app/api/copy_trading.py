"""API surface for the /copy-trading page.

Endpoints:
- GET    /api/copy-trading/config         → leaderboard threshold constants
- GET    /api/copy-trading/leaderboard    → ranked perp wallets meeting filter
- GET    /api/copy-trading/wallets/{addr} → stat header + last 20 events + histogram
- GET    /api/copy-trading/watchlist      → current watchlist
- POST   /api/copy-trading/watchlist      → add wallet
- PATCH  /api/copy-trading/watchlist/{addr}
- DELETE /api/copy-trading/watchlist/{addr}
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.cache import _client as redis_client
from app.core.db import get_session
from app.core.models import OnchainPerpEvent, PerpWalletScore, PerpWatchlist
from app.realtime.perp_watchlist_cache import INVALIDATE_CHANNEL
from app.services.perp_scoring import (
    DEFAULT_WATCH_NOTIONAL_USD,
    LEADERBOARD_LOOKBACK_DAYS,
    LEADERBOARD_MIN_PNL_USD,
    LEADERBOARD_MIN_TRADES,
    LEADERBOARD_MIN_WIN_RATE,
)

router = APIRouter(prefix="/copy-trading", tags=["copy-trading"])


# ---------- schemas ----------


class ConfigOut(BaseModel):
    lookback_days: int
    min_trades: int
    min_win_rate: float
    min_pnl_usd: float
    default_watch_notional_usd: float


class ScoreRow(BaseModel):
    wallet: str
    trades_90d: int
    win_rate_90d: float
    win_rate_long_90d: float | None
    win_rate_short_90d: float | None
    realized_pnl_90d: float
    avg_hold_secs: int
    avg_position_usd: float
    avg_leverage: float
    on_watchlist: bool


class TripRow(BaseModel):
    ts: datetime
    market: str
    side: str
    event_kind: str
    size_usd: float
    pnl_usd: float | None


class HistogramBuckets(BaseModel):
    lt_5m: int
    m5_15: int
    m15_60: int
    h1_24: int
    gt_1d: int


class WalletDetailOut(BaseModel):
    score: ScoreRow | None
    last_trades: list[TripRow]
    hold_time_histogram: HistogramBuckets


class WatchOut(BaseModel):
    wallet: str
    label: str | None
    min_notional_usd: float
    created_at: datetime


class WatchCreate(BaseModel):
    wallet: str = Field(..., pattern=r"^0x[0-9a-fA-F]{40}$")
    label: str | None = None
    min_notional_usd: float | None = None


class WatchUpdate(BaseModel):
    label: str | None = None
    min_notional_usd: float | None = None


# ---------- helpers ----------


def _score_to_row(s: PerpWalletScore, on_watchlist: bool) -> ScoreRow:
    return ScoreRow(
        wallet=s.wallet,
        trades_90d=s.trades_90d,
        win_rate_90d=float(s.win_rate_90d),
        win_rate_long_90d=None if s.win_rate_long_90d is None else float(s.win_rate_long_90d),
        win_rate_short_90d=None if s.win_rate_short_90d is None else float(s.win_rate_short_90d),
        realized_pnl_90d=float(s.realized_pnl_90d),
        avg_hold_secs=s.avg_hold_secs,
        avg_position_usd=float(s.avg_position_usd),
        avg_leverage=float(s.avg_leverage),
        on_watchlist=on_watchlist,
    )


def _publish_invalidate() -> None:
    try:
        redis_client().publish(INVALIDATE_CHANNEL, "")
    except Exception:
        # Pub/sub failure is non-fatal — the cache TTL will pick up changes.
        pass


def _hold_time_histogram(session: Session, addr: str, cutoff: datetime) -> HistogramBuckets:
    """Replay the wallet's events through a lightweight FIFO to get hold times."""
    rows = session.execute(
        select(OnchainPerpEvent)
        .where(OnchainPerpEvent.account == addr)
        .where(OnchainPerpEvent.ts >= cutoff)
        .order_by(OnchainPerpEvent.ts)
    ).scalars().all()
    inventory: dict[tuple[str, str], list[list]] = defaultdict(list)
    buckets = {"lt_5m": 0, "m5_15": 0, "m15_60": 0, "h1_24": 0, "gt_1d": 0}
    for r in rows:
        key = (r.market, r.side)
        if r.event_kind in {"open", "increase"}:
            inventory[key].append([r.size_usd, r.ts])
            continue
        if r.event_kind not in {"close", "decrease", "liquidation"}:
            continue
        remaining = r.size_usd
        while remaining > 0 and inventory[key]:
            lot = inventory[key][0]
            take = min(remaining, lot[0])
            secs = int((r.ts - lot[1]).total_seconds())
            if secs < 300:
                buckets["lt_5m"] += 1
            elif secs < 900:
                buckets["m5_15"] += 1
            elif secs < 3600:
                buckets["m15_60"] += 1
            elif secs < 86400:
                buckets["h1_24"] += 1
            else:
                buckets["gt_1d"] += 1
            lot[0] -= take
            remaining -= take
            if lot[0] <= 0:
                inventory[key].pop(0)
    return HistogramBuckets(**buckets)


# ---------- endpoints ----------


@router.get("/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    return ConfigOut(
        lookback_days=LEADERBOARD_LOOKBACK_DAYS,
        min_trades=LEADERBOARD_MIN_TRADES,
        min_win_rate=float(LEADERBOARD_MIN_WIN_RATE),
        min_pnl_usd=float(LEADERBOARD_MIN_PNL_USD),
        default_watch_notional_usd=float(DEFAULT_WATCH_NOTIONAL_USD),
    )


@router.get("/leaderboard", response_model=list[ScoreRow])
def get_leaderboard(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 100,
    min_trades: int = LEADERBOARD_MIN_TRADES,
    min_win: float = float(LEADERBOARD_MIN_WIN_RATE),
    min_pnl: float = float(LEADERBOARD_MIN_PNL_USD),
) -> list[ScoreRow]:
    rows = session.execute(
        select(PerpWalletScore)
        .where(PerpWalletScore.trades_90d >= min_trades)
        .where(PerpWalletScore.win_rate_90d >= Decimal(str(min_win)))
        .where(PerpWalletScore.realized_pnl_90d >= Decimal(str(min_pnl)))
        .order_by(desc(PerpWalletScore.realized_pnl_90d))
        .limit(limit)
    ).scalars().all()
    watched = {w for (w,) in session.execute(select(PerpWatchlist.wallet)).all()}
    return [_score_to_row(r, r.wallet in watched) for r in rows]


@router.get("/wallets/{address}", response_model=WalletDetailOut)
def get_wallet_detail(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> WalletDetailOut:
    addr = address.lower()
    score = session.execute(
        select(PerpWalletScore).where(PerpWalletScore.wallet == addr)
    ).scalar_one_or_none()
    on_wl = session.execute(
        select(PerpWatchlist.wallet).where(PerpWatchlist.wallet == addr)
    ).scalar_one_or_none() is not None
    score_row = _score_to_row(score, on_wl) if score else None

    cutoff = datetime.now(timezone.utc) - timedelta(days=LEADERBOARD_LOOKBACK_DAYS)
    events = session.execute(
        select(OnchainPerpEvent)
        .where(OnchainPerpEvent.account == addr)
        .where(OnchainPerpEvent.ts >= cutoff)
        .order_by(desc(OnchainPerpEvent.ts))
        .limit(20)
    ).scalars().all()
    last_trades = [
        TripRow(
            ts=e.ts, market=e.market, side=e.side, event_kind=e.event_kind,
            size_usd=float(e.size_usd),
            pnl_usd=None if e.pnl_usd is None else float(e.pnl_usd),
        )
        for e in events
    ]
    hist = _hold_time_histogram(session, addr, cutoff)
    return WalletDetailOut(score=score_row, last_trades=last_trades, hold_time_histogram=hist)


@router.get("/watchlist", response_model=list[WatchOut])
def get_watchlist(session: Annotated[Session, Depends(get_session)]) -> list[WatchOut]:
    rows = session.execute(
        select(PerpWatchlist).order_by(PerpWatchlist.created_at)
    ).scalars().all()
    return [
        WatchOut(
            wallet=r.wallet, label=r.label,
            min_notional_usd=float(r.min_notional_usd), created_at=r.created_at,
        ) for r in rows
    ]


@router.post("/watchlist", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
def add_watch(
    body: WatchCreate,
    session: Annotated[Session, Depends(get_session)],
) -> WatchOut:
    addr = body.wallet.lower()
    existing = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == addr)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="already on watchlist")
    row = PerpWatchlist(
        wallet=addr, label=body.label,
        min_notional_usd=(
            Decimal(str(body.min_notional_usd))
            if body.min_notional_usd is not None
            else DEFAULT_WATCH_NOTIONAL_USD
        ),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    _publish_invalidate()
    return WatchOut(
        wallet=row.wallet, label=row.label,
        min_notional_usd=float(row.min_notional_usd), created_at=row.created_at,
    )


@router.patch("/watchlist/{address}", response_model=WatchOut)
def update_watch(
    address: str,
    body: WatchUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> WatchOut:
    row = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == address.lower())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not on watchlist")
    if body.label is not None:
        row.label = body.label
    if body.min_notional_usd is not None:
        row.min_notional_usd = Decimal(str(body.min_notional_usd))
    session.commit()
    session.refresh(row)
    _publish_invalidate()
    return WatchOut(
        wallet=row.wallet, label=row.label,
        min_notional_usd=float(row.min_notional_usd), created_at=row.created_at,
    )


@router.delete("/watchlist/{address}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    row = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == address.lower())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not on watchlist")
    session.delete(row)
    session.commit()
    _publish_invalidate()
