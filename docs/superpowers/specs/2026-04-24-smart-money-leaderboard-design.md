# Smart-Money Leaderboard — Design

**Date:** 2026-04-24
**Status:** Draft (awaiting review)
**Phase:** v2 (follows `v2-derivatives` ✅, `v2-order-flow` ✅)
**Parent spec:** `2026-04-23-eth-analytics-dashboard-design.md`

## Goal

Rank the top ETH traders on mainnet DEXes by **realized USD PnL on WETH trades over a 30-day window**, and surface that ranking as a dashboard panel. Answers: "which wallets have been good at timing their ETH trades lately?"

## Non-Goals

- Multi-token PnL (e.g. per-ERC20 cost basis). WETH only.
- L2 coverage (Arbitrum, Base, Optimism). Mainnet only.
- CEX activity. On-chain DEX only.
- Predictive "smart money" signal or alerting. Descriptive board only.
- Per-wallet drill-down (trade list view). Deferred.
- User-configurable window length. Fixed 30d for v1.

## Scope Decisions

| Decision | Value | Rationale |
|---|---|---|
| Window | 30 days | Standard "recent performance" horizon; matches how traders talk about PnL |
| Leaderboard size | Top 50 | Enough to scroll, small payload, fits one screen |
| Candidate pool | Top 500 by 30d WETH volume | Balances coverage vs Dune credit cost; acknowledged bias below |
| PnL method | FIFO on realized round-trips | Standard convention; unrealized shown separately |
| Pre-window inventory | Skip sells without matching in-window buys | Honest, simple, documented |
| Asset coverage | WETH ↔ anything (not just WETH↔stables) | `dex.trades.amount_usd` is reliable for WETH regardless of counterparty |
| Router/aggregator filter | Exclude `labels.addresses` where category ∈ {`dex_aggregator`, `dex_router`} | Otherwise 1inch etc. dominate the #1 slot |
| Refresh cadence | Daily, 03:00 UTC | Low-traffic hour, leaderboards don't need sub-day freshness |
| Storage | Snapshot per run (one row per wallet per run) | Enables historical queries without extra cost |

**Known bias:** candidate pool is filtered by volume first, then re-ranked by PnL. A high-PnL low-volume wallet outside the top 500 by volume will be missed. Mitigation: a 500-wallet pool is wide enough that this is rare; if it matters later, expand the pool.

## Architecture

```
[arq cron, daily 03:00 UTC] ──▶ leaderboard_sync.refresh_leaderboard()
                                    │
                                    │ 1. Execute Dune query
                                    ▼
                               Dune dex.trades
                                    │
                                    │ 2. DataFrame of ~50K trade rows
                                    │    (500 wallets × ~100 trades each)
                                    ▼
                            pnl_engine.compute_realized_pnl()
                              (pure Python, per-wallet FIFO)
                                    │
                                    │ 3. List of 50 ranked WalletPnL records
                                    ▼
                         Postgres smart_money_leaderboard
                              (snapshot, one run_id per refresh)
                                    │
                                    ▼
                     GET /api/leaderboard/smart-money
                                    │
                                    ▼
                     Dashboard panel (SmartMoneyLeaderboard)
```

### Module layout

New files mirror the existing flow-sync pattern:

- `backend/dune/smart_money_leaderboard.sql` — parameter-free Dune query returning raw trade rows for 500 candidate wallets
- `backend/app/services/pnl_engine.py` — pure FIFO engine, no I/O
- `backend/app/services/leaderboard_sync.py` — orchestration: Dune call → engine → DB persistence
- `backend/app/workers/leaderboard_jobs.py` — arq cron wiring, mirrors `flow_jobs.py`
- `backend/app/api/leaderboard.py` — read endpoint
- `backend/alembic/versions/<rev>_smart_money_leaderboard.py` — schema migration
- `frontend/src/components/SmartMoneyLeaderboard.tsx` — dashboard panel
- `backend/tests/test_pnl_engine.py` — unit tests (pure, no DB/Dune)
- `backend/tests/test_leaderboard_sync.py` — integration test, Dune mocked, real Postgres
- `backend/tests/test_api_leaderboard.py` — endpoint test

**Boundary rationale:** the FIFO engine is the only place with logic that can be subtly wrong. Isolating it as a pure function means the interesting code is fully testable without touching the network or DB. Everything else is plumbing that follows established project patterns.

## Dune Query

`backend/dune/smart_money_leaderboard.sql`. Two CTEs — one scan, candidate filter, then project the rows Python needs.

