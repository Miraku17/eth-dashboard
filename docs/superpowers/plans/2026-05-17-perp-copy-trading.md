# Perp Copy-Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v5-perp-copy-trading subsystem — daily FIFO scoring of GMX V2 perp wallets, operator-curated watchlist, real-time Telegram alerts on open/close from watched wallets, and a `/copy-trading` page with leaderboard, watchlist, and per-wallet detail.

**Architecture:** Three new components on top of the existing `onchain_perp_event` table: (1) a daily `score_perp_wallets` cron that FIFO-matches round-trips per `(wallet, market, side)` and upserts to `perp_wallet_score`; (2) a `perp_watchlist` table with CRUD endpoints, mirrored into a Redis-cached set that the `arbitrum_listener` checks after every decoded event; (3) a new `/api/copy-trading/*` router and a new `/copy-trading` page. Alerts flow through the existing `alerts.delivery` module (Telegram only in v1).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, arq, asyncpg/psycopg, Redis (cache + pub/sub), React 18 + Vite + TanStack Query, shadcn/ui, Recharts.

**Spec:** `docs/superpowers/specs/2026-05-17-perp-copy-trading-design.md`.

---

## File Structure

**Backend — new files:**
- `backend/alembic/versions/0028_perp_copy_trading.py` — schema migration
- `backend/app/services/perp_scoring.py` — FIFO kernel + named thresholds + leaderboard query helper
- `backend/app/services/perp_watch_dispatch.py` — payload builder + dispatcher for watchlist alerts
- `backend/app/realtime/perp_watchlist_cache.py` — Redis-backed set + pub/sub invalidation listener
- `backend/app/workers/perp_scoring_jobs.py` — daily cron entry
- `backend/app/api/copy_trading.py` — config / leaderboard / wallet detail / watchlist CRUD
- `backend/tests/test_perp_scoring.py` — kernel unit tests
- `backend/tests/test_copy_trading_api.py` — API integration tests
- `backend/tests/test_perp_watch_dispatch.py` — dispatcher unit tests

**Backend — modified files:**
- `backend/app/core/models.py` — add `PerpWalletScore` + `PerpWatchlist` ORM classes
- `backend/app/realtime/arbitrum_listener.py` — call dispatcher after persist
- `backend/app/workers/arq_settings.py` — register `score_perp_wallets` cron at 04:23 UTC
- `backend/app/services/alerts/delivery.py` — add `perp_watch` formatter branch
- `backend/app/main.py` — mount `copy_trading_router`

**Frontend — new files:**
- `frontend/src/routes/CopyTradingPage.tsx`
- `frontend/src/components/copy-trading/Leaderboard.tsx`
- `frontend/src/components/copy-trading/Watchlist.tsx`
- `frontend/src/components/copy-trading/WalletDetail.tsx`
- `frontend/src/components/copy-trading/HoldTimeHistogram.tsx`
- `frontend/src/components/copy-trading/PerpPerformanceTile.tsx`
- `frontend/src/api/copyTrading.ts`

**Frontend — modified files:**
- `frontend/src/App.tsx` — add route + nav entry
- `frontend/src/components/Topbar.tsx` (or wherever nav lives) — add "Copy Trading" link
- `frontend/src/components/WalletDrawer.tsx` — mount `PerpPerformanceTile` when score row exists

**Docs:**
- `CLAUDE.md` — append v5-perp-copy-trading entry to the v5 status block

---

## Task 1: Schema migration

**Files:**
- Create: `backend/alembic/versions/0028_perp_copy_trading.py`

- [ ] **Step 1: Write the migration**

```python
"""perp copy-trading: perp_wallet_score + perp_watchlist

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perp_wallet_score",
        sa.Column("wallet", sa.String(42), primary_key=True),
        sa.Column("trades_90d", sa.Integer, nullable=False),
        sa.Column("win_rate_90d", sa.Numeric(5, 4), nullable=False),
        sa.Column("win_rate_long_90d", sa.Numeric(5, 4), nullable=True),
        sa.Column("win_rate_short_90d", sa.Numeric(5, 4), nullable=True),
        sa.Column("realized_pnl_90d", sa.Numeric(20, 2), nullable=False),
        sa.Column("avg_hold_secs", sa.Integer, nullable=False),
        sa.Column("avg_position_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("avg_leverage", sa.Numeric(6, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        """
        CREATE INDEX perp_wallet_score_leaderboard_idx
          ON perp_wallet_score (realized_pnl_90d DESC)
          WHERE trades_90d >= 30
            AND win_rate_90d >= 0.6
            AND realized_pnl_90d >= 10000
        """
    )
    op.create_table(
        "perp_watchlist",
        sa.Column("wallet", sa.String(42), primary_key=True),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column(
            "min_notional_usd",
            sa.Numeric(20, 2),
            server_default="25000",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("perp_watchlist")
    op.execute("DROP INDEX IF EXISTS perp_wallet_score_leaderboard_idx")
    op.drop_table("perp_wallet_score")
```

- [ ] **Step 2: Run the migration**

Run: `make migrate`
Expected: alembic reports `0027 -> 0028, perp copy-trading` and exits 0.

- [ ] **Step 3: Verify schema**

