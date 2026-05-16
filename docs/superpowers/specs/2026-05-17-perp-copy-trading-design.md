# Perp Copy-Trading — Design

**Date:** 2026-05-17
**Status:** Approved (brainstorming complete; implementation pending)
**Scope:** GMX V2 perps on Arbitrum (v1). Mainnet spot and other perp venues out of scope.

## Motivation

The operator does not want to trade actively but wants to identify consistently profitable on-chain perp traders, surface their stats (win rate, sample size, avg hold time, side split), and receive sub-second Telegram alerts when a vetted wallet opens or closes a position — fast enough to manually mirror trades whose average hold time is ~15 minutes.

The foundation already exists: `onchain_perp_event` captures every GMX V2 open / increase / close / decrease / liquidation with originating EOA, market, side, size, and leverage. This spec adds the scoring, watchlist, alert hop, and UI on top.

## Non-goals

- **Auto-execution.** Alert payload may include a deep link to GMX; the operator copies manually.
- **Spot copy-trading.** Mainnet DEX swaps are noisier (rotations / hedges are indistinguishable from directional bets) and gas costs make small mirrors uneconomic. The existing `wallet_score` + smart-money surfaces already cover spot.
- **Other perp venues.** Vertex, Aevo, dYdX, Hyperliquid deferred. The scoring kernel is decoupled from the GMX decoder, so adding a venue later is a registry + event-source addition, not a redesign.
- **Backtesting.** v1 ranks by realized 90d performance only.

## Components

Three new components on top of existing data.

### 1. `score_perp_wallets` daily cron

- Runs at **04:23 UTC** (slotted between existing 04:13 spot `score_wallets` and 04:33 cluster purge).
- Reads `onchain_perp_event` rows from the last 90 days.
- Per (wallet, market, side), runs the FIFO matcher in `app/services/perp_scoring.py` (a new module — separate from `wallet_scoring.py` because the inputs and per-trip metrics differ).
- Upserts one row per wallet into `perp_wallet_score`. Latest-only; previous row replaced on each run.

### 2. `perp_watchlist` table + CRUD endpoints

- Operator-curated set of wallets to alert on. One row per wallet.
- Per-wallet `min_notional_usd` (default **$25,000**) gates noise from scale-ins.
- Optional `label` (nickname) for the Telegram payload.
- CRUD via the API; mutations publish a Redis pub/sub message that the arbitrum listener consumes to refresh its cached set.

### 3. Real-time alert dispatcher (inside `arbitrum_listener`)

- After persisting a decoded GMX event, the listener checks:
  1. `event.account ∈ perp_watchlist` (Redis-cached `SET`, 30s safety TTL, primary invalidation via pub/sub)
  2. `event.kind ∈ {open, close, increase, decrease, liquidation}`
  3. `event.size_usd ≥ watch.min_notional_usd`
- If all true, enqueues an alert payload onto the existing alerts delivery worker — same queue, same retry / formatting / mute logic the rules engine uses.
- Dedup on `(tx_hash, log_index)` happens upstream at the persist step, so one trade = one alert.

**Why not a new alert rule type?** Watchlist alerts fire on *every* trade from a watched wallet — they aren't conditional on per-rule params. Reusing the rules engine would require one rule per watched wallet plus a `wallet_address` param, which is awkward UX and duplicates the watchlist concept. Treating the watchlist itself as the rule source keeps the model clean.

## Schema

