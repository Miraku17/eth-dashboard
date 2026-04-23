# M1 — Price / Volume Sync & Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest ETH OHLCV candles from Binance for six timeframes (1m, 5m, 15m, 1h, 4h, 1d), expose them via `/api/price/candles`, and render a price + volume chart in the dashboard using TradingView Lightweight Charts. Backfill 30 days of 1h and 7 days of 1m on first run; keep data current via arq cron jobs.

**Architecture:** A thin `BinanceClient` (httpx async) fetches `/api/v3/klines`. A `PriceSyncService` maps klines to `PriceCandle` rows and upserts them. Two arq jobs run: `backfill_price_history` (idempotent, runs once on worker startup) and `sync_price_latest` (cron every minute — fetches the most recent candle for each active timeframe and upserts). REST endpoint `GET /api/price/candles` serves query-filtered candles. Frontend adds a `PriceChart` component with a timeframe selector that fetches the current timeframe's candles and renders them.

**Tech Stack:** httpx, arq (with `cron_jobs`), SQLAlchemy bulk upsert via `insert().on_conflict_do_update`. Frontend: `lightweight-charts` (v4). All existing M0 infrastructure.

**Spec reference:** `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md`

**Confirmed assumptions (from brainstorming):**
- Source: Binance public klines (`ETHUSDT`), no API key
- Timeframes: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
- Backfill: 30d of 1h + 7d of 1m on first run
- "Significant change" alerting deferred to M4

---

## File Structure

```
backend/
├── app/
│   ├── clients/
│   │   ├── __init__.py                  (create)
│   │   └── binance.py                   (create) — async klines client
│   ├── services/
│   │   ├── __init__.py                  (create)
│   │   └── price_sync.py                (create) — upsert logic, backfill/sync orchestration
│   ├── workers/
│   │   ├── arq_settings.py              (modify) — register price jobs + cron, drop noop
│   │   └── price_jobs.py                (create) — arq task wrappers
│   └── api/
│       ├── price.py                     (create) — GET /api/price/candles
│       └── schemas.py                   (create) — Pydantic response models
├── app/main.py                          (modify) — include price router
└── tests/
    ├── test_binance_client.py           (create)
    ├── test_price_sync.py                (create) — uses migrated_engine fixture
    ├── test_price_api.py                 (create)
    └── fixtures/
        └── binance_klines_1h.json       (create) — recorded response for tests

frontend/
├── package.json                         (modify) — add lightweight-charts
└── src/
    ├── api.ts                           (create) — typed fetch wrapper
    ├── components/
    │   ├── PriceChart.tsx               (create)
    │   └── TimeframeSelector.tsx        (create)
    └── App.tsx                          (modify) — render PriceChart + selector
```

---

### Task 1: Binance client

**Files:**
- Create: `backend/app/clients/__init__.py` (empty)
- Create: `backend/app/clients/binance.py`
- Create: `backend/tests/fixtures/__init__.py` (empty)
- Create: `backend/tests/fixtures/binance_klines_1h.json`
- Create: `backend/tests/test_binance_client.py`

- [ ] **Step 1: Record a fixture**

Create `backend/tests/fixtures/binance_klines_1h.json` with three representative klines (the content is what Binance literally returns — a JSON array of arrays). Use this exact content:

```json
[
  [1714089600000,"3000.00","3050.00","2990.00","3040.00","120.5","1714093199999","365000.00",1234,"80.0","240000.00","0"],
  [1714093200000,"3040.00","3060.00","3020.00","3055.00","100.0","1714096799999","305000.00",1000,"60.0","180000.00","0"],
  [1714096800000,"3055.00","3080.00","3050.00","3075.00","150.25","1714100399999","460000.00",1500,"90.0","275000.00","0"]
]
```

Columns (per Binance docs): `open_time, open, high, low, close, volume, close_time, quote_asset_volume, n_trades, taker_buy_base_vol, taker_buy_quote_vol, ignore`.

- [ ] **Step 2: Failing test `backend/tests/test_binance_client.py`**