Run: `docker compose exec api python -c "from app.core.db import get_sessionmaker; s = get_sessionmaker()(); print(s.execute(__import__('sqlalchemy').text('SELECT to_regclass(\\'perp_wallet_score\\'), to_regclass(\\'perp_watchlist\\')')).first())"`
Expected: `('perp_wallet_score', 'perp_watchlist')` (both non-NULL).

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0028_perp_copy_trading.py
git commit -m "feat(perp-copy): schema for perp_wallet_score + perp_watchlist"
```

---

## Task 2: ORM models

**Files:**
- Modify: `backend/app/core/models.py` (append two new classes)

- [ ] **Step 1: Add models**

Append to `backend/app/core/models.py` (anywhere after `OnchainPerpEvent`):

```python
class PerpWalletScore(Base):
    """Latest 90d scoring snapshot per wallet for GMX V2 perp activity."""
    __tablename__ = "perp_wallet_score"
    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    trades_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate_90d: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    win_rate_long_90d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    win_rate_short_90d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    realized_pnl_90d: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    avg_hold_secs: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_position_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    avg_leverage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class PerpWatchlist(Base):
    """Operator-curated set of wallets that fire Telegram alerts on perp open/close."""
    __tablename__ = "perp_watchlist"
    wallet: Mapped[str] = mapped_column(String(42), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    min_notional_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("25000")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
```

If `text` isn't imported in the file yet, add `from sqlalchemy import text` at the top alongside existing sqlalchemy imports.

- [ ] **Step 2: Smoke-test import**

Run: `docker compose exec api python -c "from app.core.models import PerpWalletScore, PerpWatchlist; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/models.py
git commit -m "feat(perp-copy): ORM models for perp_wallet_score + perp_watchlist"
```

---

## Task 3: FIFO scoring kernel (TDD)

**Files:**
- Create: `backend/app/services/perp_scoring.py`
- Test: `backend/tests/test_perp_scoring.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_perp_scoring.py`:

```python
"""Unit tests for the perp FIFO scoring kernel."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from app.services.perp_scoring import (
    PerpEvent,
    WalletStats,
    score_wallet,
)


def _ts(minutes: int) -> datetime:
    return datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def _ev(kind, side, size, price, leverage, mins, pnl=None):
    return PerpEvent(
        ts=_ts(mins),
        market="ETH-USD",
        side=side,
        event_kind=kind,
        size_usd=Decimal(size),
        price_usd=Decimal(price),
        leverage=Decimal(leverage),
        pnl_usd=None if pnl is None else Decimal(pnl),
    )


def test_profitable_long_round_trip():
    events = [
        _ev("open", "long", "50000", "3000", "10", 0),
        _ev("close", "long", "50000", "3100", "10", 15, pnl="1666"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.win_rate_90d == Decimal("1.0000")
    assert stats.win_rate_long_90d == Decimal("1.0000")
    assert stats.win_rate_short_90d is None
    assert stats.realized_pnl_90d == Decimal("1666.00")
    assert stats.avg_hold_secs == 15 * 60


def test_losing_short_round_trip():
    events = [
        _ev("open", "short", "30000", "3000", "5", 0),
        _ev("close", "short", "30000", "3100", "5", 8, pnl="-1000"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.win_rate_90d == Decimal("0.0000")
    assert stats.win_rate_short_90d == Decimal("0.0000")
    assert stats.win_rate_long_90d is None
    assert stats.realized_pnl_90d == Decimal("-1000.00")


def test_partial_close_realizes_half():
    events = [
        _ev("open", "long", "100000", "3000", "10", 0),
        _ev("decrease", "long", "50000", "3100", "10", 10, pnl="833"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.realized_pnl_90d == Decimal("833.00")
    assert stats.avg_hold_secs == 10 * 60


def test_multiple_opens_consumed_fifo_by_one_close():
    events = [
        _ev("open",     "long", "20000", "3000", "10", 0),
        _ev("increase", "long", "30000", "3050", "10", 5),
        _ev("close",    "long", "50000", "3100", "10", 20, pnl="1500"),
    ]
    stats = score_wallet(events)
    # Two round-trips because FIFO matches lot-by-lot.
    assert stats.trades_90d == 2
    assert stats.realized_pnl_90d == Decimal("1500.00")
    # Hold times: lot1 = 20m, lot2 = 15m → mean = 17.5m
    assert stats.avg_hold_secs == int((20 * 60 + 15 * 60) / 2)


def test_orphan_close_skipped():
    events = [_ev("close", "long", "10000", "3000", "5", 0, pnl="100")]
    stats = score_wallet(events)
    assert stats.trades_90d == 0
    assert stats.realized_pnl_90d == Decimal("0.00")
    assert stats.win_rate_90d == Decimal("0.0000")


def test_liquidation_treated_as_close():
    events = [
        _ev("open",        "long", "50000", "3000", "20", 0),
        _ev("liquidation", "long", "50000", "2900", "20", 5, pnl="-1666"),
    ]
    stats = score_wallet(events)
    assert stats.trades_90d == 1
    assert stats.realized_pnl_90d == Decimal("-1666.00")
    assert stats.win_rate_90d == Decimal("0.0000")


def test_side_split_long_only_keeps_short_null():
    events = [
        _ev("open",  "long", "10000", "3000", "5", 0),
        _ev("close", "long", "10000", "3100", "5", 5, pnl="333"),
    ]
    stats = score_wallet(events)
    assert stats.win_rate_long_90d == Decimal("1.0000")
    assert stats.win_rate_short_90d is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make backend-test -- tests/test_perp_scoring.py -v`
Expected: All seven tests fail with `ImportError: cannot import name 'PerpEvent'` or similar.

- [ ] **Step 3: Write the kernel**

Create `backend/app/services/perp_scoring.py`:

```python
"""Per-wallet 90d FIFO scoring of GMX V2 perp activity.

Pure compute. The cron in workers/perp_scoring_jobs.py is responsible for
loading events out of `onchain_perp_event` and persisting results to
`perp_wallet_score`. This module knows nothing about the DB.

FIFO model
----------
Per (market, side) we maintain a queue of lots, each a tuple of
(remaining_size_usd, open_ts). open + increase append to the queue;
close / decrease / liquidation pop lots from the head, partially or fully
consuming each. PnL is supplied by the event (decoded upstream) and
proportionally allocated when a close splits across lots.

Orphan closes (close with empty inventory) are silently dropped — the
wallet was already trading before the 90d window, so we cannot fairly
attribute a P/L outcome.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable

LEADERBOARD_LOOKBACK_DAYS = 90
LEADERBOARD_MIN_TRADES = 30
LEADERBOARD_MIN_WIN_RATE = Decimal("0.60")
LEADERBOARD_MIN_PNL_USD = Decimal("10000")
DEFAULT_WATCH_NOTIONAL_USD = Decimal("25000")

OPEN_KINDS = {"open", "increase"}
CLOSE_KINDS = {"close", "decrease", "liquidation"}


@dataclass(frozen=True)
class PerpEvent:
    ts: datetime
    market: str
    side: str           # "long" | "short"
    event_kind: str     # open | increase | close | decrease | liquidation
    size_usd: Decimal
    price_usd: Decimal
    leverage: Decimal
    pnl_usd: Decimal | None  # NULL on opens/increases


@dataclass
class WalletStats:
    trades_90d: int = 0
    win_rate_90d: Decimal = Decimal("0.0000")
    win_rate_long_90d: Decimal | None = None
    win_rate_short_90d: Decimal | None = None
    realized_pnl_90d: Decimal = Decimal("0.00")
    avg_hold_secs: int = 0
    avg_position_usd: Decimal = Decimal("0.00")
    avg_leverage: Decimal = Decimal("0.00")


@dataclass
class _RoundTrip:
    side: str
    notional_usd: Decimal
    leverage: Decimal
    pnl_usd: Decimal
    hold_secs: int


def score_wallet(events: Iterable[PerpEvent]) -> WalletStats:
    events = sorted(events, key=lambda e: e.ts)
    # inventory: key = (market, side) → list of [remaining_size, open_ts, leverage]
    inventory: dict[tuple[str, str], list[list]] = defaultdict(list)
    trips: list[_RoundTrip] = []

    for ev in events:
        key = (ev.market, ev.side)
        if ev.event_kind in OPEN_KINDS:
            inventory[key].append([ev.size_usd, ev.ts, ev.leverage])
            continue
        if ev.event_kind not in CLOSE_KINDS:
            continue
        # Close path: pop FIFO until size_usd is consumed.
        remaining = ev.size_usd
        # PnL is reported on the whole close; allocate proportionally per lot.
        total_pnl = ev.pnl_usd or Decimal("0")
        consumed_total = ev.size_usd if ev.size_usd > 0 else Decimal("1")
        while remaining > 0 and inventory[key]:
            lot = inventory[key][0]
            take = min(remaining, lot[0])
            share = take / consumed_total
            trips.append(
                _RoundTrip(
                    side=ev.side,
                    notional_usd=take,
                    leverage=lot[2],
                    pnl_usd=(total_pnl * share).quantize(Decimal("0.01")),
                    hold_secs=int((ev.ts - lot[1]).total_seconds()),
                )
            )
            lot[0] -= take
            remaining -= take
            if lot[0] <= 0:
                inventory[key].pop(0)
        # remaining > 0 → orphan portion: silently drop.

    return _aggregate(trips)


def _aggregate(trips: list[_RoundTrip]) -> WalletStats:
    if not trips:
        return WalletStats()
    n = len(trips)
    wins = sum(1 for t in trips if t.pnl_usd > 0)
    longs = [t for t in trips if t.side == "long"]
    shorts = [t for t in trips if t.side == "short"]
    pnl = sum((t.pnl_usd for t in trips), Decimal("0"))
    hold_total = sum(t.hold_secs for t in trips)
    notional_total = sum((t.notional_usd for t in trips), Decimal("0"))
    leverage_total = sum((t.leverage for t in trips), Decimal("0"))

    def _wr(sub: list[_RoundTrip]) -> Decimal | None:
        if not sub:
            return None
        w = sum(1 for t in sub if t.pnl_usd > 0)
        return (Decimal(w) / Decimal(len(sub))).quantize(Decimal("0.0001"))

    return WalletStats(
        trades_90d=n,
        win_rate_90d=(Decimal(wins) / Decimal(n)).quantize(Decimal("0.0001")),
        win_rate_long_90d=_wr(longs),
        win_rate_short_90d=_wr(shorts),
        realized_pnl_90d=pnl.quantize(Decimal("0.01")),
        avg_hold_secs=int(hold_total / n),
        avg_position_usd=(notional_total / Decimal(n)).quantize(Decimal("0.01")),
        avg_leverage=(leverage_total / Decimal(n)).quantize(Decimal("0.01")),
    )
```

- [ ] **Step 4: Run tests until green**

Run: `make backend-test -- tests/test_perp_scoring.py -v`
Expected: all 7 pass. If any fail, adjust the kernel (do NOT relax the tests — they encode spec invariants).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/perp_scoring.py backend/tests/test_perp_scoring.py
git commit -m "feat(perp-copy): FIFO scoring kernel with unit tests"
```

---

## Task 4: Daily scoring cron

**Files:**
- Create: `backend/app/workers/perp_scoring_jobs.py`
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Write the cron entry**

Create `backend/app/workers/perp_scoring_jobs.py`:

```python
"""Daily cron: replay last 90d of onchain_perp_event into perp_wallet_score."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import get_sessionmaker
from app.core.models import OnchainPerpEvent, PerpWalletScore
from app.services.perp_scoring import (
    LEADERBOARD_LOOKBACK_DAYS,
    PerpEvent,
    score_wallet,
)

log = logging.getLogger(__name__)


async def score_perp_wallets(ctx: dict) -> dict:
    """Rebuild perp_wallet_score from the last 90d of onchain_perp_event.

    Latest-only table — each run rewrites every wallet's row. Cheap because
    the working set is a few thousand rows max.
    """
    SessionLocal = get_sessionmaker()
    cutoff = datetime.now(timezone.utc) - timedelta(days=LEADERBOARD_LOOKBACK_DAYS)
    by_wallet: dict[str, list[PerpEvent]] = defaultdict(list)
    with SessionLocal() as session:
        rows = session.execute(
            select(OnchainPerpEvent).where(OnchainPerpEvent.ts >= cutoff)
        ).scalars()
        for r in rows:
            by_wallet[r.account.lower()].append(
                PerpEvent(
                    ts=r.ts,
                    market=r.market,
                    side=r.side,
                    event_kind=r.event_kind,
                    size_usd=r.size_usd,
                    price_usd=r.price_usd,
                    leverage=r.leverage,
                    pnl_usd=r.pnl_usd,
                )
            )

        written = 0
        for wallet, events in by_wallet.items():
            stats = score_wallet(events)
            if stats.trades_90d == 0:
                continue
            stmt = pg_insert(PerpWalletScore.__table__).values(
                wallet=wallet,
                trades_90d=stats.trades_90d,
                win_rate_90d=stats.win_rate_90d,
                win_rate_long_90d=stats.win_rate_long_90d,
                win_rate_short_90d=stats.win_rate_short_90d,
                realized_pnl_90d=stats.realized_pnl_90d,
                avg_hold_secs=stats.avg_hold_secs,
                avg_position_usd=stats.avg_position_usd,
                avg_leverage=stats.avg_leverage,
                updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["wallet"],
                set_={
                    "trades_90d": stats.trades_90d,
                    "win_rate_90d": stats.win_rate_90d,
                    "win_rate_long_90d": stats.win_rate_long_90d,
                    "win_rate_short_90d": stats.win_rate_short_90d,
                    "realized_pnl_90d": stats.realized_pnl_90d,
                    "avg_hold_secs": stats.avg_hold_secs,
                    "avg_position_usd": stats.avg_position_usd,
                    "avg_leverage": stats.avg_leverage,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            session.execute(stmt)
            written += 1
        session.commit()
    log.info("score_perp_wallets: wrote %d rows", written)
    return {"wallets_scored": written}
```

- [ ] **Step 2: Register the cron**

In `backend/app/workers/arq_settings.py`:

1. Add the import alongside other worker imports near the top:

```python
from app.workers.perp_scoring_jobs import score_perp_wallets
```

2. Find the `WorkerSettings` class (or the equivalent cron registration block — likely a `cron_jobs = [...]` list). Add a cron entry that fires daily at 04:23 UTC. Example (match the style used for the existing `score_wallets` cron at 04:13):

```python
cron(score_perp_wallets, hour={4}, minute={23}, run_at_startup=False),
```

3. Also export `score_perp_wallets` in the worker functions tuple if the file uses one (mirror how `score_wallets` is wired).

If the file's cron structure differs from this template, follow the existing pattern. Do NOT invent a new pattern.

- [ ] **Step 3: Run the cron manually once for smoke test**

Run: `docker compose exec worker python -c "import asyncio; from app.workers.perp_scoring_jobs import score_perp_wallets; print(asyncio.run(score_perp_wallets({})))"`
Expected: `{'wallets_scored': N}` where N ≥ 0. No exception.

- [ ] **Step 4: Verify rows landed**

Run: `docker compose exec api python -c "from app.core.db import get_sessionmaker; from app.core.models import PerpWalletScore; s=get_sessionmaker()(); print(s.query(PerpWalletScore).count())"`
Expected: integer (likely small on a fresh DB).

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/perp_scoring_jobs.py backend/app/workers/arq_settings.py
git commit -m "feat(perp-copy): daily score_perp_wallets cron @ 04:23 UTC"
```

---

## Task 5: Watchlist Redis cache + pub/sub

**Files:**
- Create: `backend/app/realtime/perp_watchlist_cache.py`

- [ ] **Step 1: Write the cache module**

Create `backend/app/realtime/perp_watchlist_cache.py`:

```python
"""Redis-backed cache of the perp watchlist for the realtime hot path.

Primary invalidation is via Redis pub/sub on `perp_watchlist:invalidate`.
A 30s TTL is a safety net so the listener self-heals if it ever misses a
publish (e.g. transient Redis disconnect).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.models import PerpWatchlist

log = logging.getLogger(__name__)

INVALIDATE_CHANNEL = "perp_watchlist:invalidate"
CACHE_TTL_SECONDS = 30


class PerpWatchlistCache:
    """In-process watchlist (hex address → min_notional_usd Decimal).

    Refreshed on TTL expiry and on pub/sub invalidation.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._entries: dict[str, Decimal] = {}
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self._reload()
        asyncio.create_task(self._subscribe_invalidations())

    async def lookup(self, account: str) -> Decimal | None:
        """Return the min_notional_usd floor if `account` is watched, else None."""
        if time.monotonic() - self._loaded_at > CACHE_TTL_SECONDS:
            await self._reload()
        return self._entries.get(account.lower())

    async def _reload(self) -> None:
        async with self._lock:
            SessionLocal = get_sessionmaker()
            with SessionLocal() as session:
                rows = session.execute(select(PerpWatchlist)).scalars().all()
            self._entries = {r.wallet.lower(): r.min_notional_usd for r in rows}
            self._loaded_at = time.monotonic()
        log.info("perp_watchlist_cache: %d entries loaded", len(self._entries))

    async def _subscribe_invalidations(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(INVALIDATE_CHANNEL)
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await self._reload()
            except Exception:
                log.exception("perp_watchlist_cache reload failed")


async def publish_invalidate(redis: Redis) -> None:
    """Called by the CRUD endpoints after every watchlist mutation."""
    await redis.publish(INVALIDATE_CHANNEL, json.dumps({"ts": time.time()}))
```

- [ ] **Step 2: Smoke-test import**

Run: `docker compose exec api python -c "from app.realtime.perp_watchlist_cache import PerpWatchlistCache, publish_invalidate; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/realtime/perp_watchlist_cache.py
git commit -m "feat(perp-copy): redis-backed watchlist cache with pub/sub invalidation"
```

---

## Task 6: Alert dispatcher + listener integration

**Files:**
- Create: `backend/app/services/perp_watch_dispatch.py`
- Create: `backend/tests/test_perp_watch_dispatch.py`
- Modify: `backend/app/services/alerts/delivery.py`
- Modify: `backend/app/realtime/arbitrum_listener.py`

- [ ] **Step 1: Write the dispatcher**

Create `backend/app/services/perp_watch_dispatch.py`:

```python
"""Build payload + ship Telegram alert for a watchlist perp event.

Sits between the arbitrum_listener decoder and the existing
alerts.delivery layer so we get retries + formatting for free.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import AlertEvent, AlertRule, PerpWalletScore, PerpWatchlist
from app.services.alerts.delivery import dispatch
from sqlalchemy import select

log = logging.getLogger(__name__)

RULE_NAME = "perp_watch"
RULE_TYPE = "perp_watch"


def _ensure_rule(session) -> AlertRule:
    """Singleton AlertRule row that all perp_watch events FK to."""
    rule = session.execute(
        select(AlertRule).where(AlertRule.name == RULE_NAME)
    ).scalar_one_or_none()
    if rule is not None:
        return rule
    rule = AlertRule(
        name=RULE_NAME,
        rule_type=RULE_TYPE,
        params={},
        channels=[{"type": "telegram"}],
        enabled=False,  # cron evaluator skips disabled rules; we dispatch manually.
    )
    session.add(rule)
    session.commit()
    return rule


def build_payload(
    event: dict,
    watch: PerpWatchlist,
    score: PerpWalletScore | None,
) -> dict[str, Any]:
    """Shape the alert payload. `event` is the decoded GMX event dict."""
    return {
        "wallet": event["account"],
        "label": watch.label,
        "event_kind": event["event_kind"],
        "market": event["market"],
        "side": event["side"],
        "size_usd": str(event["size_usd"]),
        "leverage": str(event["leverage"]),
        "price_usd": str(event["price_usd"]),
        "pnl_usd": None if event.get("pnl_usd") is None else str(event["pnl_usd"]),
        "tx_hash": event["tx_hash"],
        "score": None if score is None else {
            "win_rate": str(score.win_rate_90d),
            "trades": score.trades_90d,
            "avg_hold_secs": score.avg_hold_secs,
        },
    }


async def dispatch_perp_watch(
    http: httpx.AsyncClient,
    event: dict,
    watch: PerpWatchlist,
) -> None:
    """Format + deliver + persist a single perp watchlist alert."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rule = _ensure_rule(session)
        score = session.execute(
            select(PerpWalletScore).where(PerpWalletScore.wallet == event["account"].lower())
        ).scalar_one_or_none()
        payload = build_payload(event, watch, score)
        delivered = await dispatch(
            http,
            [{"type": "telegram"}],
            rule_name=watch.label or event["account"][:10],
            rule_type=RULE_TYPE,
            payload=payload,
        )
        session.add(AlertEvent(
            rule_id=rule.id,
            fired_at=datetime.fromisoformat(event["ts"]) if isinstance(event["ts"], str) else event["ts"],
            payload=payload,
            delivered=delivered,
        ))
        session.commit()
```

- [ ] **Step 2: Extend the Telegram formatter**

In `backend/app/services/alerts/delivery.py`, inside `format_telegram_message`, add a branch for `rule_type == "perp_watch"` BEFORE the generic fallback. Read the existing formatter to match the formatting style; here is the branch to add:

```python
    if rule_type == "perp_watch":
        kind = payload.get("event_kind", "?")
        side = payload.get("side", "?")
        emoji = "🟢" if (kind in {"open", "increase"} and side == "long") else \
                "🔴" if (kind in {"open", "increase"} and side == "short") else "⚪"
        score = payload.get("score") or {}
        score_line = (
            f"\n★ {Decimal(score['win_rate'])*100:.0f}% win / "
            f"{score['trades']} trades / "
            f"avg {score['avg_hold_secs']//60}m"
            if score else ""
        )
        wallet_disp = payload.get("label") or payload.get("wallet", "?")[:10]
        size = Decimal(payload.get("size_usd", "0"))
        lev = Decimal(payload.get("leverage", "0"))
        return (
            f"{emoji} {kind.upper()}  {payload.get('market','?')}  "
            f"{side.upper()}  ${size:,.0f}  {lev:.1f}x\n"
            f"Wallet: {wallet_disp}{score_line}\n"
            f"Tx: {payload.get('tx_hash','')[:12]}…"
        )
```

Ensure `from decimal import Decimal` is imported at the top of `delivery.py` (add if not already present).

- [ ] **Step 3: Write dispatcher tests**

Create `backend/tests/test_perp_watch_dispatch.py`:

```python
"""Unit tests for perp watchlist alert payload building."""
from decimal import Decimal

from app.core.models import PerpWalletScore, PerpWatchlist
from app.services.perp_watch_dispatch import build_payload


def _watch(label="vitalik") -> PerpWatchlist:
    return PerpWatchlist(wallet="0xabc", label=label, min_notional_usd=Decimal("25000"))


def _event() -> dict:
    return {
        "account": "0xabc",
        "event_kind": "open",
        "market": "ETH-USD",
        "side": "long",
        "size_usd": Decimal("52300"),
        "leverage": Decimal("10"),
        "price_usd": Decimal("3000"),
        "pnl_usd": None,
        "tx_hash": "0xtx",
        "ts": "2026-05-17T12:00:00+00:00",
    }


def test_payload_no_score():
    p = build_payload(_event(), _watch(), score=None)
    assert p["wallet"] == "0xabc"
    assert p["label"] == "vitalik"
    assert p["score"] is None
    assert p["event_kind"] == "open"
    assert p["size_usd"] == "52300"


def test_payload_with_score():
    score = PerpWalletScore(
        wallet="0xabc",
        trades_90d=142,
        win_rate_90d=Decimal("0.78"),
        win_rate_long_90d=Decimal("0.80"),
        win_rate_short_90d=Decimal("0.70"),
        realized_pnl_90d=Decimal("240000"),
        avg_hold_secs=14 * 60,
        avg_position_usd=Decimal("50000"),
        avg_leverage=Decimal("8"),
    )
    p = build_payload(_event(), _watch(), score)
    assert p["score"]["trades"] == 142
    assert p["score"]["win_rate"] == "0.78"
    assert p["score"]["avg_hold_secs"] == 840
```

- [ ] **Step 4: Run dispatcher tests**

Run: `make backend-test -- tests/test_perp_watch_dispatch.py -v`
Expected: both tests pass.

- [ ] **Step 5: Wire into the arbitrum listener**

In `backend/app/realtime/arbitrum_listener.py`:

1. Add imports near the other imports:

```python
from app.realtime.perp_watchlist_cache import PerpWatchlistCache
from app.services.perp_watch_dispatch import dispatch_perp_watch
from app.core.db import get_sessionmaker
from app.core.models import PerpWatchlist
from sqlalchemy import select
```

2. In the listener's setup function (where the Redis client and DB pool are constructed; mirror how `arbitrum_listener.py` already wires Redis — search for `Redis` or `redis` to find the existing handle), instantiate and start the cache once:

```python
perp_watchlist = PerpWatchlistCache(redis)
await perp_watchlist.start()
```

3. After the persist step (look for where each decoded event is written to `onchain_perp_event`; the file already does `for ev in events: ... persist`. Find that loop), add the dispatch hop:

```python
floor = await perp_watchlist.lookup(ev.account)
if floor is None:
    continue
if ev.event_kind not in {"open", "increase", "close", "decrease", "liquidation"}:
    continue
if ev.size_usd < floor:
    continue
SessionLocal = get_sessionmaker()
with SessionLocal() as session:
    watch = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == ev.account.lower())
    ).scalar_one_or_none()