```sql
-- 30d top-PnL leaderboard candidate feed.
-- Returns raw WETH trade rows for the top 500 wallets by 30d WETH volume,
-- so the backend can compute per-wallet FIFO realized PnL.
WITH router_exclusions (address) AS (
  VALUES
    (0x1111111254EEB25477B68fb85Ed929f73A960582),  -- 1inch v5
    (0x6131B5fae19EA4f9D964eAc0408E4408b66337b5)   -- KyberSwap
    -- ...curated list, maintained inline; see prose below
),
windowed_trades AS (
  SELECT
    tx_from AS trader,
    block_time,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN 'buy'
      ELSE 'sell'
    END AS side,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN token_bought_amount
      ELSE token_sold_amount
    END AS weth_amount,
    amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    AND block_date >= current_date - interval '30' day
    AND block_time > now() - interval '30' day
    AND (token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
      OR token_sold_address   = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2)
    AND amount_usd IS NOT NULL AND amount_usd > 0
    AND tx_from NOT IN (SELECT address FROM router_exclusions)
),
candidates AS (
  SELECT trader
  FROM windowed_trades
  GROUP BY trader
  ORDER BY SUM(amount_usd) DESC
  LIMIT 500
)
SELECT
  t.trader,
  t.block_time,
  t.side,
  t.weth_amount,
  t.amount_usd,
  l.name AS label
FROM windowed_trades t
JOIN candidates c USING (trader)
LEFT JOIN labels.addresses l
  ON l.address = t.trader AND l.blockchain = 'ethereum'
ORDER BY t.trader, t.block_time;
```

**Router exclusion:** `router_exclusions` is an inline VALUES CTE listing aggregator/router EOAs compiled from `labels.addresses` where category ∈ {`dex_aggregator`, `dex_router`}. Maintained directly in the SQL file; if it drifts, the worst case is a router address ranks highly and gets added on the next edit. The choice to hard-code vs. JOIN on `labels.addresses` is deliberate — labels may be incomplete, and we want the exclusion list under our control.

**`tx_from` over `taker`:** `tx_from` is the EOA signer; `taker` is often the router contract address.

**Partition pruning:** both `block_date` and `block_time` predicates are set so DuneSQL skips irrelevant daily partitions. Same pattern as `order_flow.sql`.

**Payload size:** ~500 wallets × ~100 avg trades × ~80 bytes/row ≈ 4 MB. One-shot, fits in memory trivially.

## FIFO Engine

`backend/app/services/pnl_engine.py` — pure function, no I/O.

```python
from dataclasses import dataclass
from decimal import Decimal
from collections import deque
from typing import Iterable

@dataclass(frozen=True)
class WalletPnL:
    wallet: str              # lowercase 0x-hex
    label: str | None
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal | None   # None if no open position at window end
    win_rate: Decimal | None             # None if no closed round-trips
    trade_count: int
    volume_usd: Decimal
    weth_bought: Decimal
    weth_sold: Decimal

def compute_realized_pnl(
    rows: list[dict],                    # raw Dune rows, sorted by (trader, block_time)
    window_end_eth_price: Decimal,       # for unrealized mark
) -> list[WalletPnL]:
    ...
```

### Per-wallet algorithm

1. Walk trades in time order. Maintain `lots: deque[(weth_amount, usd_cost)]`.
2. On `buy`: append `(weth_amount, amount_usd)` to `lots`.
3. On `sell`:
   - `sell_price = amount_usd / weth_amount`
   - `weth_to_close = weth_amount`
   - While `weth_to_close > 0` and `lots` non-empty:
     - Pop front lot. Let `consumed = min(lot.weth, weth_to_close)`.
     - `cost_basis = lot.usd_cost * (consumed / lot.weth)`
     - `proceeds = sell_price * consumed`
     - `realized_pnl += proceeds - cost_basis`
     - If `lot.weth > consumed`, push `(lot.weth - consumed, lot.usd_cost - cost_basis)` back to front.
     - `weth_to_close -= consumed`
   - Any remaining `weth_to_close` → skip silently (pre-window inventory).
   - **Win/loss counting:** a sell is only counted toward `win_rate` if it closed at least some WETH against at least one lot. A sell that hit an empty `lots` deque and was entirely skipped does not count as a win or a loss. Of the counted sells: `realized_pnl > 0` is a win, `<= 0` is a loss. `win_rate = wins / (wins + losses)`; `None` if `wins + losses == 0`.