```sql
CREATE TABLE perp_wallet_score (
  wallet             BYTEA PRIMARY KEY,
  trades_90d         INT NOT NULL,            -- closed round-trips, not raw events
  win_rate_90d       NUMERIC(5,4) NOT NULL,
  win_rate_long_90d  NUMERIC(5,4),            -- NULL when zero long round-trips
  win_rate_short_90d NUMERIC(5,4),            -- NULL when zero short round-trips
  realized_pnl_90d   NUMERIC(20,2) NOT NULL,
  avg_hold_secs      INT NOT NULL,
  avg_position_usd   NUMERIC(20,2) NOT NULL,
  avg_leverage       NUMERIC(6,2) NOT NULL,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX perp_wallet_score_leaderboard_idx
  ON perp_wallet_score (realized_pnl_90d DESC)
  WHERE trades_90d >= 30
    AND win_rate_90d >= 0.6
    AND realized_pnl_90d >= 10000;

CREATE TABLE perp_watchlist (
  wallet            BYTEA PRIMARY KEY,
  label             TEXT,
  min_notional_usd  NUMERIC(20,2) NOT NULL DEFAULT 25000,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Latest-only `perp_wallet_score` stays small (a few thousand rows) so retuning thresholds means dropping + recreating the partial index — cheap.

## FIFO scoring kernel

Per wallet over the last 90d:

1. Group events by `(market, side)`. Long and short inventories are independent — they do not net.
2. Replay events in `ts` order:
   - `open` and `increase` push a lot `(size_usd, entry_price, leverage, open_ts)` onto the inventory.
   - `close` and `decrease` pop FIFO from the head, realizing PnL on the consumed quantity. Partial closes leave the remainder in the head lot; hold time for the consumed half is `event.ts − head.open_ts`.
   - `liquidation` events close at the liquidation price.
3. Per closed round-trip, record `(notional_usd, leverage, pnl, hold_secs)`.
4. Aggregate per wallet:
   - `trades_90d` = round-trip count
   - `win_rate_90d` = `wins / trades_90d` (win = `pnl > 0`)
   - `win_rate_long_90d` / `win_rate_short_90d` = side split, NULL when the side has zero round-trips
   - `realized_pnl_90d` = Σ pnl
   - `avg_hold_secs`, `avg_position_usd`, `avg_leverage` = arithmetic means

**Leverage source:** `PositionIncrease` emits `sizeInUsd` and `collateralAmount`; leverage = `sizeInUsd / collateralUsd`. Already decoded.

**Orphan closes** (close with no inventory — wallet was already trading before the 90d window): skipped, not counted as wins or losses. Same convention as the spot scorer.

**Thresholds as named constants** in `app/services/perp_scoring.py`:

```python
LEADERBOARD_LOOKBACK_DAYS = 90
LEADERBOARD_MIN_TRADES = 30
LEADERBOARD_MIN_WIN_RATE = 0.60
LEADERBOARD_MIN_PNL_USD = 10_000
DEFAULT_WATCH_NOTIONAL_USD = 25_000
```

Frontend reads these via a small `/api/copy-trading/config` endpoint so the partial index, query, and UI never drift.

## Alert payload (Telegram)

```
🟢 OPEN  ETH-USD  LONG  $52,300  10x
Wallet: vitalik.eth (★ 78% win / 142 trades / avg 14m)
Tx: 0xab12…
GMX: <market link>
```

- Side emoji: 🟢 long open, 🔴 short open, ⚪ close (color of close determined by realized PnL: green profit / red loss).
- Wallet label: watchlist `label` if set → ENS reverse lookup (Redis-cached 1h) → truncated hex.
- Stat trio (`78% win / 142 trades / avg 14m`) reads from `perp_wallet_score` at alert time, so the operator sees the wallet's current form before copying.

**Failure modes:**
- Alerts worker down → dispatcher writes payload to Redis list `perp_alerts:pending`; worker drains on recovery.
- Telegram API outage → worker retries with backoff (existing behavior).
- Watchlist cache stale → 30s TTL forces refresh; pub/sub invalidation is the primary path.

## API

```
GET    /api/copy-trading/config
       → { lookback_days, min_trades, min_win_rate, min_pnl_usd, default_watch_notional_usd }

GET    /api/copy-trading/leaderboard
       ?lookback=90d&min_trades=30&min_win=0.6&min_pnl=10000&limit=100
       → list of perp_wallet_score rows + watchlist membership flag

GET    /api/copy-trading/wallets/{address}
       → stat header (8 metrics) + last 20 closed round-trips + hold-time histogram buckets
         (<5m / 5–15m / 15–60m / 1–24h / >1d)