if watch is None:
    continue
await dispatch_perp_watch(
    http=ctx["http"],
    event={
        "account": ev.account,
        "event_kind": ev.event_kind,
        "market": ev.market,
        "side": ev.side,
        "size_usd": ev.size_usd,
        "leverage": ev.leverage,
        "price_usd": ev.price_usd,
        "pnl_usd": ev.pnl_usd,
        "tx_hash": ev.tx_hash,
        "ts": ev.ts,
    },
    watch=watch,
)
```

Where `ctx["http"]` is the existing httpx client the listener already uses for RPC calls. If the listener uses a different httpx client variable name, use that one.

- [ ] **Step 6: Run full test suite to catch import regressions**

Run: `make backend-test`
Expected: all tests pass. If any pre-existing tests fail, fix the regression (likely an import cycle in models.py).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/perp_watch_dispatch.py \
        backend/app/services/alerts/delivery.py \
        backend/app/realtime/arbitrum_listener.py \
        backend/tests/test_perp_watch_dispatch.py
git commit -m "feat(perp-copy): realtime alert dispatch on watched-wallet perp events"
```

---

## Task 7: API router

**Files:**
- Create: `backend/app/api/copy_trading.py`
- Create: `backend/tests/test_copy_trading_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the router**

Create `backend/app/api/copy_trading.py`:

```python
"""API surface for the /copy-trading page.

Endpoints:
- GET    /api/copy-trading/config         → leaderboard threshold constants
- GET    /api/copy-trading/leaderboard    → paginated ranked wallets
- GET    /api/copy-trading/wallets/{addr} → stat header + last 20 trips + histogram
- GET    /api/copy-trading/watchlist      → current watchlist
- POST   /api/copy-trading/watchlist      → add wallet
- PATCH  /api/copy-trading/watchlist/{addr}
- DELETE /api/copy-trading/watchlist/{addr}
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.cache import get_redis  # adjust if redis dep is named differently
from app.core.db import get_session
from app.core.models import OnchainPerpEvent, PerpWalletScore, PerpWatchlist
from app.realtime.perp_watchlist_cache import publish_invalidate
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
    limit: int = 100,
    min_trades: int = LEADERBOARD_MIN_TRADES,
    min_win: float = float(LEADERBOARD_MIN_WIN_RATE),
    min_pnl: float = float(LEADERBOARD_MIN_PNL_USD),
    session: Session = Depends(get_session),
) -> list[ScoreRow]:
    rows = session.execute(
        select(PerpWalletScore)
        .where(PerpWalletScore.trades_90d >= min_trades)
        .where(PerpWalletScore.win_rate_90d >= Decimal(str(min_win)))
        .where(PerpWalletScore.realized_pnl_90d >= Decimal(str(min_pnl)))
        .order_by(desc(PerpWalletScore.realized_pnl_90d))
        .limit(limit)
    ).scalars().all()
    watched = {
        w for (w,) in session.execute(select(PerpWatchlist.wallet)).all()
    }
    return [_score_to_row(r, r.wallet in watched) for r in rows]


@router.get("/wallets/{address}", response_model=WalletDetailOut)
def get_wallet_detail(
    address: str,
    session: Session = Depends(get_session),
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

    # Cheap histogram: re-run the scorer to get per-trip hold_secs would
    # require another query. For v1 we approximate from close-event ts minus
    # nearest prior open for the same (account, market, side). Keep simple:
    # build buckets by walking the 90d window once.
    hist = _hold_time_histogram(session, addr, cutoff)
    return WalletDetailOut(score=score_row, last_trades=last_trades, hold_time_histogram=hist)


def _hold_time_histogram(session: Session, addr: str, cutoff: datetime) -> HistogramBuckets:
    """Replay the wallet's events through a lightweight FIFO to get hold times.

    Reuses the same kernel pattern as perp_scoring but only emits per-trip
    hold_secs into bucket counters; no PnL math needed.
    """
    from collections import defaultdict
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


@router.get("/watchlist", response_model=list[WatchOut])
def get_watchlist(session: Session = Depends(get_session)) -> list[WatchOut]:
    rows = session.execute(select(PerpWatchlist).order_by(PerpWatchlist.created_at)).scalars().all()
    return [
        WatchOut(
            wallet=r.wallet, label=r.label,
            min_notional_usd=float(r.min_notional_usd), created_at=r.created_at,
        ) for r in rows
    ]


@router.post("/watchlist", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
async def add_watch(
    body: WatchCreate,
    session: Session = Depends(get_session),
    redis = Depends(get_redis),
) -> WatchOut:
    addr = body.wallet.lower()
    existing = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == addr)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="already on watchlist")
    row = PerpWatchlist(
        wallet=addr, label=body.label,
        min_notional_usd=Decimal(str(body.min_notional_usd))
        if body.min_notional_usd is not None else DEFAULT_WATCH_NOTIONAL_USD,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    await publish_invalidate(redis)
    return WatchOut(
        wallet=row.wallet, label=row.label,
        min_notional_usd=float(row.min_notional_usd), created_at=row.created_at,
    )


@router.patch("/watchlist/{address}", response_model=WatchOut)
async def update_watch(
    address: str,
    body: WatchUpdate,
    session: Session = Depends(get_session),
    redis = Depends(get_redis),
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
    await publish_invalidate(redis)
    return WatchOut(
        wallet=row.wallet, label=row.label,
        min_notional_usd=float(row.min_notional_usd), created_at=row.created_at,
    )


@router.delete("/watchlist/{address}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watch(
    address: str,
    session: Session = Depends(get_session),
    redis = Depends(get_redis),
) -> None:
    row = session.execute(
        select(PerpWatchlist).where(PerpWatchlist.wallet == address.lower())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not on watchlist")
    session.delete(row)
    session.commit()
    await publish_invalidate(redis)
```

Note: `get_redis` and `get_session` dependency-injectables should already exist (the other routers use them). If their import paths differ from `app.core.cache.get_redis` / `app.core.db.get_session`, find the correct names by reading e.g. `backend/app/api/whales.py` and matching that pattern.

- [ ] **Step 2: Mount the router**

In `backend/app/main.py`, mirror the existing block of `include_router` calls. Add:

```python
from app.api.copy_trading import router as copy_trading_router
# ... other imports ...
app.include_router(copy_trading_router, prefix="/api", dependencies=[AuthDep])
```

- [ ] **Step 3: Write API integration tests**

Create `backend/tests/test_copy_trading_api.py`:

```python
"""Integration tests for /api/copy-trading endpoints."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from app.core.models import OnchainPerpEvent, PerpWalletScore, PerpWatchlist


