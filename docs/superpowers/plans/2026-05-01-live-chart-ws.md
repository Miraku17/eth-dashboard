# Live Chart via Direct Binance WebSocket — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ETH price chart and price-hero ticker stream live from Binance directly, replacing 30s polling + full-series rebuilds with single-WS in-place updates so the UX feels like CoinMarketCap.

**Architecture:** Browser opens one combined-stream WebSocket to `wss://stream.binance.com:9443/stream?streams=ethusdt@trade/ethusdt@kline_<tf>`. A singleton manager (`lib/binanceWS.ts`) reference-counts subscribers, multiplexes streams over one socket, and reconnects with exponential backoff. `<PriceChart>` drops polling and calls `series.update()` on every kline tick. `<PriceHero>` subscribes to trades for the big-number price. Backend gets a 60s Redis cache around `/api/price/candles` for the bootstrap path.

**Tech Stack:** TypeScript, React, Lightweight Charts (already a dep — `series.update()` is built-in), TanStack Query, native browser `WebSocket`. Backend: FastAPI + redis-py (already a dep, used by sessions.py / sync_status.py — same pattern).

**Spec:** `docs/superpowers/specs/2026-05-01-live-chart-ws-design.md`.

**File map:**
- Create:
  - `backend/app/core/cache.py` — tiny JSON read-through Redis helper
  - `frontend/src/lib/binanceWS.ts` — singleton WS manager
  - `frontend/src/hooks/useBinanceTrade.ts` — React lifecycle wrapper
  - `frontend/src/hooks/useBinanceKline.ts` — React lifecycle wrapper
  - `frontend/src/hooks/useBinanceStatus.ts` — connection-state hook (drives the "disconnected" badge)
- Modify:
  - `backend/app/api/price.py` — wrap candles query in `cached_json_get`/`cached_json_set`
  - `backend/tests/test_price_api.py` — one new test asserting the second call is cached
  - `backend/tests/conftest.py` — autouse fixture to reset cache module's redis client between tests
  - `frontend/src/components/PriceChart.tsx` — drop `refetchInterval`, call `series.update()` on kline ticks, re-bootstrap on reconnect, render disconnected badge
  - `frontend/src/components/PriceHero.tsx` — read live trade price, derive change% against `(data.price - data.change24hAbs)`
  - `CLAUDE.md` — append a one-line entry under a new "## UI polish" sub-heading once shipped

No new dependencies. No new env vars.

---

## Task 1 — Tiny JSON read-through Redis helper

**Files:**
- Create: `backend/app/core/cache.py`
- Test: indirectly exercised by Task 2's price-API test.

- [ ] **Step 1: Create the cache module**

`backend/app/core/cache.py`:

```python
"""Tiny JSON read-through Redis helper.

Mirrors the singleton pattern used by `core/sessions.py` and
`core/sync_status.py` — one Redis client per process, lazy-init.

Designed for response-shaped payloads: store JSON, retrieve JSON.
TTL is required at write time; there's no implicit expiry.
"""
from __future__ import annotations

import json
from typing import Any

import redis

from app.core.config import get_settings

_client_instance: redis.Redis | None = None


def _client() -> redis.Redis:
    global _client_instance
    if _client_instance is None:
        _client_instance = redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _client_instance


def _reset_client_for_tests() -> None:
    """Drop the cached client so a new REDIS_URL takes effect."""
    global _client_instance
    _client_instance = None


def cached_json_get(key: str) -> Any:
    raw = _client().get(key)
    return json.loads(raw) if raw is not None else None


def cached_json_set(key: str, value: Any, ttl_seconds: int) -> None:
    _client().setex(key, ttl_seconds, json.dumps(value))
```

- [ ] **Step 2: Verify it imports clean**

Run: `cd backend && .venv/bin/python -c "from app.core.cache import cached_json_get, cached_json_set, _reset_client_for_tests; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/cache.py
git commit -m "feat(cache): add tiny JSON read-through Redis helper"
```

---

## Task 2 — Wrap `/api/price/candles` with the cache

**Files:**
- Modify: `backend/app/api/price.py`
- Modify: `backend/tests/test_price_api.py` (append one test)
- Modify: `backend/tests/conftest.py` (add a fixture reset)

- [ ] **Step 1: Add a test that proves the second call is cached**

Append to `backend/tests/test_price_api.py`:

```python
from unittest.mock import patch


def test_candles_endpoint_caches_response(seeded_session, auth_client):
    """Second call within TTL should NOT re-execute the SQL query."""
    # First call — populates cache
    r1 = auth_client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    assert r1.status_code == 200

    # Patch the SQL execute on the session bound to the request to count calls.
    # The endpoint is sync, so we wrap it via a monkeypatched executor on the engine.
    from app.core.db import get_session

    call_count = {"n": 0}
    real_get_session = get_session

    def counting_get_session():
        for s in real_get_session():
            orig_execute = s.execute

            def counting_execute(*a, **kw):
                call_count["n"] += 1
                return orig_execute(*a, **kw)

            s.execute = counting_execute  # type: ignore[method-assign]
            yield s

    from app.main import app
    app.dependency_overrides[get_session] = counting_get_session
    try:
        r2 = auth_client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert call_count["n"] == 0, "second call should be served from Redis without DB queries"
```

- [ ] **Step 2: Add an autouse fixture to flush the cache between tests**

Modify `backend/tests/conftest.py`. Find the existing `_flush_redis` autouse fixture and update it to also reset the cache-module client. Replace the existing fixture with:

```python
@pytest.fixture(autouse=True)
def _flush_redis(redis_container: RedisContainer) -> Iterator[None]:
    """Each test starts with an empty Redis so session/cache state is clean."""
    yield
    client = redis_container.get_client()
    client.flushdb()
    # Drop cached redis-client singletons so a flushed DB is seen.
    from app.core.cache import _reset_client_for_tests as _reset_cache
    _reset_cache()
```

(The `_reset_client_for_tests` import was added in Task 1.)

- [ ] **Step 3: Run the new test, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_price_api.py::test_candles_endpoint_caches_response -v`
Expected: FAIL — `assert call_count["n"] == 0` because no caching is wired yet.

- [ ] **Step 4: Wire the cache into the route**

Edit `backend/app/api/price.py`. Replace the entire file body with:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Candle, CandlesResponse, Timeframe
from app.core.cache import cached_json_get, cached_json_set
from app.core.db import get_session
from app.core.models import PriceCandle

router = APIRouter(prefix="/price", tags=["price"])

DEFAULT_SYMBOL = "ETHUSDT"
CANDLES_CACHE_TTL_S = 60


@router.get("/candles", response_model=CandlesResponse)
def get_candles(
    session: Annotated[Session, Depends(get_session)],
    timeframe: Timeframe = "1h",
    limit: int = Query(500, ge=1, le=2000),
    symbol: str = DEFAULT_SYMBOL,
) -> CandlesResponse:
    cache_key = f"candles:{symbol}:{timeframe}:{limit}"
    cached = cached_json_get(cache_key)
    if cached is not None:
        return CandlesResponse.model_validate(cached)

    rows = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == symbol, PriceCandle.timeframe == timeframe)
        .order_by(PriceCandle.ts.desc())
        .limit(limit)
    ).scalars().all()

    rows = list(reversed(rows))

    response = CandlesResponse(
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
    cached_json_set(cache_key, response.model_dump(mode="json"), CANDLES_CACHE_TTL_S)
    return response
```

- [ ] **Step 5: Run the test, expect PASS**

Run: `cd backend && .venv/bin/pytest tests/test_price_api.py -v`
Expected: all tests in the file PASS, including the new caching test.

- [ ] **Step 6: Sanity — full backend test suite still green**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | tail -10`
Expected: no new failures relative to main. (The two `test_flows_api` failures pre-exist on main and are unrelated.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/price.py backend/tests/test_price_api.py backend/tests/conftest.py
git commit -m "feat(price): 60s Redis cache around /api/price/candles"
```

---

## Task 3 — `lib/binanceWS.ts` singleton WS manager

**Files:**
- Create: `frontend/src/lib/binanceWS.ts`

This is the largest piece of code in the plan. No frontend test infra exists — validation is `npm run build` + manual smoke at the end.

- [ ] **Step 1: Create the manager**

Create `frontend/src/lib/binanceWS.ts`:

```typescript
/**
 * Singleton manager for our Binance market-data WebSocket.
 *
 * - One underlying `WebSocket` per tab, multiplexed via Binance's combined-
 *   stream URL (`/stream?streams=a/b`). Subscribers reference-count;
 *   the socket opens on first subscribe and closes on last unsubscribe.
 * - In-band SUBSCRIBE/UNSUBSCRIBE control messages add and remove streams
 *   without re-opening the socket.
 * - On unexpected close, reconnects with exponential backoff
 *   (1s, 2s, 4s, 8s, 16s, capped at 30s). Re-subscribes to all currently-
 *   live streams on each successful re-open.
 * - Fires `onReconnect` callbacks (after the first open) so consumers can
 *   re-bootstrap historical data and fill any gap.
 * - On `document.visibilitychange` returning from a >5min hidden state,
 *   force-closes the socket so the reconnect path runs.
 */

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export type TradeMsg = { price: number; ts: number };

export type KlineMsg = {
  openTime: number;   // unix seconds, the bar's start
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closed: boolean;     // true on the message that seals the bar
};

const BINANCE_WS_BASE = "wss://stream.binance.com:9443";
const SYMBOL = "ethusdt";
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000];
const HIDDEN_RECONNECT_THRESHOLD_MS = 5 * 60 * 1_000;

type TradeHandler = (m: TradeMsg) => void;
type KlineHandler = (m: KlineMsg) => void;
type StatusHandler = (connected: boolean) => void;
type ReconnectHandler = () => void;

type State = {
  ws: WebSocket | null;
  reconnectAttempts: number;
  reconnectTimer: number | null;
  hiddenSince: number | null;
  hasOpenedOnce: boolean;

  tradeHandlers: Set<TradeHandler>;
  klineHandlers: Map<Timeframe, Set<KlineHandler>>;
  statusHandlers: Set<StatusHandler>;
  reconnectHandlers: Set<ReconnectHandler>;
};

function streamNameKline(tf: Timeframe): string {
  return `${SYMBOL}@kline_${tf}`;
}
const STREAM_TRADE = `${SYMBOL}@trade`;

function buildUrl(streams: string[]): string {
  return `${BINANCE_WS_BASE}/stream?streams=${streams.join("/")}`;
}

function activeStreams(state: State): string[] {
  const out: string[] = [];
  if (state.tradeHandlers.size > 0) out.push(STREAM_TRADE);
  for (const [tf, set] of state.klineHandlers.entries()) {
    if (set.size > 0) out.push(streamNameKline(tf));
  }
  return out;
}

function notifyStatus(state: State, connected: boolean): void {
  for (const h of state.statusHandlers) h(connected);
}

function clearReconnectTimer(state: State): void {
  if (state.reconnectTimer !== null) {
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
}

function scheduleReconnect(state: State, openSocket: () => void): void {
  clearReconnectTimer(state);
  const delay = BACKOFF_MS[Math.min(state.reconnectAttempts, BACKOFF_MS.length - 1)];
  state.reconnectAttempts += 1;
  state.reconnectTimer = window.setTimeout(() => {
    if (activeStreams(state).length > 0) openSocket();
  }, delay);
}

function createManager() {
  const state: State = {
    ws: null,
    reconnectAttempts: 0,
    reconnectTimer: null,
    hiddenSince: null,
    hasOpenedOnce: false,
    tradeHandlers: new Set(),
    klineHandlers: new Map(),
    statusHandlers: new Set(),
    reconnectHandlers: new Set(),
  };

  function handleMessage(raw: string): void {
    let envelope: { stream?: string; data?: any };
    try {
      envelope = JSON.parse(raw);
    } catch {
      return;
    }
    const stream = envelope.stream;
    const data = envelope.data;
    if (!stream || !data) return;

    if (stream === STREAM_TRADE) {
      const msg: TradeMsg = {
        price: parseFloat(data.p),
        ts: data.T as number,
      };
      if (Number.isFinite(msg.price)) {
        for (const h of state.tradeHandlers) h(msg);
      }
      return;
    }

    // kline streams: ethusdt@kline_<tf>
    const klineMatch = stream.match(/^ethusdt@kline_(\w+)$/);
    if (klineMatch) {
      const tf = klineMatch[1] as Timeframe;
      const k = data.k;
      if (!k) return;
      const msg: KlineMsg = {
        openTime: Math.floor(k.t / 1000),
        open: parseFloat(k.o),
        high: parseFloat(k.h),
        low: parseFloat(k.l),
        close: parseFloat(k.c),
        volume: parseFloat(k.v),
        closed: !!k.x,
      };
      const set = state.klineHandlers.get(tf);
      if (set) for (const h of set) h(msg);
    }
  }

  function openSocket(): void {
    const streams = activeStreams(state);
    if (streams.length === 0) return;

    const url = buildUrl(streams);
    const ws = new WebSocket(url);
    state.ws = ws;

    ws.addEventListener("open", () => {
      state.reconnectAttempts = 0;
      notifyStatus(state, true);
      if (state.hasOpenedOnce) {
        for (const h of state.reconnectHandlers) h();
      }
      state.hasOpenedOnce = true;
    });

    ws.addEventListener("message", (ev) => {
      handleMessage(typeof ev.data === "string" ? ev.data : "");
    });

    ws.addEventListener("close", () => {
      state.ws = null;
      notifyStatus(state, false);
      if (activeStreams(state).length > 0) {
        scheduleReconnect(state, openSocket);
      }
    });

    ws.addEventListener("error", () => {
      // 'close' will fire after; let it own the reconnect path.
    });
  }

  function ensureSocket(): void {
    if (state.ws && state.ws.readyState <= 1) return;  // CONNECTING (0) or OPEN (1)
    clearReconnectTimer(state);
    state.reconnectAttempts = 0;
    openSocket();
  }

  function sendControl(method: "SUBSCRIBE" | "UNSUBSCRIBE", params: string[]): void {
    if (state.ws && state.ws.readyState === 1) {
      state.ws.send(JSON.stringify({ method, params, id: Date.now() }));
    }
    // If not yet OPEN, the next 'open' rebuilds the URL from activeStreams() so
    // we'll pick up the new subscription naturally.
  }

  function teardownIfIdle(): void {
    if (activeStreams(state).length === 0) {
      clearReconnectTimer(state);
      if (state.ws) {
        try {
          state.ws.close(1000, "no subscribers");
        } catch {
          /* ignore */
        }
        state.ws = null;
      }
    }
  }

  function subscribeTrade(handler: TradeHandler): () => void {
    state.tradeHandlers.add(handler);
    if (state.tradeHandlers.size === 1) {
      ensureSocket();
      sendControl("SUBSCRIBE", [STREAM_TRADE]);
    }
    return () => {
      state.tradeHandlers.delete(handler);
      if (state.tradeHandlers.size === 0) {
        sendControl("UNSUBSCRIBE", [STREAM_TRADE]);
        teardownIfIdle();
      }
    };
  }

  function subscribeKline(tf: Timeframe, handler: KlineHandler): () => void {
    let set = state.klineHandlers.get(tf);
    if (!set) {
      set = new Set();
      state.klineHandlers.set(tf, set);
    }
    set.add(handler);
    if (set.size === 1) {
      ensureSocket();
      sendControl("SUBSCRIBE", [streamNameKline(tf)]);
    }
    return () => {
      const s = state.klineHandlers.get(tf);
      if (!s) return;
      s.delete(handler);
      if (s.size === 0) {
        state.klineHandlers.delete(tf);
        sendControl("UNSUBSCRIBE", [streamNameKline(tf)]);
        teardownIfIdle();
      }
    };
  }

  function subscribeStatus(handler: StatusHandler): () => void {
    state.statusHandlers.add(handler);
    // Push the current state so consumers don't wait for the next event.
    handler(state.ws !== null && state.ws.readyState === 1);
    return () => {
      state.statusHandlers.delete(handler);
    };
  }

  function onReconnect(handler: ReconnectHandler): () => void {
    state.reconnectHandlers.add(handler);
    return () => {
      state.reconnectHandlers.delete(handler);
    };
  }

  // Visibility recovery: if hidden for >5 min, force a reconnect on return.
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        state.hiddenSince = Date.now();
        return;
      }
      const hiddenFor = state.hiddenSince ? Date.now() - state.hiddenSince : 0;
      state.hiddenSince = null;
      if (hiddenFor > HIDDEN_RECONNECT_THRESHOLD_MS && state.ws) {
        try {
          state.ws.close(4000, "tab returned from long hidden");
        } catch {
          /* ignore */
        }
      }
    });
  }

  return { subscribeTrade, subscribeKline, subscribeStatus, onReconnect };
}

export const binanceWS = createManager();
```