GET    /api/copy-trading/watchlist             → list
POST   /api/copy-trading/watchlist             → { wallet, label?, min_notional_usd? }
PATCH  /api/copy-trading/watchlist/{address}   → label / min_notional_usd
DELETE /api/copy-trading/watchlist/{address}
```

All endpoints sit behind the existing session-auth gate. Mutations publish a Redis pub/sub message `perp_watchlist:invalidate` consumed by the arbitrum listener.

## UI — `/copy-trading` page

New top-level route, added to nav alongside Overview / Markets / Onchain / Mempool.

**Desktop layout — two-column:**

- **Left (2/3 width): Leaderboard**
  - Filter bar (lookback, min trades, min win %, min PnL — all default to spec constants from `/config`).
  - Table columns: rank, wallet (`<AddressLink>`), win %, long/short split, trades, PnL, avg hold, avg leverage, ⭐ add-to-watchlist button.
  - Row click opens the existing wallet drawer (single canonical wallet view across the app). Drawer gains a **"Perp performance"** tile that renders only when the address has a `perp_wallet_score` row.
- **Right (1/3 width): Watchlist**
  - Compact cards: label or truncated hex, side-split win rate, last alert timestamp.
  - `min_notional_usd` editable inline ($1k step).
  - ✕ button removes.
- **Below leaderboard, on row select: Wallet detail panel**
  - 8-stat header.
  - Last 20 closed round-trips (market, side, notional, PnL, hold, ts).
  - Hold-time histogram (Recharts bar, 5 buckets).
  - `[+ Add to watchlist]` button with inline min-notional input.

**Mobile:** sections stack (Leaderboard → Watchlist → detail-on-tap).

**No Overview companion panel** in v1. Watchlist alert firings appear in the existing AlertEvents panel because they flow through the same alerts engine.

## Where this fits in the existing architecture

- **Data source:** `onchain_perp_event` (v5-onchain-perps, shipped). Unchanged.
- **Realtime hop:** `app/realtime/arbitrum_listener.py` — adds the watchlist check after persist. Decoder unchanged.
- **New service:** `app/services/perp_scoring.py` (FIFO kernel + leaderboard query helpers). Pure compute; unit-testable.
- **New worker:** `score_perp_wallets` cron in `app/workers/arq_settings.py`.
- **New API router:** `app/api/copy_trading.py`.
- **New frontend route + page:** `frontend/src/pages/CopyTrading.tsx` and supporting components under `frontend/src/components/copy-trading/`.
- **Drawer extension:** `frontend/src/components/wallet-drawer/` gets a new "Perp performance" tile.

## Testing

- `app/services/perp_scoring.py` unit tests (mirror `wallet_scoring.py` test layout):
  - Profitable long round-trip with a single open and single close.
  - Losing short round-trip.
  - Partial close: 50% decrease realizes half PnL, leaves remainder.
  - Multiple opens (increase events) consumed FIFO by one close.
  - Orphan close (no inventory) is skipped, not negative.
  - Long-only wallet: `win_rate_short_90d` is NULL not 0.
  - Liquidation event closes at liquidation price.
- Integration test: end-to-end alert path with a fake GMX event hitting a wallet in `perp_watchlist`, asserting the alerts queue receives the formatted payload.
- API tests for leaderboard filter query (asserting partial index is used via `EXPLAIN`).

## Rollout

1. Schema migration (two new tables + partial index).
2. Ship `score_perp_wallets` cron and `perp_scoring.py` kernel + tests; let it run once daily for a week before the UI lands so the leaderboard is non-empty at launch.
3. Ship watchlist CRUD + arbitrum listener hop. No alerts fire until at least one wallet is in the watchlist.
4. Ship `/copy-trading` page and drawer tile.
5. Update CLAUDE.md status block with a new v5 sub-track entry.

## Operator-tunable knobs (post-launch)

After a week of live data, the operator may retune:

- `LEADERBOARD_MIN_TRADES` — if too few wallets qualify, drop to 20.
- `LEADERBOARD_MIN_WIN_RATE` — if leaderboard is empty, drop to 0.55.
- `LEADERBOARD_MIN_PNL_USD` — currency floor on noise.
- `DEFAULT_WATCH_NOTIONAL_USD` — per-watch override always wins.

Retuning means editing the constants and recreating the partial index. One migration, no schema churn.