def _seed_score(session, wallet: str, **overrides) -> None:
    defaults = dict(
        wallet=wallet, trades_90d=50, win_rate_90d=Decimal("0.7"),
        win_rate_long_90d=Decimal("0.75"), win_rate_short_90d=Decimal("0.6"),
        realized_pnl_90d=Decimal("50000"), avg_hold_secs=900,
        avg_position_usd=Decimal("40000"), avg_leverage=Decimal("8"),
    )
    defaults.update(overrides)
    session.add(PerpWalletScore(**defaults))
    session.commit()


def test_config_returns_constants(client):
    r = client.get("/api/copy-trading/config")
    assert r.status_code == 200
    data = r.json()
    assert data["lookback_days"] == 90
    assert data["min_trades"] == 30
    assert data["min_win_rate"] == 0.60
    assert data["min_pnl_usd"] == 10000
    assert data["default_watch_notional_usd"] == 25000


def test_leaderboard_applies_filters(client, db_session):
    _seed_score(db_session, "0x" + "a" * 40, realized_pnl_90d=Decimal("80000"))
    # Below trades threshold:
    _seed_score(db_session, "0x" + "b" * 40, trades_90d=10)
    # Below win-rate threshold:
    _seed_score(db_session, "0x" + "c" * 40, win_rate_90d=Decimal("0.4"))
    r = client.get("/api/copy-trading/leaderboard")
    assert r.status_code == 200
    wallets = [row["wallet"] for row in r.json()]
    assert "0x" + "a" * 40 in wallets
    assert "0x" + "b" * 40 not in wallets
    assert "0x" + "c" * 40 not in wallets


