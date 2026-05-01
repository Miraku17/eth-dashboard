# Live Chart via Direct Binance WebSocket — Design

**Status:** approved 2026-05-01
**Track:** UI polish — perf pass on the price chart + hero ticker
**Related specs:**
- `2026-04-23-eth-analytics-dashboard-design.md` (parent)

## Goal

Make the ETH price chart and the price-hero ticker feel like CoinMarketCap.
Every visible tick of price should appear in the UI within ~100 ms of
Binance reporting it. Switching timeframes should feel instant. Zoom and
pan must survive live updates. The fix is architectural: stop polling and
re-rendering the whole series, start streaming and updating in place.

## Non-goals

- Multi-symbol or multi-exchange support. ETH/USDT on Binance only.
- Persisting live ticks server-side. The existing kline sync worker
  continues to write 1m / 5m / 1h / etc. closed bars to `price_candles`
  every minute — that's our historical record. Live ticks are a
  presentation concern, not a data-integrity concern.
- A new backend WebSocket service relaying Binance to clients. The browser
  connects to Binance directly. (See "Why direct, not relay" below.)
- Multi-tab synchronisation. Each open tab opens its own WS — Binance is
  generous with connection limits at our scale.
- Storing the user's zoom/pan state across reloads. Out of scope; tackle
  later if asked.

## UX

1. **Initial paint:** open the dashboard. The chart shows ~500 historical
   candles within ~100 ms (Redis-cached). Within ~1 s the WS has
   connected and the latest candle starts ticking.
2. **Steady state:** the price-hero big number flickers ~5×/sec as
   trades arrive. The current candle's body and wick visibly extend as
   the kline message updates the bar in place. User's zoom and pan are
   never disturbed.
3. **Timeframe switch:** click 1h → 1d. The historical fetch fires
   (cached), the WS sends `UNSUBSCRIBE ethusdt@kline_1h` then
   `SUBSCRIBE ethusdt@kline_1d` on the same socket, the chart re-paints
   with the new series within ~300 ms.
4. **Disconnect:** if the WS drops (laptop sleep, network blip), a small
   "live disconnected — retrying" badge appears next to the chart title.
   On reconnect (typically <30 s) the badge disappears and the chart
   re-bootstraps historical bars to backfill any gap.

## Why direct browser → Binance, not via our backend

A backend WS relay (browser ↔ our `/ws/price` ↔ Binance) was the
honourable runner-up. It was rejected because:

- We're a single-user tool. The relay's main payoff — fan-out to many
  clients — doesn't apply.
- Every hop adds 30–80 ms latency. The whole point of this work is to
  feel snappy.
- A long-running WS daemon on the VPS is one more thing to babysit.
- Binance's public market WS doesn't require an API key, has no quota at
  one-connection-per-tab scale, and works through corporate firewalls
  via standard 443/wss.

The direct path means the chart keeps ticking even if our VPS goes down
(only the historical bootstrap breaks). That's a good failure mode for a
solo trading tool.

## Architecture

```
Browser
  ├─ /api/price/candles?timeframe=X   (one-shot bootstrap, Redis-cached)
  │     └─ TanStack Query (no refetchInterval)
  │
  └─ wss://stream.binance.com:9443/stream?streams=
         ethusdt@trade /ethusdt@kline_<tf>
        │
        ├─ trade events  → liveStream { price, ts } → <PriceHero>
        └─ kline events  → series.update({...})    → <PriceChart>
```

One WebSocket connection per tab, multiplexed via Binance's combined-
stream URL. The connection is owned by a singleton manager
(`lib/binanceWS.ts`); both `<PriceHero>` and `<PriceChart>` subscribe
through it.

### Component layout

```
frontend/src/
  lib/
    binanceWS.ts                  # NEW — singleton WS manager
  hooks/
    useBinanceTrade.ts            # NEW — React wrapper, returns {price, ts} | null
    useBinanceKline.ts            # NEW — React wrapper, calls back on every kline tick
  components/
    PriceChart.tsx                # MODIFIED — drops refetchInterval, subscribes to kline
    PriceHero.tsx                 # MODIFIED — subscribes to trade
backend/app/
  api/price.py                    # MODIFIED — wrap candles query in a 60s Redis cache
```