- [ ] **Step 2: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/binanceWS.ts
git commit -m "feat(chart): singleton Binance WS manager with refcount + backoff"
```

---

## Task 4 — React lifecycle hooks

**Files:**
- Create: `frontend/src/hooks/useBinanceTrade.ts`
- Create: `frontend/src/hooks/useBinanceKline.ts`
- Create: `frontend/src/hooks/useBinanceStatus.ts`

- [ ] **Step 1: Create `useBinanceTrade.ts`**

```typescript
import { useEffect, useState } from "react";
import { binanceWS, type TradeMsg } from "../lib/binanceWS";

export function useBinanceTrade(): TradeMsg | null {
  const [trade, setTrade] = useState<TradeMsg | null>(null);
  useEffect(() => {
    const unsub = binanceWS.subscribeTrade((m) => setTrade(m));
    return unsub;
  }, []);
  return trade;
}
```

- [ ] **Step 2: Create `useBinanceKline.ts`**

```typescript
import { useEffect } from "react";
import {
  binanceWS,
  type KlineMsg,
  type Timeframe,
} from "../lib/binanceWS";

export function useBinanceKline(
  timeframe: Timeframe,
  handler: (m: KlineMsg) => void,
): void {
  useEffect(() => {
    const unsub = binanceWS.subscribeKline(timeframe, handler);
    return unsub;
    // We deliberately depend on `timeframe` only — `handler` is held by ref-style
    // closure and re-subscribing on every render would churn the WS uselessly.
    // Callers must pass a stable callback (useCallback or module-level fn).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe]);
}
```

- [ ] **Step 3: Create `useBinanceStatus.ts`**

```typescript
import { useEffect, useState } from "react";
import { binanceWS } from "../lib/binanceWS";

export function useBinanceStatus(): boolean {
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    return binanceWS.subscribeStatus(setConnected);
  }, []);
  return connected;
}
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useBinanceTrade.ts \
        frontend/src/hooks/useBinanceKline.ts \
        frontend/src/hooks/useBinanceStatus.ts