def test_watchlist_crud(client):
    addr = "0x" + "d" * 40
    # add
    r = client.post("/api/copy-trading/watchlist", json={"wallet": addr, "label": "alice"})
    assert r.status_code == 201
    assert r.json()["min_notional_usd"] == 25000.0
    # duplicate
    r = client.post("/api/copy-trading/watchlist", json={"wallet": addr})
    assert r.status_code == 409
    # patch
    r = client.patch(f"/api/copy-trading/watchlist/{addr}", json={"min_notional_usd": 50000})
    assert r.status_code == 200
    assert r.json()["min_notional_usd"] == 50000.0
    # list
    r = client.get("/api/copy-trading/watchlist")
    assert any(row["wallet"] == addr for row in r.json())
    # delete
    r = client.delete(f"/api/copy-trading/watchlist/{addr}")
    assert r.status_code == 204
    r = client.get("/api/copy-trading/watchlist")
    assert not any(row["wallet"] == addr for row in r.json())


def test_wallet_detail_returns_histogram(client, db_session):
    addr = "0x" + "e" * 40
    _seed_score(db_session, addr)
    base_ts = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add_all([
        OnchainPerpEvent(
            ts=base_ts, venue="gmx_v2", account=addr, market="ETH-USD",
            event_kind="open", side="long",
            size_usd=Decimal("10000"), size_after_usd=Decimal("10000"),
            collateral_usd=Decimal("1000"), leverage=Decimal("10"),
            price_usd=Decimal("3000"), pnl_usd=None,
            tx_hash="0x" + "1" * 64, log_index=0,
        ),
        OnchainPerpEvent(
            ts=base_ts + timedelta(minutes=10), venue="gmx_v2", account=addr, market="ETH-USD",
            event_kind="close", side="long",
            size_usd=Decimal("10000"), size_after_usd=Decimal("0"),
            collateral_usd=Decimal("1000"), leverage=Decimal("10"),
            price_usd=Decimal("3100"), pnl_usd=Decimal("333"),
            tx_hash="0x" + "2" * 64, log_index=0,
        ),
    ])
    db_session.commit()
    r = client.get(f"/api/copy-trading/wallets/{addr}")
    assert r.status_code == 200
    data = r.json()
    assert data["score"]["wallet"] == addr
    # 10-minute hold → m5_15 bucket
    assert data["hold_time_histogram"]["m5_15"] == 1
    assert len(data["last_trades"]) == 2