No new dependencies. `lightweight-charts` already supports
`series.update(bar)` for in-place last-bar updates.

## Frontend module: `lib/binanceWS.ts`

A small (~120 LOC) singleton with this public surface:

```typescript
type TradeMsg  = { price: number; ts: number };
type KlineMsg  = {
  openTime: number;          // unix seconds, the bar's start
  open: number; high: number; low: number; close: number;
  volume: number;
  closed: boolean;            // true on the message that seals the bar
};

export const binanceWS = {
  subscribeTrade(handler: (msg: TradeMsg) => void): () => void;
  subscribeKline(
    timeframe: Timeframe,
    handler: (msg: KlineMsg) => void,
  ): () => void;
  subscribeStatus(handler: (connected: boolean) => void): () => void;
  onReconnect(handler: () => void): () => void;
};
```

Internal behaviour:

- **Reference counting.** Open the underlying `WebSocket` on the first
  subscribe; close it after the last unsubscribe.
- **Combined stream URL.** Built from the union of currently-subscribed
  streams. Adding/removing a stream while the socket is alive uses
  Binance's in-band `{method: "SUBSCRIBE"|"UNSUBSCRIBE", params: [...]}`
  control messages — no socket churn.
- **Reconnect.** On socket close other than a clean unmount, retry with
  exponential backoff: 1 s, 2 s, 4 s, 8 s, 16 s, capped at 30 s. Reset
  the backoff on a successful open.
- **`onReconnect` event.** Fired after each successful re-open of the
  socket (excluding the very first open). Consumers use this to
  re-bootstrap historical data and fill any gap.
- **Visibility recovery.** Listen for `document.visibilitychange`; if
  the page returns from hidden after >5 min, force-close the socket so
  the reconnect path runs. Browsers sometimes pause WS in backgrounded
  tabs; this avoids serving stale data on tab return.
- **No silent failures.** A 5-attempt streak with no successful open
  flips an internal `connected: false` state, exposed via a third
  subscribe primitive (`subscribeStatus`) so the UI can show the
  "disconnected" badge.

The manager is exported as a module-level singleton (`export const
binanceWS = createManager()`). Tests are not required for this file —
no vitest infra is set up (per Task 11/12 of wallet-clustering); we
validate via `npm run build` + manual smoke test.

## Frontend: `<PriceChart>` changes

Drop these from the existing implementation:

- `refetchInterval: 30_000` on the `useQuery`.
- The `setData` rebuild of both series on every poll.

Add:

- After the initial `setData` of historical candles, subscribe via
  `useBinanceKline(timeframe, handleTick)`.
- `handleTick` calls
  `candleSeries.update({time, open, high, low, close})` and
  `volumeSeries.update({time, value, color})`. Lightweight Charts
  recognises that `time` matches the last bar and performs an in-place
  update — no flicker, zoom preserved.
- When the kline message has `closed: true`, also write the bar into
  the local `candleMapRef` map so the hover legend shows the right
  values for that completed bar.
- `useEffect` cleanup unsubscribes on unmount or timeframe change.
- Subscribe to `binanceWS.onReconnect(...)` and on each fire, manually
  trigger a re-bootstrap via TanStack Query's `queryClient.invalidateQueries(['candles', tf])`.

## Frontend: `<PriceHero>` changes

- Subscribe to `useBinanceTrade()`. Returns `{price, ts}` updated on
  every trade message (~5×/sec for ETHUSDT).
- The big-number price renders the live value, falling back to
  `data.price` from `useMarketSummary()` until the first trade arrives.
- `change24hPct` is computed from `(livePrice / data.price24hAgo - 1)
  * 100` so the `▲ x.yz%` chip ticks alongside the price.
- Existing `useMarketSummary()` continues to drive 24h high/low,
  volume, and the sparkline — those don't benefit from sub-second
  updates and re-fetching them every 30 s is already cheap.

## Backend: candles Redis cache

Wrap the existing query body with a Redis read-through:

- Key: `candles:{symbol}:{timeframe}:{limit}`
- TTL: 60 seconds.
- On miss: run the existing SQLAlchemy query, serialize the response
  payload to JSON, write to Redis, return.
- On hit: deserialize, return.