git commit -m "feat(chart): React hooks for Binance trade/kline/status streams"
```

---

## Task 5 — `<PriceHero>`: live price ticker

**Files:**
- Modify: `frontend/src/components/PriceHero.tsx`

- [ ] **Step 1: Read the current file to find the price/% delta render block**

Run: `grep -n "data.price\|data.change24h" frontend/src/components/PriceHero.tsx`
Expected: lines around 51, 60, 83, 86, 89.

- [ ] **Step 2: Add the live-trade hook + derive a live `price` and `change24hPct`**

In `frontend/src/components/PriceHero.tsx`, find the line:

```tsx
export default function PriceHero() {
  const { data, error } = useMarketSummary();
```

Replace with:

```tsx
import { useBinanceTrade } from "../hooks/useBinanceTrade";

export default function PriceHero() {
  const { data, error } = useMarketSummary();
  const trade = useBinanceTrade();

  // Live price overrides the polled value as soon as a trade arrives.
  // 24h-ago anchor = (last polled price) - (last polled 24h abs change).
  const livePrice = trade ? trade.price : data?.price ?? null;
  const price24hAgo =
    data && Number.isFinite(data.change24hAbs) ? data.price - data.change24hAbs : null;
  const liveChangeAbs =
    livePrice !== null && price24hAgo !== null ? livePrice - price24hAgo : null;
  const liveChangePct =
    livePrice !== null && price24hAgo !== null && price24hAgo !== 0
      ? (liveChangeAbs! / price24hAgo) * 100
      : data?.change24hPct ?? null;
```

(Note: the `import` line goes at the top of the file with the other imports — not nested inside the function.)

- [ ] **Step 3: Wire `livePrice` / `liveChangePct` into the existing render**

Find the block:

```tsx
const up = (data?.change24hPct ?? 0) >= 0;
```

Replace with:

```tsx
const up = (liveChangePct ?? 0) >= 0;
```

Find the block (around line 82–90):

```tsx
{data ? (
  <>
    <div className="font-mono text-4xl lg:text-5xl font-semibold tabular-nums tracking-tight">
      {formatUsdFull(data.price)}
    </div>
    <div className={"font-mono text-base font-semibold " + color}>
      {arrow} {formatPct(data.change24hPct)}
      <span className="text-slate-500 font-normal ml-2">
        ({up ? "+" : ""}
        {formatUsdFull(data.change24hAbs)})
      </span>
    </div>
  </>
) : error ? (
```

Replace with:

```tsx
{data && livePrice !== null && liveChangePct !== null && liveChangeAbs !== null ? (
  <>
    <div className="font-mono text-4xl lg:text-5xl font-semibold tabular-nums tracking-tight">
      {formatUsdFull(livePrice)}
    </div>
    <div className={"font-mono text-base font-semibold " + color}>
      {arrow} {formatPct(liveChangePct)}
      <span className="text-slate-500 font-normal ml-2">
        ({up ? "+" : ""}
        {formatUsdFull(liveChangeAbs)})
      </span>
    </div>
  </>
) : error ? (
```

Also find the `rangePct` calculation (around line 56):

```tsx
const rangePct =
    data && data.high24h > data.low24h
      ? Math.max(
          0,
          Math.min(100, ((data.price - data.low24h) / (data.high24h - data.low24h)) * 100),
        )
      : 50;
```

Replace `data.price` with `(livePrice ?? data.price)`:

```tsx
const rangePct =
    data && data.high24h > data.low24h && livePrice !== null
      ? Math.max(
          0,
          Math.min(100, ((livePrice - data.low24h) / (data.high24h - data.low24h)) * 100),
        )
      : 50;
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PriceHero.tsx
git commit -m "feat(chart): PriceHero ticks live from Binance @trade stream"
```

---

## Task 6 — `<PriceChart>`: drop polling, stream in place, reconnect re-bootstrap

**Files:**
- Modify: `frontend/src/components/PriceChart.tsx`

- [ ] **Step 1: Update imports**

At the top of `frontend/src/components/PriceChart.tsx`, ALONGSIDE the existing imports add:

```tsx
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { binanceWS } from "../lib/binanceWS";
import { useBinanceStatus } from "../hooks/useBinanceStatus";
```

Also import `useEffect` if not already imported (it is — line 2).

- [ ] **Step 2: Drop `refetchInterval`; add `queryClient` + status hook**

Inside the `PriceChart` function, find:

```tsx
  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    refetchInterval: 30_000,
  });
```

Replace with:

```tsx
  const queryClient = useQueryClient();
  const wsConnected = useBinanceStatus();

  const { data, isLoading, error } = useQuery({
    queryKey: ["candles", timeframe],
    queryFn: () => fetchCandles(timeframe, 500),
    // No refetchInterval — the live WS handles freshness. We re-fetch only
    // on timeframe change (queryKey change) and on WS reconnect.
    refetchOnWindowFocus: false,
  });
```

- [ ] **Step 3: Subscribe to live kline ticks**

Add this `useEffect` after the existing data-loading effect (the one ending around line 198, after `setHover(...)`):

```tsx
  // Live-tick the last candle in place. Lightweight Charts' series.update()
  // recognises matching `time` as the last bar and updates without flicker.
  const handleTick = useCallback((m: { openTime: number; open: number; high: number; low: number; close: number; volume: number; closed: boolean }) => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !volumeSeries) return;
    const t = m.openTime as UTCTimestamp;
    candleSeries.update({ time: t, open: m.open, high: m.high, low: m.low, close: m.close });
    volumeSeries.update({
      time: t,
      value: m.volume,
      color: m.close >= m.open ? "rgba(25,195,125,0.45)" : "rgba(255,92,98,0.45)",
    });
    // When a bar closes, also update the local candleMap so the hover legend
    // sees the sealed values.
    if (m.closed) {
      candleMapRef.current.set(m.openTime, {
        time: m.openTime,
        open: m.open,
        high: m.high,
        low: m.low,
        close: m.close,
        volume: m.volume,
      });
    }
  }, []);

  useEffect(() => {
    return binanceWS.subscribeKline(timeframe, handleTick);
  }, [timeframe, handleTick]);
```

- [ ] **Step 4: Re-bootstrap on WS reconnect**

Add another `useEffect` after the kline subscription:

```tsx
  // After a WS reconnect, refetch historical bars so any gap during the
  // disconnect is filled. The Redis cache (60s) on the backend keeps this
  // cheap.
  useEffect(() => {
    return binanceWS.onReconnect(() => {
      queryClient.invalidateQueries({ queryKey: ["candles", timeframe] });
    });
  }, [timeframe, queryClient]);
```

- [ ] **Step 5: Render the disconnected badge**

Find the existing `<Card>` element at the bottom. The `subtitle` prop currently is:

```tsx
      subtitle={
        isLoading
          ? "loading…"
          : error
            ? "chart unavailable"
            : `${data?.candles.length ?? 0} ${timeframe} candles · Binance`
      }
```

Replace with:

```tsx
      subtitle={
        isLoading
          ? "loading…"
          : error
            ? "chart unavailable"
            : !wsConnected
              ? `${data?.candles.length ?? 0} ${timeframe} candles · live disconnected — retrying`
              : `${data?.candles.length ?? 0} ${timeframe} candles · Binance live`
      }
```

- [ ] **Step 6: Build**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/PriceChart.tsx
git commit -m "feat(chart): live kline streaming via Binance WS, in-place series.update()"
```

---

## Task 7 — Manual smoke test + CLAUDE.md note

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Restart the local stack**

Run from the repo root:

```bash
make down && make up
```

Wait ~10s for containers to settle. (Migrations run on api startup; nothing new to migrate for this feature.)

- [ ] **Step 2: Smoke test in the browser**

Open `http://localhost:5173`, log in. Then verify each of the following — if any fail, STOP and debug:

- [ ] **Big number ticks live.** The price-hero number should visibly tick within ~1s of page load and continue ticking ~5×/sec during liquid hours. The `▲ x.yz%` chip should also tick (slower, since it's % of a slowly-changing 24h base).
- [ ] **Last candle grows in place.** The most recent candle's wick should visibly extend during a price move. No flicker. Zoom in tightly with the scroll wheel — your zoom level must NOT reset on each tick.
- [ ] **Timeframe switch is fast.** Click 1m → 5m → 1h → 1d. Each switch should paint within ~500 ms perceived latency. The chart should NOT show a long blank period.
- [ ] **Reconnect path works.** In Chrome DevTools → Network → set "Offline" for ~10s, then back to "Online". You should see the chart subtitle change to "live disconnected — retrying" then back to "Binance live", and the chart should re-bootstrap (any closed bars during the disconnect window appear).
- [ ] **Backgrounded-tab recovery.** Open another tab and leave the dashboard tab inactive for >6min. Return to it. The big number should resume ticking within a second.
- [ ] **Pan/zoom is preserved.** Pan the chart back 50 bars. Wait for several live ticks. Your scroll position must NOT jump.

- [ ] **Step 3: Note the change in CLAUDE.md**

Edit `CLAUDE.md`. Find the line `**v2 complete.**` (around line 82). Append AFTER it:

```markdown

## UI polish

- Live chart ✅ Direct browser-to-Binance WebSocket (combined `@trade` + `@kline_<tf>` streams) drives the price-hero ticker and in-place candle updates via `series.update()`; backend wraps `/api/price/candles` in a 60s Redis cache for the bootstrap path. Spec: `docs/superpowers/specs/2026-05-01-live-chart-ws-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(chart): note live-chart shipping under UI polish"
```

---

## Self-review

**Spec coverage:**
- Goal / UX expectations: covered by Tasks 5–7 (PriceHero live, PriceChart live, smoke checklist).
- Architecture (single combined-stream WS): Task 3.
- Module surface (`subscribeTrade`/`subscribeKline`/`subscribeStatus`/`onReconnect`): Task 3.
- Hooks: Task 4.
- `<PriceChart>` uses `series.update()`, drops polling, re-bootstraps on reconnect: Task 6.
- `<PriceHero>` uses live trades, derives 24h % from existing baseline: Task 5.
- Backend: Redis cache wrapping `/api/price/candles` (Task 2), test (Task 2).
- Reconnection / gap handling: Tasks 3 + 6 step 4.
- Configuration: no env vars; constants in `binanceWS.ts` (Task 3).
- Risks / known limits: addressed via reconnect logic + visibility-restore handling (Task 3); manual smoke covers the failure paths (Task 7).
- Out of scope (multi-symbol, ws relay, LocalStorage zoom): explicitly skipped.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:**
- `Timeframe`, `TradeMsg`, `KlineMsg` exported from `lib/binanceWS.ts` and consumed by hooks (Task 4) + chart (Task 6) — names match.
- `binanceWS.subscribeKline(tf, handler)` signature: same shape in declaration (Task 3) and usage (Task 6). The `handler` is wrapped in `useCallback` with a stable identity so `useEffect` doesn't re-subscribe needlessly.
- `KlineMsg.openTime` is unix seconds, used as `UTCTimestamp` in Task 6's `update()` call — consistent (Lightweight Charts accepts seconds-as-number).
- `useBinanceStatus()` returns `boolean` in Task 4, consumed in Task 6 step 5 as `wsConnected` — consistent.
- `cached_json_get` / `cached_json_set` (Task 1) imported by `price.py` (Task 2) — consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-live-chart-ws.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