```

Match the existing `conftest.py` fixtures (`client`, `db_session`) — if those fixture names differ in the repo, adjust accordingly.

- [ ] **Step 4: Run API tests**

Run: `make backend-test -- tests/test_copy_trading_api.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Smoke-test the live API**

Run: `curl -s http://localhost:8000/api/copy-trading/config | head`
Expected: JSON with lookback_days/min_trades/etc. (Will 401 if auth is enabled — log in via the dashboard first or use a stored session cookie.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/copy_trading.py backend/app/main.py backend/tests/test_copy_trading_api.py
git commit -m "feat(perp-copy): /api/copy-trading router (config/leaderboard/detail/watchlist)"
```

---

## Task 8: Frontend — API client

**Files:**
- Create: `frontend/src/api/copyTrading.ts`

- [ ] **Step 1: Write the client + TanStack hooks**

Create `frontend/src/api/copyTrading.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client"; // adjust to your existing axios/fetch wrapper

export type Config = {
  lookback_days: number;
  min_trades: number;
  min_win_rate: number;
  min_pnl_usd: number;
  default_watch_notional_usd: number;
};

export type ScoreRow = {
  wallet: string;
  trades_90d: number;
  win_rate_90d: number;
  win_rate_long_90d: number | null;
  win_rate_short_90d: number | null;
  realized_pnl_90d: number;
  avg_hold_secs: number;
  avg_position_usd: number;
  avg_leverage: number;
  on_watchlist: boolean;
};

export type TripRow = {
  ts: string;
  market: string;
  side: string;
  event_kind: string;
  size_usd: number;
  pnl_usd: number | null;
};

export type HistogramBuckets = {
  lt_5m: number;
  m5_15: number;
  m15_60: number;
  h1_24: number;
  gt_1d: number;
};

export type WalletDetail = {
  score: ScoreRow | null;
  last_trades: TripRow[];
  hold_time_histogram: HistogramBuckets;
};

export type WatchRow = {
  wallet: string;
  label: string | null;
  min_notional_usd: number;
  created_at: string;
};

export function useCopyTradingConfig() {
  return useQuery({
    queryKey: ["copy-trading", "config"],
    queryFn: async () => (await api.get<Config>("/copy-trading/config")).data,
    staleTime: 1000 * 60 * 60,
  });
}

export function useLeaderboard(args: {
  minTrades?: number; minWin?: number; minPnl?: number;
} = {}) {
  return useQuery({
    queryKey: ["copy-trading", "leaderboard", args],
    queryFn: async () => {
      const r = await api.get<ScoreRow[]>("/copy-trading/leaderboard", { params: {
        min_trades: args.minTrades, min_win: args.minWin, min_pnl: args.minPnl,
      }});
      return r.data;
    },
    refetchInterval: 60_000,
  });
}

export function useWalletDetail(address: string | null) {
  return useQuery({
    queryKey: ["copy-trading", "wallet", address],
    queryFn: async () =>
      (await api.get<WalletDetail>(`/copy-trading/wallets/${address}`)).data,
    enabled: !!address,
  });
}

export function useWatchlist() {
  return useQuery({
    queryKey: ["copy-trading", "watchlist"],
    queryFn: async () => (await api.get<WatchRow[]>("/copy-trading/watchlist")).data,
    refetchInterval: 30_000,
  });
}

export function useAddWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { wallet: string; label?: string; min_notional_usd?: number }) =>
      (await api.post<WatchRow>("/copy-trading/watchlist", body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
    },
  });
}

export function useUpdateWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ wallet, ...patch }: { wallet: string; label?: string; min_notional_usd?: number }) =>
      (await api.patch<WatchRow>(`/copy-trading/watchlist/${wallet}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] }),
  });
}

export function useDeleteWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (wallet: string) => api.delete(`/copy-trading/watchlist/${wallet}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["copy-trading", "watchlist"] });
      qc.invalidateQueries({ queryKey: ["copy-trading", "leaderboard"] });
    },
  });
}
```

The `api` import at the top of the file must match the project's existing convention. Read `frontend/src/api.ts` (or `frontend/src/api/client.ts`) to find it — many panels import it as `import { api } from "../api"`. Use whichever the codebase already uses.

- [ ] **Step 2: Type-check the client**

Run: `docker compose exec frontend npm run -s build 2>&1 | tail -20`
Expected: build succeeds with no new errors (the page that consumes these hooks doesn't exist yet, but the file alone must type-check).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/copyTrading.ts
git commit -m "feat(perp-copy): frontend API hooks for /copy-trading"
```

---

## Task 9: Frontend — page + components

**Files:**
- Create: `frontend/src/routes/CopyTradingPage.tsx`
- Create: `frontend/src/components/copy-trading/Leaderboard.tsx`
- Create: `frontend/src/components/copy-trading/Watchlist.tsx`
- Create: `frontend/src/components/copy-trading/WalletDetail.tsx`
- Create: `frontend/src/components/copy-trading/HoldTimeHistogram.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: nav component (search for the existing tab strip — likely `frontend/src/components/Topbar.tsx` or `DashboardShell.tsx`)

- [ ] **Step 1: Create the leaderboard component**

Create `frontend/src/components/copy-trading/Leaderboard.tsx`:

```tsx
import { useLeaderboard, useAddWatch, useDeleteWatch, type ScoreRow } from "../../api/copyTrading";
import { AddressLink } from "../AddressLink";

type Props = { onSelect: (addr: string) => void };