```python
import json
from pathlib import Path

import httpx
import pytest

from app.clients.binance import BinanceClient, Kline


FIXTURE = Path(__file__).parent / "fixtures" / "binance_klines_1h.json"


@pytest.mark.asyncio
async def test_fetch_klines_parses_binance_response():
    fixture = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        assert request.url.params["symbol"] == "ETHUSDT"
        assert request.url.params["interval"] == "1h"
        assert request.url.params["limit"] == "500"
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        client = BinanceClient(http)
        klines = await client.fetch_klines("ETHUSDT", "1h", limit=500)

    assert len(klines) == 3
    assert isinstance(klines[0], Kline)
    assert klines[0].open_time_ms == 1714089600000
    assert klines[0].open == 3000.0
    assert klines[0].close == 3040.0
    assert klines[0].volume == 120.5


@pytest.mark.asyncio
async def test_fetch_klines_supports_time_range():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["startTime"] == "1714000000000"
        assert request.url.params["endTime"] == "1714100000000"
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        client = BinanceClient(http)
        result = await client.fetch_klines(
            "ETHUSDT", "1h", start_ms=1714000000000, end_ms=1714100000000
        )

    assert result == []
```

Run: `cd backend && .venv/bin/pytest tests/test_binance_client.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `backend/app/clients/binance.py`**

```python
from dataclasses import dataclass

import httpx

BINANCE_BASE_URL = "https://api.binance.com"
VALID_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


@dataclass(slots=True)
class Kline:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time_ms: int