4. End of wallet: leftover lots = open position. `unrealized = (window_end_eth_price - avg_lot_price) * leftover_weth` where `avg_lot_price = sum(lot.usd_cost) / sum(lot.weth)`. If no leftover, `unrealized = None`.

### Metric definitions

- `trade_count` — count of trade rows observed for the wallet in the window. Buys + sells, including skipped-sell rows. Measures activity, not closed round-trips.
- `volume_usd` — sum of `amount_usd` across all the wallet's trade rows in the window.
- `weth_bought` / `weth_sold` — gross, not net; summed across all buys / all sells.

### Precision

Everything in `Decimal`. Inputs arrive as strings or floats from Dune; convert at the boundary with `Decimal(str(x))` per field on row ingest. Never do `Decimal + float`.

### Ranking

Sort candidates descending by `realized_pnl_usd`. Take top 50. Assign `rank` 1..50.

### window_end_eth_price

Fetched from the existing price service (`price_sync` populates `prices` table). Use the last 1h candle close at or before `snapshot_at`. If unavailable, set `unrealized_pnl_usd = None` for all entries rather than fail the refresh.

## Database Schema

New Alembic migration.

```sql
CREATE TABLE smart_money_leaderboard (
  id                 BIGSERIAL PRIMARY KEY,
  run_id             UUID NOT NULL,
  snapshot_at        TIMESTAMPTZ NOT NULL,
  window_days        SMALLINT NOT NULL,
  rank               SMALLINT NOT NULL,
  wallet_address     VARCHAR(42) NOT NULL,
  label              TEXT,
  realized_pnl_usd   NUMERIC(20, 2) NOT NULL,
  unrealized_pnl_usd NUMERIC(20, 2),
  win_rate           NUMERIC(5, 4),
  trade_count        INTEGER NOT NULL,
  volume_usd         NUMERIC(24, 2) NOT NULL,
  weth_bought        NUMERIC(36, 18) NOT NULL,
  weth_sold          NUMERIC(36, 18) NOT NULL
);

CREATE INDEX ix_leaderboard_latest
  ON smart_money_leaderboard (window_days, snapshot_at DESC, rank);
```

### Notes

- `wallet_address VARCHAR(42)` stores the lowercase hex `0x…` form, matching the existing `transfers` table convention.
- `run_id` groups one refresh atomically. The read endpoint joins on the latest `run_id` so partial writes during a refresh can never be observed.
- `NUMERIC` everywhere — no `DOUBLE PRECISION`. PnL to cents, WETH amounts to 18 decimals.
- `unrealized_pnl_usd` nullable: `NULL` means "no open position at window end" (meaningfully different from `0`).
- `win_rate` nullable: `NULL` means "no closed round-trips in window" (e.g. buy-only wallet that accidentally made the candidate pool).
- `label` denormalized onto the row. Cheap, and Dune labels change slowly.
- No retention policy in v1. ~18K rows/year. Add pruning later if it ever matters.

**Not stored in v1:** individual trades. Per-wallet drill-down is deferred.

## API

### Endpoint

`GET /api/leaderboard/smart-money`

**Query params:**
- `window_days` (int, default 30) — only `30` supported in v1; parameter reserved for future 7d addition
- `limit` (int, default 50, max 50) — cap at stored leaderboard size

**Response:**
```json
{
  "snapshot_at": "2026-04-24T03:00:12Z",
  "window_days": 30,
  "entries": [
    {
      "rank": 1,
      "wallet": "0xabc...def",
      "label": "Jump Trading",
      "realized_pnl_usd": "1843221.50",
      "unrealized_pnl_usd": "420018.00",
      "win_rate": 0.7143,
      "trade_count": 42,
      "volume_usd": "18400000.00",
      "weth_bought": "5821.234567890123456789",
      "weth_sold": "5210.100000000000000000"
    }
  ]
}
```

**Semantics:**
- Returns the most recent completed snapshot (`run_id` with max `snapshot_at`).
- Empty `entries: []` when no snapshot exists (first-run state) — matches existing panel conventions.
- Decimal fields serialized as strings to preserve precision; `win_rate` as a number (0..1, nullable).

**Caching:** Redis-cached for 5 minutes. Data refreshes daily, so TTL ≪ refresh interval is fine.

## Frontend

**Component:** `frontend/src/components/SmartMoneyLeaderboard.tsx`

**Layout:** single-panel table in the existing dashboard grid. Columns:
- **#** — rank
- **Wallet** — truncated `0x1234…abcd` in monospace, click to open Etherscan, copy button, label badge if present
- **Realized PnL** — USD, colored green/red, monospace, thousands-separators
- **Unrealized** — USD, same formatting, em-dash if null
- **Win rate** — percentage + small horizontal bar; em-dash if null
- **Trades** — integer
- **Volume** — USD, compact (`$18.4M`)