Why 60 s: the live chart no longer relies on this endpoint for
freshness — the WS does. The endpoint exists for the bootstrap fetch
on page load and for tab focus. 60 s is a sweet spot between
"effectively cached" and "still picks up new bars from the kline
sync worker shortly after they land."

The kline sync worker (`backend/app/workers/price_jobs.py::sync_price_latest`)
runs every minute. We don't actively invalidate the cache when it
writes new bars — the 60 s TTL handles it implicitly. Stale-by-up-to-
60-seconds for the bootstrap path is fine; the WS overlays freshness
as soon as it connects.

## Reconnection and gap handling

A WS reconnect can leave a gap: bars closed during the disconnect window
won't appear in the live stream. To handle:

- On reconnect, the manager fires `onReconnect`.
- `<PriceChart>` invalidates its TanStack Query and re-fetches
  `/api/price/candles`. The Redis cache may be ≤60 s stale; the kline
  worker fills the cache on its next run. Worst case the user sees a
  ~60 s gap that fills on the next refetch.
- If a *short* disconnect happens (under one bar's duration), nothing
  is lost — the next kline message includes the in-progress bar.

We deliberately don't try to backfill via Binance's REST `/api/v3/klines`
from the browser; that's another integration to maintain and the
existing path is sufficient.

## Configuration

No new env vars. Two constants in `binanceWS.ts`:

```typescript
const BINANCE_WS_BASE = "wss://stream.binance.com:9443";
const SYMBOL = "ethusdt";
```

Both are hard-coded — multi-symbol support is non-goal. If/when v3
introduces other assets, surface these as props and accept a symbol
argument throughout the manager.

## Risks and known limits

- **Browser WS limit per origin.** Binance permits 5 concurrent
  connections per origin per IP. We open one. Plenty of headroom.
- **Binance message volume.** ETHUSDT trades arrive at ~5–20/sec
  during liquid hours. Each trade message is ~200 bytes. ~10 KB/sec
  network down — negligible. Hero render at this rate is cheap because
  React re-renders only the price text node.
- **Browser tab in background.** Browsers may throttle or pause WS in
  backgrounded tabs. We force a reconnect on visibility-restore so the
  UI doesn't show stale data when the user comes back.
- **Binance outage.** Live updates stop; chart shows a "disconnected"
  badge; historical bootstrap still works (different domain). Realistic
  recovery time is whatever Binance's recovery time is.
- **Cache stampede on cold start.** First request to
  `/api/price/candles` after worker boot fills the cache; subsequent
  requests within 60 s hit it. Stampede potential is low (one user).
  Not worth a lock.

## Testing

Backend:
- One new test in `tests/test_price_api.py`: hit `/api/price/candles`
  twice, assert the second call doesn't re-execute the SQL query
  (mock `session.execute` and assert call count). Verifies the cache
  is wired without testing Redis directly.

Frontend:
- No automated tests (no vitest infra). Manual smoke checklist in the
  implementation plan covers the cases that matter:
  - Big number ticks visibly within ~1 s of page load
  - Last candle wick extends in real time
  - Timeframe switch is <500 ms perceived
  - Pulling network for 10 s and reconnecting shows the disconnected
    badge then recovers and re-bootstraps
  - Pan/zoom is preserved across live ticks
  - Switching browser tabs for 1 min and returning recovers cleanly

## Implementation milestones

Approximate ordering for the writing-plans pass to refine:

1. Backend: Redis cache wrapping `/api/price/candles` + test.
2. New `lib/binanceWS.ts` manager (singleton, refcount, reconnect).
3. New hooks `useBinanceTrade`, `useBinanceKline`.
4. `<PriceHero>` subscribes to live trade stream.
5. `<PriceChart>` drops `refetchInterval`, subscribes to live kline,
   handles reconnect re-bootstrap.
6. Disconnected-badge UI element on the chart card.
7. Smoke-test pass per the checklist above.
8. Docs note in CLAUDE.md (one line — not a milestone block, just an
   acknowledgement under "## v2 status" or a new "## UI polish" sub-heading).

## Open questions

None at design time.

## Future work

- **Multi-symbol live charts** (when v3 introduces, for example, an
  LST page comparing stETH / rETH).
- **Persist user's zoom/pan** across reloads (LocalStorage).
- **Aggregate ticker** (CoinGecko-style cross-exchange average) — needs
  multiple WS sources, out of scope for solo tool.