class BinanceClient:
    """Thin async wrapper around Binance public klines endpoint."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 500,
    ) -> list[Kline]:
        if interval not in VALID_INTERVALS:
            raise ValueError(f"unsupported interval: {interval}")

        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        resp = await self._http.get("/api/v3/klines", params=params)
        resp.raise_for_status()
        return [_row_to_kline(row) for row in resp.json()]


def _row_to_kline(row: list) -> Kline:
    return Kline(
        open_time_ms=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time_ms=int(row[6]),
    )
```

- [ ] **Step 4: Run test — expect PASS**

`cd backend && .venv/bin/pytest tests/test_binance_client.py -v`

- [ ] **Step 5: Commit**

```
git add backend/app/clients backend/tests/fixtures backend/tests/test_binance_client.py
git commit -m "feat(backend): Binance klines client with kline dataclass"
```

---

### Task 2: Price sync service (upsert)

**Files:**
- Create: `backend/app/services/__init__.py` (empty)
- Create: `backend/app/services/price_sync.py`
- Create: `backend/tests/test_price_sync.py`

- [ ] **Step 1: Failing test `backend/tests/test_price_sync.py`**

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.clients.binance import Kline
from app.core.models import PriceCandle
from app.services.price_sync import upsert_klines


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        # clean between tests for isolation
        s.query(PriceCandle).delete()
        s.commit()
        yield s


def _kline(ts_ms: int, close: float) -> Kline:
    return Kline(
        open_time_ms=ts_ms,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=10.0,
        close_time_ms=ts_ms + 3600_000 - 1,
    )


def test_upsert_inserts_new_candles(session):
    klines = [_kline(1714089600000, 3040.0), _kline(1714093200000, 3055.0)]

    upsert_klines(session, symbol="ETHUSDT", timeframe="1h", klines=klines)

    rows = session.execute(
        select(PriceCandle).order_by(PriceCandle.ts)
    ).scalars().all()
    assert len(rows) == 2
    assert float(rows[0].close) == 3040.0
    assert rows[0].ts == datetime(2026, 4, 25, 23, 20, tzinfo=timezone.utc) or \
           rows[0].ts.timestamp() == 1714089600.0
    assert rows[0].symbol == "ETHUSDT"
    assert rows[0].timeframe == "1h"


def test_upsert_updates_existing_candle(session):
    ts_ms = 1714089600000
    upsert_klines(session, "ETHUSDT", "1h", [_kline(ts_ms, 3000.0)])
    upsert_klines(session, "ETHUSDT", "1h", [_kline(ts_ms, 3100.0)])  # updated close

    rows = session.execute(select(PriceCandle)).scalars().all()
    assert len(rows) == 1, "should have upserted, not inserted duplicate"
    assert float(rows[0].close) == 3100.0


def test_upsert_empty_list_is_noop(session):
    upsert_klines(session, "ETHUSDT", "1h", [])
    assert session.query(PriceCandle).count() == 0
```

Run: FAIL — `app.services.price_sync` missing.

- [ ] **Step 2: Implement `backend/app/services/price_sync.py`**

```python
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients.binance import Kline
from app.core.models import PriceCandle


def upsert_klines(
    session: Session,
    symbol: str,
    timeframe: str,
    klines: Iterable[Kline],
) -> int:
    """Upsert candles for (symbol, timeframe). Returns number of rows affected."""
    rows = [_kline_to_row(symbol, timeframe, k) for k in klines]
    if not rows:
        return 0

    stmt = pg_insert(PriceCandle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "timeframe", "ts"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount or 0


def _kline_to_row(symbol: str, timeframe: str, k: Kline) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": datetime.fromtimestamp(k.open_time_ms / 1000, tz=timezone.utc),
        "open": k.open,
        "high": k.high,
        "low": k.low,
        "close": k.close,
        "volume": k.volume,
    }
```

- [ ] **Step 3: Run — expect 3 passed**

`cd backend && .venv/bin/pytest tests/test_price_sync.py -v`

- [ ] **Step 4: Commit**

```
git add backend/app/services backend/tests/test_price_sync.py
git commit -m "feat(backend): price_sync upsert service for Binance klines"
```

---

### Task 3: Sync orchestration — backfill & forward sync functions

**Files:**
- Modify: `backend/app/services/price_sync.py` (append new functions)
- Modify: `backend/tests/test_price_sync.py` (append new tests)

- [ ] **Step 1: Failing test — append to `test_price_sync.py`**

```python
from datetime import timedelta

import httpx

from app.services.price_sync import backfill_timeframe, sync_latest


def _fixture_klines_for_range(start_ms: int, count: int, interval_ms: int) -> list:
    return [
        [
            start_ms + i * interval_ms,
            "3000.0", "3010.0", "2990.0", "3005.0", "10.0",
            start_ms + (i + 1) * interval_ms - 1,
            "30000.0", 1, "5.0", "15000.0", "0",
        ]
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_backfill_timeframe_fetches_and_upserts(session, migrated_engine):
    # Binance returns up to 1000 per request; backfill_timeframe must paginate.
    # Return 500 candles for first call, 0 for second (end of range).
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_fixture_klines_for_range(1_700_000_000_000, 500, 3_600_000))
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        total = await backfill_timeframe(
            http, session, symbol="ETHUSDT", timeframe="1h",
            start_ms=1_700_000_000_000, end_ms=1_700_000_000_000 + 500 * 3_600_000,
        )

    assert total == 500
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_sync_latest_fetches_recent_candles(session, migrated_engine):
    def handler(request):
        # sync_latest must not use startTime/endTime (just `limit=2`)
        assert "startTime" not in request.url.params
        return httpx.Response(200, json=_fixture_klines_for_range(1_700_000_000_000, 2, 3_600_000))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.binance.com") as http:
        n = await sync_latest(http, session, symbol="ETHUSDT", timeframe="1h")

    assert n == 2
```

Run: FAIL.

- [ ] **Step 2: Implement — append to `app/services/price_sync.py`**

```python
import httpx

from app.clients.binance import BinanceClient

# how many recent candles to fetch on each forward-sync tick
SYNC_LATEST_LIMIT = 2


async def backfill_timeframe(
    http: httpx.AsyncClient,
    session: Session,
    *,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    page_size: int = 500,
) -> int:
    """Paginate klines from start_ms to end_ms and upsert them. Returns total rows."""
    client = BinanceClient(http)
    total = 0
    cursor = start_ms
    while cursor < end_ms:
        batch = await client.fetch_klines(
            symbol, timeframe, start_ms=cursor, end_ms=end_ms, limit=page_size
        )
        if not batch:
            break
        total += upsert_klines(session, symbol, timeframe, batch)
        # advance cursor past the last fetched candle's open_time
        cursor = batch[-1].open_time_ms + 1
    return total


async def sync_latest(
    http: httpx.AsyncClient,
    session: Session,
    *,
    symbol: str,
    timeframe: str,
) -> int:
    """Fetch the most recent few candles (including the current forming one) and upsert."""
    client = BinanceClient(http)
    batch = await client.fetch_klines(symbol, timeframe, limit=SYNC_LATEST_LIMIT)
    return upsert_klines(session, symbol, timeframe, batch)
```

- [ ] **Step 3: Run all price_sync tests**

`cd backend && .venv/bin/pytest tests/test_price_sync.py -v` → 5 passed.

- [ ] **Step 4: Commit**

```
git add backend/app/services/price_sync.py backend/tests/test_price_sync.py
git commit -m "feat(backend): backfill and forward-sync orchestration for price data"
```

---

### Task 4: arq job wrappers + wire WorkerSettings cron

**Files:**
- Create: `backend/app/workers/price_jobs.py`
- Modify: `backend/app/workers/arq_settings.py` (replace `noop`, add cron jobs)

- [ ] **Step 1: Write `backend/app/workers/price_jobs.py`**

```python
"""arq task entrypoints for price sync. Thin wrappers around services.price_sync."""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.clients.binance import BINANCE_BASE_URL
from app.core.db import get_sessionmaker
from app.services.price_sync import backfill_timeframe, sync_latest

log = logging.getLogger(__name__)

SYMBOL = "ETHUSDT"
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")

# Initial backfill windows (days)
BACKFILL_WINDOWS = {
    "1m": 7,
    "5m": 30,
    "15m": 30,
    "1h": 30,
    "4h": 90,
    "1d": 365,
}


def _tf_to_ms(timeframe: str) -> int:
    mapping = {
        "1m": 60_000,
        "5m": 5 * 60_000,
        "15m": 15 * 60_000,
        "1h": 60 * 60_000,
        "4h": 4 * 60 * 60_000,
        "1d": 24 * 60 * 60_000,
    }
    return mapping[timeframe]


async def backfill_price_history(ctx: dict) -> dict:
    """Run once: backfill configured windows for each timeframe, skipping already-filled ranges."""
    http: httpx.AsyncClient = ctx["http"]
    SessionLocal = get_sessionmaker()
    results = {}
    end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    with SessionLocal() as session:
        for tf in TIMEFRAMES:
            days = BACKFILL_WINDOWS[tf]
            start_ms = end_ms - days * 24 * 60 * 60 * 1000
            n = await backfill_timeframe(
                http, session, symbol=SYMBOL, timeframe=tf,
                start_ms=start_ms, end_ms=end_ms,
            )
            log.info("backfilled %s: %d candles (%d days)", tf, n, days)
            results[tf] = n
    return results


async def sync_price_latest(ctx: dict) -> dict:
    """Forward sync: fetch the 2 most recent candles for each timeframe and upsert."""
    http: httpx.AsyncClient = ctx["http"]
    SessionLocal = get_sessionmaker()
    results = {}
    with SessionLocal() as session:
        for tf in TIMEFRAMES:
            n = await sync_latest(http, session, symbol=SYMBOL, timeframe=tf)
            results[tf] = n
    return results
```

- [ ] **Step 2: Rewrite `backend/app/workers/arq_settings.py`**

Replace the entire file contents with:

```python
import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from app.clients.binance import BINANCE_BASE_URL
from app.core.config import get_settings
from app.workers.price_jobs import backfill_price_history, sync_price_latest


async def startup(ctx: dict) -> None:
    ctx["http"] = httpx.AsyncClient(base_url=BINANCE_BASE_URL, timeout=15.0)
    # Kick off a one-shot backfill. arq executes this via enqueue on startup.
    await ctx["redis"].enqueue_job("backfill_price_history")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()


class WorkerSettings:
    functions = [backfill_price_history, sync_price_latest]
    cron_jobs = [
        cron("app.workers.price_jobs.sync_price_latest", minute=set(range(0, 60)), run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

Note: `cron(..., minute=set(range(0, 60)))` runs every minute. We use the module-path form so arq can look the function up.

- [ ] **Step 3: Verify imports**

```
cd backend && POSTGRES_USER=u POSTGRES_PASSWORD=p POSTGRES_DB=d POSTGRES_HOST=h REDIS_URL=redis://localhost:6379/0 \
  .venv/bin/python -c "from app.workers import arq_settings; print(arq_settings.WorkerSettings.functions)"
```

Expected: prints a list with the two coroutine functions.

- [ ] **Step 4: Commit**

```
git add backend/app/workers/price_jobs.py backend/app/workers/arq_settings.py
git commit -m "feat(backend): arq price sync jobs (backfill on startup, cron every minute)"
```

---

### Task 5: `/api/price/candles` endpoint

**Files:**
- Create: `backend/app/api/schemas.py`
- Create: `backend/app/api/price.py`
- Modify: `backend/app/main.py` (include router)
- Create: `backend/tests/test_price_api.py`

- [ ] **Step 1: Failing test `backend/tests/test_price_api.py`**

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import PriceCandle
from app.main import app


VALID_TFS = ("1m", "5m", "15m", "1h", "4h", "1d")


@pytest.fixture
def seeded_session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    base = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    with Session() as s:
        s.query(PriceCandle).delete()
        for i in range(10):
            s.add(PriceCandle(
                symbol="ETHUSDT", timeframe="1h",
                ts=base + timedelta(hours=i),
                open=Decimal("3000"), high=Decimal("3010"),
                low=Decimal("2990"), close=Decimal("3005"),
                volume=Decimal("100"),
            ))
        s.commit()
        yield s


def test_candles_endpoint_returns_ordered_candles(seeded_session):
    client = TestClient(app)
    resp = client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "ETHUSDT"
    assert data["timeframe"] == "1h"
    assert len(data["candles"]) == 5
    times = [c["time"] for c in data["candles"]]
    assert times == sorted(times), "candles must be returned in ascending time order"


def test_candles_endpoint_rejects_invalid_timeframe(seeded_session):
    client = TestClient(app)
    resp = client.get("/api/price/candles", params={"timeframe": "2h", "limit": 5})
    assert resp.status_code == 422


def test_candles_endpoint_default_timeframe_is_1h(seeded_session):
    client = TestClient(app)
    resp = client.get("/api/price/candles")
    assert resp.status_code == 200
    assert resp.json()["timeframe"] == "1h"
```

Run: FAIL.

- [ ] **Step 2: Implement `backend/app/api/schemas.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


class Candle(BaseModel):
    time: int = Field(description="open time, unix seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    candles: list[Candle]
```

- [ ] **Step 3: Implement `backend/app/api/price.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Candle, CandlesResponse, Timeframe
from app.core.db import get_session
from app.core.models import PriceCandle

router = APIRouter(prefix="/price", tags=["price"])

DEFAULT_SYMBOL = "ETHUSDT"


@router.get("/candles", response_model=CandlesResponse)
def get_candles(
    session: Annotated[Session, Depends(get_session)],
    timeframe: Timeframe = "1h",
    limit: int = Query(500, ge=1, le=2000),
    symbol: str = DEFAULT_SYMBOL,
) -> CandlesResponse:
    rows = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == symbol, PriceCandle.timeframe == timeframe)
        .order_by(PriceCandle.ts.desc())
        .limit(limit)
    ).scalars().all()

    # API returns ascending order for chart consumption
    rows = list(reversed(rows))

    return CandlesResponse(
        symbol=symbol,
        timeframe=timeframe,
        candles=[
            Candle(
                time=int(r.ts.timestamp()),
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume),
            )
            for r in rows
        ],
    )
```

- [ ] **Step 4: Modify `backend/app/main.py`**

Replace its contents with:

```python
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.price import router as price_router

app = FastAPI(title="Eth Analytics API", version="0.1.0")
app.include_router(health_router, prefix="/api")
app.include_router(price_router, prefix="/api")
```

- [ ] **Step 5: Run all backend tests**

`cd backend && .venv/bin/pytest -v` → expect all passing (config, schema, health, binance, price_sync × 5, price_api × 3).

- [ ] **Step 6: Commit**

```
git add backend/app/api/schemas.py backend/app/api/price.py backend/app/main.py backend/tests/test_price_api.py
git commit -m "feat(backend): GET /api/price/candles endpoint"
```

---

### Task 6: Frontend — add lightweight-charts + api client

**Files:**
- Modify: `frontend/package.json` (dependency)
- Create: `frontend/src/api.ts`

- [ ] **Step 1: Install dependency**

```
cd /Users/zianvalles/Projects/Eth/frontend && npm install lightweight-charts@^4.2.0
```

Expected: `package.json` now includes `"lightweight-charts": "^4.2.0"`.

- [ ] **Step 2: Write `frontend/src/api.ts`**

```ts
export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export type Candle = {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandlesResponse = {
  symbol: string;
  timeframe: Timeframe;
  candles: Candle[];
};

export async function fetchCandles(
  timeframe: Timeframe,
  limit = 500,
): Promise<CandlesResponse> {
  const r = await fetch(`/api/price/candles?timeframe=${timeframe}&limit=${limit}`);
  if (!r.ok) throw new Error(`candles fetch failed: ${r.status}`);
  return r.json();
}

export type Health = { status: string; version: string };

export async function fetchHealth(): Promise<Health> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error("health check failed");
  return r.json();
}
```

- [ ] **Step 3: Verify build still passes**

`cd frontend && npm run build` → expect success.

- [ ] **Step 4: Commit**

```
git add frontend/package.json frontend/package-lock.json frontend/src/api.ts
git commit -m "feat(frontend): add lightweight-charts dep and typed api client"
```

---

### Task 7: Frontend — TimeframeSelector + PriceChart components

**Files:**
- Create: `frontend/src/components/TimeframeSelector.tsx`
- Create: `frontend/src/components/PriceChart.tsx`

- [ ] **Step 1: Write `frontend/src/components/TimeframeSelector.tsx`**

```tsx
import type { Timeframe } from "../api";

const OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

type Props = {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
};

export default function TimeframeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-md border border-neutral-800 overflow-hidden">
      {OPTIONS.map((tf) => (
        <button
          key={tf}
          type="button"
          onClick={() => onChange(tf)}
          className={
            "px-3 py-1 text-sm font-medium transition " +
            (value === tf
              ? "bg-emerald-500 text-neutral-950"
              : "bg-neutral-900 text-neutral-300 hover:bg-neutral-800")
          }
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/PriceChart.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import { fetchCandles, type Timeframe } from "../api";

type Props = {
  timeframe: Timeframe;
};

export default function PriceChart({ timeframe }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    refetchInterval: 30_000,
  });

  // Initialize chart once
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#0a0a0a" },
        textColor: "#d4d4d4",
      },
      grid: {
        vertLines: { color: "#262626" },
        horzLines: { color: "#262626" },
      },
      width: containerRef.current.clientWidth,
      height: 420,
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  // Update series data whenever candles change
  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current) return;

    const candles = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const volumes = data.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? "#10b98155" : "#ef444455",
    }));

    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(volumes);
  }, [data]);

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">ETH / USDT</h2>
        {isLoading && <span className="text-sm text-neutral-500">loading…</span>}
        {error && <span className="text-sm text-red-400">chart unavailable</span>}
      </div>
      <div ref={containerRef} />
    </div>
  );
}
```

- [ ] **Step 3: Verify type-check + build**

`cd frontend && npm run build` → expect success.

- [ ] **Step 4: Commit**

```
git add frontend/src/components
git commit -m "feat(frontend): PriceChart + TimeframeSelector components"
```

---

### Task 8: Wire components into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Replace `frontend/src/App.tsx` with:**

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth, type Timeframe } from "./api";
import PriceChart from "./components/PriceChart";
import TimeframeSelector from "./components/TimeframeSelector";

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="min-h-screen p-8 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Eth Analytics</h1>
        {health && (
          <span className="text-xs text-neutral-500">
            api: {health.status} (v{health.version})
          </span>
        )}
      </header>
      <div className="flex items-center gap-4">
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
      </div>
      <PriceChart timeframe={timeframe} />
    </main>
  );
}
```

- [ ] **Step 2: Verify build**

`cd frontend && npm run build` → expect success.

- [ ] **Step 3: Commit**

```
git add frontend/src/App.tsx
git commit -m "feat(frontend): render PriceChart with timeframe selector on home"
```

---

### Task 9: End-to-end smoke test

**Files:** none (verification only)

- [ ] **Step 1: Fresh build + stack**

```
cd /Users/zianvalles/Projects/Eth
docker compose down -v  # wipe old postgres data so we test fresh backfill
docker compose up --build -d
```

- [ ] **Step 2: Wait for backfill to make progress**

Backfill runs once on worker startup (enqueued via redis). It hits Binance's public API (no key needed) and pages through a month of 1h candles + a week of 1m, etc. Allow ~60 seconds.

Poll the API:

```
for i in 1 2 3 4 5 6; do
  n=$(curl -s "http://localhost:8000/api/price/candles?timeframe=1h&limit=1000" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['candles']))")
  echo "attempt $i: $n candles"
  [ "$n" -gt 100 ] && break
  sleep 15
done
```

Expected: eventually prints a count > 100 (full backfill should reach ~720 for 30d of 1h).

- [ ] **Step 2a: If backfill is clearly not running, check worker logs**

```
docker compose logs worker --tail=50
```
If you see errors about arq not finding the function, or cron not firing, diagnose before proceeding.

- [ ] **Step 3: Manual UI check**

Open `http://localhost:5173` in a browser. Expect:
- Header "Eth Analytics" with `api: ok (v0.1.0)` top-right
- Timeframe selector (1m, 5m, 15m, 1h, 4h, 1d) — 1h is highlighted
- Candlestick chart with ~500 recent 1h candles + volume histogram
- Clicking another timeframe reloads the chart

If the chart is empty but the API returns candles, there's a frontend wiring bug — stop and investigate.

- [ ] **Step 4: Stop stack**

```
docker compose down
```

- [ ] **Step 5: Final backend test run**

```
cd backend && .venv/bin/pytest -v
```
Expect all tests passing.

- [ ] **Step 6: Commit (empty if nothing to commit — just tag the milestone)**

Nothing to commit in this task; skip. Proceed to Task 10.

---

### Task 10: CLAUDE.md — update after-M1 status

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a section before `## Commands` noting M1 scope**

Add this block after the `## Scope discipline` section:

```markdown
## Milestone status

- M0 ✅ scaffold (docker compose, schema, health, React/Vite)
- M1 ✅ ETH price & volume (Binance klines sync + `/api/price/candles` + chart UI)
- M2–M5 pending (see spec)
```

- [ ] **Step 2: Commit**

```
git add CLAUDE.md
git commit -m "docs: mark M1 complete in CLAUDE.md"
```

---

## Exit criteria for M1

- `docker compose up` brings up stack cleanly; worker does not crash
- Within ~60s of startup, `/api/price/candles?timeframe=1h&limit=1000` returns > 100 candles
- Worker runs `sync_price_latest` cron every minute (visible in `docker compose logs worker`)
- Frontend at `http://localhost:5173` shows a live candlestick chart with a working timeframe selector
- `pytest -v` passes (~12 tests total)
- Branch `feature/m1-price-volume` pushed; PR merged to `main`

## Next plan

After M1 merges, write `docs/superpowers/plans/<date>-m2-onchain-flows.md` covering Dune Analytics integration, exchange-flow + stablecoin-flow syncs, and the corresponding panels.