**Interaction:**
- TanStack Query with `refetchInterval: 5 * 60 * 1000` (5 min).
- Clicking a wallet opens Etherscan in a new tab.
- Stale-snapshot banner if `snapshot_at > 36h` ago.
- Empty state: "No leaderboard snapshot yet. Refreshes daily at 03:00 UTC."
- Wrapped in existing `ErrorBoundary`.

**Not in v1:** sortable columns, search, drill-down drawer, historical "was top-10 yesterday?" indicator.

## Error Handling

| Condition | Behavior |
|---|---|
| Dune execute timeout / failure | arq job fails, retries next cycle. No partial DB write. |
| Dune returns empty rows | Log warning, skip persistence. Previous snapshot remains; stale banner will eventually trigger. |
| Unknown trade side in result (neither token_bought nor token_sold is WETH) | Defensive: skip row, increment warning counter. Should be unreachable given the WHERE clause. |
| Wallet with only sells (pre-window inventory) | Produces `realized_pnl = 0`, `win_rate = 0` or `NULL`, won't crack top 50 normally. Not an error. |
| `window_end_eth_price` unavailable | Set `unrealized_pnl_usd = NULL` for all rows. Snapshot still persists. |
| `run_id` collision | Impossible (UUID4). Not handled. |
| Endpoint called with no snapshots in DB | Return `{"snapshot_at": null, "window_days": 30, "entries": []}`. |

**Transactional boundary:** the full refresh (all 50 rows) writes in one transaction. Either all rows for a `run_id` land or none do.

## Testing

- **`backend/tests/test_pnl_engine.py`** (pure unit tests, no DB or Dune):
  - Single buy + single sell, profit
  - Single buy + single sell, loss
  - Partial close (sell < open position)
  - Multiple lots, FIFO ordering
  - Sell without prior buy in window (skip behavior)
  - Buy-only wallet (no realized PnL, win_rate = None)
  - Sell-only wallet (realized = 0, trades counted)
  - Flipper: many tiny round-trips, verify `win_rate` arithmetic
  - Decimal precision: 18-decimal WETH amounts, no float contamination
  - Open position at end → `unrealized_pnl_usd` computed correctly

- **`backend/tests/test_leaderboard_sync.py`** (integration, Dune mocked):
  - Fixture CSV → engine → Postgres. Assert one `run_id`, 50 rows, correct `rank` ordering.
  - Dune returns empty → no DB write, previous snapshot intact.
  - Dune raises → no DB write, exception propagates.

- **`backend/tests/test_api_leaderboard.py`**:
  - Seed two snapshots → endpoint returns only the latest.
  - Seed zero snapshots → returns empty entries with `snapshot_at: null`.
  - `limit` param clamps correctly.

- **Frontend:** one vitest component test for `SmartMoneyLeaderboard` with mocked fetch covering populated, empty, and stale states.

## Observability

- Per-refresh log line: `{run_id, candidate_count, leaderboard_count, dune_execution_ms, top1_wallet, top1_pnl_usd, total_duration_ms}`.
- `/api/health` gains a `smart_money` entry with `snapshot_at` and lag, same shape as existing sources.
- Topbar data-lag dropdown picks this up automatically once `/api/health` exposes it.

## Configuration

New env var:

- `DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD` — Dune query ID for the leaderboard query. When unset, the sync job logs and skips (matches existing flow-sync conventions; panel shows "no data yet").

No new secrets.

## Rollout

1. Ship behind the same "unset query ID = no-op" pattern as other Dune-backed features. Safe to deploy even before the Dune query is registered.
2. Register the Dune query, set the env var, run one manual refresh via an arq trigger (pattern from `flow_jobs.py`).
3. Verify the snapshot, unblock the daily cron.
4. Update CLAUDE.md milestone status: `v2-smart-money-leaderboard ✅`.

## Open Questions

None blocking v1.

## Future Work (explicitly deferred)

- 7-day window toggle (trivial once schema's `window_days` column is in place).
- Per-wallet trade drill-down drawer (adds `smart_money_trades` table).
- Historical position tracking ("top-10 streak"), sparkline of cumulative PnL.
- Candidate-pool widening if missed-high-PnL-low-volume wallets become a complaint.
- L2 extension (Base/Arbitrum/Optimism) — same query shape, additional `blockchain` values.
- LIFO option / wash-sale-aware variants.