export function Leaderboard({ onSelect }: Props) {
  const { data, isLoading } = useLeaderboard();
  const add = useAddWatch();
  const del = useDeleteWatch();

  if (isLoading) return <div className="p-6 text-sm opacity-60">Loading leaderboard…</div>;
  if (!data || data.length === 0)
    return <div className="p-6 text-sm opacity-60">No wallets meet the current thresholds.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs uppercase opacity-60">
        <tr>
          <th className="p-2">#</th>
          <th className="p-2">Wallet</th>
          <th className="p-2 text-right">Win</th>
          <th className="p-2 text-right">Long/Short</th>
          <th className="p-2 text-right">Trades</th>
          <th className="p-2 text-right">PnL</th>
          <th className="p-2 text-right">Hold</th>
          <th className="p-2 text-right">Lev</th>
          <th className="p-2"></th>
        </tr>
      </thead>
      <tbody>
        {data.map((r: ScoreRow, i: number) => (
          <tr
            key={r.wallet}
            className="cursor-pointer border-t border-white/5 hover:bg-white/5"
            onClick={() => onSelect(r.wallet)}
          >
            <td className="p-2 opacity-50">{i + 1}</td>
            <td className="p-2"><AddressLink address={r.wallet} /></td>
            <td className="p-2 text-right">{(r.win_rate_90d * 100).toFixed(0)}%</td>
            <td className="p-2 text-right">
              {r.win_rate_long_90d !== null ? `${(r.win_rate_long_90d * 100).toFixed(0)}%` : "—"}
              {" / "}
              {r.win_rate_short_90d !== null ? `${(r.win_rate_short_90d * 100).toFixed(0)}%` : "—"}
            </td>
            <td className="p-2 text-right">{r.trades_90d}</td>
            <td className="p-2 text-right">${r.realized_pnl_90d.toLocaleString()}</td>
            <td className="p-2 text-right">{Math.round(r.avg_hold_secs / 60)}m</td>
            <td className="p-2 text-right">{r.avg_leverage.toFixed(1)}x</td>
            <td className="p-2" onClick={(e) => e.stopPropagation()}>
              {r.on_watchlist ? (
                <button className="text-amber-400" onClick={() => del.mutate(r.wallet)} aria-label="remove from watchlist">★</button>
              ) : (
                <button className="opacity-40 hover:opacity-100" onClick={() => add.mutate({ wallet: r.wallet })} aria-label="add to watchlist">☆</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Create the watchlist component**

Create `frontend/src/components/copy-trading/Watchlist.tsx`:

```tsx
import { useState } from "react";
import { useWatchlist, useUpdateWatch, useDeleteWatch, type WatchRow } from "../../api/copyTrading";

export function Watchlist() {
  const { data } = useWatchlist();
  if (!data || data.length === 0)
    return <div className="p-4 text-sm opacity-60">No wallets watched yet. Add one from the leaderboard.</div>;
  return (
    <ul className="space-y-2 p-2">
      {data.map((r) => <WatchCard key={r.wallet} row={r} />)}
    </ul>
  );
}

function WatchCard({ row }: { row: WatchRow }) {
  const upd = useUpdateWatch();
  const del = useDeleteWatch();
  const [floor, setFloor] = useState(row.min_notional_usd);
  return (
    <li className="rounded border border-white/10 p-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-xs">{row.label || `${row.wallet.slice(0, 8)}…${row.wallet.slice(-4)}`}</div>
        <button className="text-xs opacity-50 hover:opacity-100" onClick={() => del.mutate(row.wallet)}>✕</button>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="opacity-60">Min $</span>
        <input
          type="number"
          className="w-24 rounded bg-black/40 px-2 py-1"
          value={floor}
          step={1000}
          onChange={(e) => setFloor(Number(e.target.value))}
          onBlur={() => floor !== row.min_notional_usd && upd.mutate({ wallet: row.wallet, min_notional_usd: floor })}
        />
      </div>
    </li>
  );
}
```

- [ ] **Step 3: Create the hold-time histogram**

Create `frontend/src/components/copy-trading/HoldTimeHistogram.tsx`:

```tsx
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import type { HistogramBuckets } from "../../api/copyTrading";

export function HoldTimeHistogram({ buckets }: { buckets: HistogramBuckets }) {
  const data = [
    { name: "<5m",   count: buckets.lt_5m },
    { name: "5–15m", count: buckets.m5_15 },
    { name: "15m–1h", count: buckets.m15_60 },
    { name: "1–24h", count: buckets.h1_24 },
    { name: ">1d",   count: buckets.gt_1d },
  ];
  return (
    <div className="h-40">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: 0, right: 0, top: 8, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="count" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Create the wallet detail panel**

Create `frontend/src/components/copy-trading/WalletDetail.tsx`:

```tsx
import { useWalletDetail, useAddWatch, type WalletDetail as TDetail } from "../../api/copyTrading";
import { AddressLink } from "../AddressLink";
import { HoldTimeHistogram } from "./HoldTimeHistogram";

export function WalletDetail({ address }: { address: string }) {
  const { data, isLoading } = useWalletDetail(address);
  const add = useAddWatch();
  if (isLoading || !data) return <div className="p-4 text-sm opacity-60">Loading…</div>;

  const { score, last_trades, hold_time_histogram } = data;

  return (
    <div className="space-y-4 rounded border border-white/10 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm"><AddressLink address={address} /></div>
        {score && !score.on_watchlist && (
          <button
            className="rounded bg-emerald-600/30 px-3 py-1 text-xs hover:bg-emerald-600/50"
            onClick={() => add.mutate({ wallet: address })}
          >+ Add to watchlist</button>
        )}
      </div>

      {score && <StatGrid score={score} />}

      <div>
        <div className="mb-1 text-xs uppercase opacity-60">Hold-time distribution</div>
        <HoldTimeHistogram buckets={hold_time_histogram} />
      </div>

      <div>
        <div className="mb-1 text-xs uppercase opacity-60">Last 20 events</div>
        <table className="w-full text-xs">
          <thead className="text-left opacity-50">
            <tr><th>ts</th><th>market</th><th>kind</th><th>side</th><th className="text-right">size</th><th className="text-right">pnl</th></tr>
          </thead>
          <tbody>
            {last_trades.map((t, i) => (
              <tr key={i} className="border-t border-white/5">
                <td>{new Date(t.ts).toLocaleString()}</td>
                <td>{t.market}</td>
                <td>{t.event_kind}</td>
                <td>{t.side}</td>
                <td className="text-right">${t.size_usd.toLocaleString()}</td>
                <td className={`text-right ${t.pnl_usd && t.pnl_usd > 0 ? "text-emerald-400" : t.pnl_usd && t.pnl_usd < 0 ? "text-rose-400" : "opacity-50"}`}>
                  {t.pnl_usd === null ? "—" : `$${t.pnl_usd.toLocaleString()}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatGrid({ score }: { score: TDetail["score"] & object }) {
  const cells: [string, string][] = [
    ["Win rate", `${(score.win_rate_90d * 100).toFixed(0)}%`],
    ["Long win", score.win_rate_long_90d !== null ? `${(score.win_rate_long_90d * 100).toFixed(0)}%` : "—"],
    ["Short win", score.win_rate_short_90d !== null ? `${(score.win_rate_short_90d * 100).toFixed(0)}%` : "—"],
    ["Trades", score.trades_90d.toString()],
    ["PnL 90d", `$${score.realized_pnl_90d.toLocaleString()}`],
    ["Avg hold", `${Math.round(score.avg_hold_secs / 60)}m`],
    ["Avg size", `$${score.avg_position_usd.toLocaleString()}`],
    ["Avg lev", `${score.avg_leverage.toFixed(1)}x`],
  ];
  return (
    <div className="grid grid-cols-4 gap-2">
      {cells.map(([k, v]) => (
        <div key={k} className="rounded bg-white/5 p-2">
          <div className="text-[10px] uppercase opacity-50">{k}</div>
          <div className="text-sm font-medium">{v}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create the page**

Create `frontend/src/routes/CopyTradingPage.tsx`:

```tsx
import { useState } from "react";
import { Leaderboard } from "../components/copy-trading/Leaderboard";
import { Watchlist } from "../components/copy-trading/Watchlist";
import { WalletDetail } from "../components/copy-trading/WalletDetail";

export default function CopyTradingPage() {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Copy Trading</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="md:col-span-2 rounded border border-white/10">
          <Leaderboard onSelect={setSelected} />
        </div>
        <div className="rounded border border-white/10">
          <div className="border-b border-white/10 p-3 text-xs uppercase opacity-60">Watchlist</div>
          <Watchlist />
        </div>
      </div>
      {selected && <WalletDetail address={selected} />}
    </div>
  );
}
```

- [ ] **Step 6: Add the route + nav entry**

In `frontend/src/App.tsx` (or wherever React Router is configured — search for `Route path=` in the file), add a new route:

```tsx
import CopyTradingPage from "./routes/CopyTradingPage";
// ... inside <Routes>
<Route path="/copy-trading" element={<CopyTradingPage />} />
```

Find the existing nav tab strip (search for `Overview` literal across `frontend/src/`) and add an entry mirroring its style:

```tsx
{ to: "/copy-trading", label: "Copy Trading" }
```

- [ ] **Step 7: Build to verify**

Run: `docker compose exec frontend npm run -s build`
Expected: build succeeds, no type errors.

- [ ] **Step 8: Visual check in browser**

Run: `make up` (if not already running), navigate to http://localhost:5173/copy-trading. Verify:
- "Copy Trading" appears in the nav.
- Page renders without errors.
- Leaderboard shows "No wallets meet the current thresholds" (expected on a fresh DB) or rows if scoring has run.
- Adding a wallet via the watchlist API (`curl -X POST .../watchlist -d '{"wallet":"0x...."}'`) makes it appear in the right column.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/CopyTradingPage.tsx \
        frontend/src/components/copy-trading/ \
        frontend/src/App.tsx \
        frontend/src/components/Topbar.tsx
git commit -m "feat(perp-copy): /copy-trading page (leaderboard + watchlist + detail)"
```

(Adjust the second-to-last path if the nav lives in `DashboardShell.tsx` instead.)

---

## Task 10: Wallet drawer "Perp performance" tile

**Files:**
- Create: `frontend/src/components/copy-trading/PerpPerformanceTile.tsx`
- Modify: `frontend/src/components/WalletDrawer.tsx`

- [ ] **Step 1: Create the tile**

Create `frontend/src/components/copy-trading/PerpPerformanceTile.tsx`:

```tsx
import { useWalletDetail } from "../../api/copyTrading";

export function PerpPerformanceTile({ address }: { address: string }) {
  const { data } = useWalletDetail(address);
  const score = data?.score;
  if (!score) return null;
  return (
    <div className="rounded border border-amber-500/30 bg-amber-500/5 p-3">
      <div className="mb-2 text-[10px] uppercase tracking-wide opacity-70">Perp performance (90d)</div>
      <div className="grid grid-cols-4 gap-2 text-xs">
        <Cell k="Win" v={`${(score.win_rate_90d * 100).toFixed(0)}%`} />
        <Cell k="Trades" v={score.trades_90d.toString()} />
        <Cell k="PnL" v={`$${score.realized_pnl_90d.toLocaleString()}`} />
        <Cell k="Hold" v={`${Math.round(score.avg_hold_secs / 60)}m`} />
      </div>
    </div>
  );
}

function Cell({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] opacity-50">{k}</div>
      <div className="font-medium">{v}</div>
    </div>
  );
}
```

- [ ] **Step 2: Mount in WalletDrawer**

In `frontend/src/components/WalletDrawer.tsx`, import the tile near the other tile imports:

```tsx
import { PerpPerformanceTile } from "./copy-trading/PerpPerformanceTile";
```

Inside the drawer body, between the existing balance card and token holdings (or wherever the existing smart-money tile is rendered — search for `wallet_score` or similar), add:

```tsx
<PerpPerformanceTile address={address} />
```

The tile returns `null` when no score row exists, so it's safe to mount unconditionally.

- [ ] **Step 3: Build to verify**

Run: `docker compose exec frontend npm run -s build`
Expected: build succeeds.

- [ ] **Step 4: Visual check**

Open the wallet drawer for a wallet that has a `perp_wallet_score` row. Tile should appear above token holdings. For a wallet with no perp activity, tile is hidden.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/copy-trading/PerpPerformanceTile.tsx \
        frontend/src/components/WalletDrawer.tsx
git commit -m "feat(perp-copy): perp-performance tile in wallet drawer"
```

---

## Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append v5 sub-track entry**

In `CLAUDE.md`, find the `## v5 status` section. After the existing `v5-onchain-perps` bullet, add:

```markdown
- v5-perp-copy-trading ✅ Operator-curated copy-trading workflow on top of v5-onchain-perps. Daily 04:23 UTC cron `score_perp_wallets` FIFO-matches the last 90d of `onchain_perp_event` per (wallet, market, side) and upserts to `perp_wallet_score` (8 stats: trades, win rate, long/short split, realized PnL, avg hold, avg position, avg leverage). New `perp_watchlist` table holds the curated set; CRUD via `/api/copy-trading/watchlist` publishes a Redis pub/sub `perp_watchlist:invalidate` consumed by the arbitrum listener, which keeps a 30s-TTL cached set in-process. After every decoded GMX event, the listener checks watchlist membership + per-watch `min_notional_usd` floor (default $25k) and dispatches a Telegram alert via the existing `alerts.delivery` module. Alerts persist to `alert_events` under a singleton `perp_watch` AlertRule so they show in the existing Alerts panel and Telegram thread. New `/copy-trading` page (`/copy-trading` route) renders a 90d leaderboard (filtered ≥30 trades / ≥60% win / ≥$10k PnL by default; thresholds live as named constants in `app/services/perp_scoring.py` and ride a Postgres partial index for cheap leaderboard scans), a watchlist column with inline editable min-notional, and a per-wallet detail panel (8-stat header, last 20 events, hold-time histogram). Wallet drawer gains a "Perp performance" tile when a score row exists. v1 covers GMX V2 on Arbitrum only; the FIFO kernel is venue-agnostic so adding Vertex/Aevo/dYdX later is decoder + market-registry work. Spec: `docs/superpowers/specs/2026-05-17-perp-copy-trading-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md v5-perp-copy-trading status entry"
```

---

## Verification (end-to-end)

After Task 11:

- [ ] **Backend tests pass:** `make backend-test` → all green.
- [ ] **Frontend builds:** `docker compose exec frontend npm run -s build` → no errors.
- [ ] **Cron fires:** `docker compose exec worker python -c "import asyncio; from app.workers.perp_scoring_jobs import score_perp_wallets; print(asyncio.run(score_perp_wallets({})))"` → `{'wallets_scored': N}`.
- [ ] **Page loads:** http://localhost:5173/copy-trading renders without console errors.
- [ ] **Watchlist round-trip:** Add a wallet via the page → tail `docker compose logs arbitrum_realtime` → simulate or wait for a real GMX event from that wallet → confirm Telegram alert delivered (or, if no real activity, manually POST a synthetic event row to `onchain_perp_event` matching a watched wallet and confirm the dispatcher fires on the next listener tick).
- [ ] **Drawer tile:** Open the wallet drawer on a wallet with a `perp_wallet_score` row → tile visible.
- [ ] **Lint:** `make lint` → no new violations.

---

## Notes for the executor

- **Frequent commits:** every task ends with `git commit`. Do not batch commits across tasks.
- **TDD discipline:** Tasks 3 and 6 are TDD-first. Run the failing test before writing code. Do not relax the tests to make implementation easier — the tests encode invariants from the spec.
- **Path verification:** A few code blocks reference paths/utilities the spec assumes exist but may differ slightly (`get_redis` dep, `api` axios wrapper, exact nav file). Where flagged, read the existing pattern in a neighbor file and match it.
- **No new abstractions:** Do not refactor unrelated code. Do not introduce a new alert delivery channel; reuse `alerts.delivery.dispatch`.
- **Idle-mode safety:** All new components must degrade gracefully if no rows exist (empty leaderboard, empty watchlist, etc.). The page should render cleanly on a fresh DB.
