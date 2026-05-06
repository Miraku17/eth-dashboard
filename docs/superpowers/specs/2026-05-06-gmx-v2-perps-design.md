# GMX V2 On-Chain Perps — Design

**Date:** 2026-05-06
**Status:** Draft
**Track:** post-v4 backlog — first item ("on-chain perp positions / leverage / liquidations")
**Predecessors:** v2 derivatives panel (CEX OI + funding) + v2 liquidations panel (Binance forceOrder stream) — both already shipping; this design adds the **on-chain** counterpart.

## Goal

Surface real on-chain perpetual-futures activity — **opens, closes, leverage, and forced liquidations** — for the largest on-chain perp venue. Today the dashboard tracks CEX derivatives (Binance/Bybit/OKX/Deribit OI + funding) and Binance liquidations; it has no visibility into on-chain leverage, even though that's where increasingly meaningful flow lives.

v1 ships **GMX V2 only** on Arbitrum, with one new realtime listener pointed at an Arbitrum WS endpoint, one new table, and one new dashboard panel.

The work also lays the foundation that a future Mantle-network listener (next item in the backlog) will reuse — same connection scaffolding, swap the event-decoder registry.

## Non-goals

- **Other on-chain perp venues.** Vertex, Hyperliquid, Aevo, dYdX v4 all defer. The schema's `venue` column accommodates them without API change.
- **Order-book depth.** v1 reads execution events, not pending orders. No "size queued for liquidation at $X" gauge.
- **PnL recomputation.** GMX V2's `EventEmitter` already reports realized PnL on close events; we record it, not derive it.
- **Funding-fee accounting.** GMX has its own funding model; we record events as they fire and don't try to model accumulated funding per position. (CEX funding is already covered by the existing v2 derivatives panel — different shape, different venue.)
- **Real-time push to the browser.** Panel polls every 10s, same cadence as `LiquidationsPanel`.
- **Cross-chain position aggregation.** A single account's mainnet activity, GMX position, and Vertex position are not joined into one "this trader's book." Wallet drawer can do that later if the operator wants it.

## Why GMX V2 first

| Venue        | Why pick                                                                  | Why skip for v1                              |
|--------------|---------------------------------------------------------------------------|----------------------------------------------|
| **GMX V2**   | Largest on-chain perp by OI; simple EventEmitter; well-documented schema  | —                                            |
| Vertex       | High volume                                                                | Heavier event surface; needs a sequencer feed besides on-chain |
| Hyperliquid  | High volume                                                                | Bridge runs on Arbitrum but matching is off-chain — see backlog 🔴 entry; shelved by operator |
| dYdX v4      | Pure on-chain                                                              | Cosmos chain, separate stack — out of scope of "Arbitrum sibling listener" foundation |

GMX V2 also reuses the Arbitrum-listener scaffolding most cleanly for future expansion (Vertex is also Arbitrum, so adding it later is "extend the event-decoder registry" not "build another listener").

## Architecture

```
┌─────────────────────────────┐         ┌─────────────────────────────┐
│  realtime (mainnet)          │         │  arbitrum_realtime (NEW)    │
│  app/realtime/listener.py    │         │  app/realtime/arbitrum_     │
│  - newHeads (Geth WS)        │         │       listener.py           │
│  - newPendingTransactions    │         │  - eth_subscribe logs to    │
│  - decode whale ERC-20s      │         │    GMX V2 EventEmitter      │
│  - mint/burn aggregator      │         │  - decode EventLog{1,2}     │
│  - dex_swap aggregator       │         │  - resolve account → EOA    │
│  - …everything we have today │         │  - persist onchain_perp_    │
│                              │         │       event rows            │
└─────────────────────────────┘         └─────────────────────────────┘
            │                                       │
            └────────────── postgres ───────────────┘
                                │
                          api + workers
```

A new sibling Docker service `arbitrum_realtime`, structurally a clone of `realtime` but pointed at an Arbitrum WS endpoint, owning its own reconnect loop. Crashing or losing the Arbitrum endpoint cannot disrupt mainnet processing — same isolation principle that the Binance liquidation listener follows today.

## Arbitrum endpoint

v1 uses **Alchemy free tier** for Arbitrum. Operator already has an `ALCHEMY_API_KEY` for the mainnet fallback path; Alchemy serves Arbitrum WS at `wss://arb-mainnet.g.alchemy.com/v2/<key>` on the same key, no additional signup. Free tier limit is 300 CUs/sec — well above what `eth_subscribe logs` for one contract emits even at peak GMX volume (≤ ~1 event/sec).

New env vars:

```
ARBITRUM_WS_URL            # e.g. wss://arb-mainnet.g.alchemy.com/v2/<key>
                           # (or ws://172.17.0.1:8547 for a future self-hosted Nitro)
ARBITRUM_HTTP_URL          # https://arb-mainnet.g.alchemy.com/v2/<key>
                           # used for receipt → tx.from EOA lookups
```

If `ARBITRUM_WS_URL` is unset, the new listener container starts in "no-op" mode (logs a warning, sleeps) so the stack still boots cleanly in dev.

## GMX V2 contract surface

GMX V2 is event-driven through a single `EventEmitter` contract. All of `PositionIncrease`, `PositionDecrease`, `OrderCreated`, `OrderExecuted`, `OrderCancelled`, `LiquidationFee`, etc. fire from one address as `EventLog` / `EventLog1` / `EventLog2` topics, with the actual event name encoded as a string in the data payload alongside an `EventLogData` struct (addressItems, uintItems, intItems, boolItems, bytes32Items, bytesItems, stringItems — each a key/value-array pair).

Mainnet (Arbitrum) addresses we'll subscribe / call:

| Contract       | Address                                                                | Use                                                                 |
|----------------|------------------------------------------------------------------------|---------------------------------------------------------------------|
| EventEmitter   | `0xC8ee91A54287DB53897056e12D9819156D3822Fb`                            | the only `eth_subscribe logs` topic we need                         |
| Reader         | `0xf60becbba223EEA9495Da3f606753867eC10d139`                            | optional — used to enrich market metadata (token decimals, symbol)  |
| DataStore      | `0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8`                            | optional fallback for market lookups; v1 hardcodes the market list  |

Markets (v1, hand-curated; covers ~99% of GMX V2 OI):

```
ETH-USD, BTC-USD, SOL-USD, AVAX-USD, ARB-USD, LINK-USD, DOGE-USD, NEAR-USD
```

Stored as `market_token_address → display_symbol` in `app/realtime/gmx_v2_markets.py` — same shape as the mainnet `tokens.py` registry.

## Event decoding

The GMX V2 ABI for `EventLog2` (the most common variant we'll handle):

```solidity
event EventLog2(
    address msgSender,
    string eventName,
    string indexed eventNameHash,    // topics[1] = keccak256(eventName)
    bytes32 indexed topic1,          // topics[2] = e.g. keccak256(account)
    bytes32 indexed topic2,          // topics[3] = e.g. keccak256(market)
    EventLogData eventData
)
```

Decoder lives at `app/realtime/gmx_v2_decoder.py`. Pure function, unit-testable:

```python
def decode_gmx_event(log: dict) -> GmxEvent | None:
    """Return a GmxEvent if the log is a tracked event name (PositionIncrease,
    PositionDecrease, LiquidationFee), else None.

    The EventLogData struct is decoded with eth_abi.decode_abi against the
    EventLog2 tuple shape; we then pull out the items by key — sizeDeltaUsd,
    sizeInUsd, collateralAmount, executionPrice, basePnlUsd, etc.
    """
```

We only persist three event names in v1:

| Event name           | Maps to `event_kind`                                  | Why                                                           |
|----------------------|-------------------------------------------------------|---------------------------------------------------------------|
| `PositionIncrease`   | `open` (if `sizeInUsd before == 0`) else `increase`   | size & collateral & leverage all readable from the payload    |
| `PositionDecrease`   | `close` (if `sizeInUsd after == 0`) else `decrease`   | realized pnl in `basePnlUsd` field                             |
| `PositionDecrease` w/ `orderType == Liquidation` (uint key) | `liquidation`                  | distinguishes forced unwind from voluntary close              |

`OrderCreated` / `OrderExecuted` are skipped — they fire ahead of the position event and don't add information v1 cares about. We can revisit if order-book-depth becomes a goal.

## Schema

One new table. Shipped in a single Alembic migration.

```sql
CREATE TABLE onchain_perp_event (
  id              BIGSERIAL PRIMARY KEY,
  ts              TIMESTAMPTZ NOT NULL,
  venue           TEXT NOT NULL,                    -- "gmx_v2" in v1
  account         TEXT NOT NULL,                    -- lowercase 0x…
  market          TEXT NOT NULL,                    -- "ETH-USD", "BTC-USD", …
  event_kind      TEXT NOT NULL,                    -- open|increase|close|decrease|liquidation
  side            TEXT NOT NULL,                    -- long|short
  size_usd        NUMERIC(38, 6) NOT NULL,          -- size delta on this event (USD)
  size_after_usd  NUMERIC(38, 6) NOT NULL,          -- post-event remaining size (USD)
  collateral_usd  NUMERIC(38, 6) NOT NULL,          -- post-event collateral (USD)
  leverage        NUMERIC(12, 4) NOT NULL,          -- size_after_usd / collateral_usd, snapshot at event
  price_usd       NUMERIC(38, 6) NOT NULL,          -- execution / mark price
  pnl_usd         NUMERIC(38, 6),                   -- realized PnL on decrease/close/liq; NULL otherwise
  tx_hash         TEXT NOT NULL,
  log_index       INT NOT NULL,
  UNIQUE (tx_hash, log_index)
);

CREATE INDEX idx_perp_event_ts        ON onchain_perp_event (ts DESC);
CREATE INDEX idx_perp_event_account   ON onchain_perp_event (account, ts DESC);
CREATE INDEX idx_perp_event_kind_ts   ON onchain_perp_event (event_kind, ts DESC);
```

**Why one row per event instead of "current positions" + "history":**

GMX V2's "current positions" state lives in the contract; we'd be reconstructing it. By persisting events as they fire and reconstructing open positions on read with a windowed aggregation (`size_after_usd > 0` per `(account, market, side)`, latest event wins), we get:

- Auditable history (every change recorded)
- Trivial liquidation feed (`WHERE event_kind = 'liquidation'`)
- Open-positions view from a single GROUP BY in the API layer

The cost is the open-positions query is O(events in window). Index `(account, ts DESC)` keeps it cheap, and we cap "open positions" reconstruction at the last 30 days (positions held longer than that are vanishingly rare on GMX V2 given funding accrual).

## API

```
GET /api/perps/events?hours=24&kind=liquidation&min_size_usd=10000
→ {
    events: [
      {
        ts, venue, account, market, event_kind, side,
        size_usd, leverage, price_usd, pnl_usd, tx_hash
      },
      …
    ]
  }
```

```
GET /api/perps/summary?hours=24
→ {
    opens_count, closes_count, liquidations_count,
    total_long_liq_usd, total_short_liq_usd,
    biggest_liq: { account, market, size_usd, ts },
    open_long_size_usd, open_short_size_usd,    // current state, reconstructed
    long_short_skew                              // (long - short) / (long + short)
  }
```

```
GET /api/perps/largest-positions?limit=20
→ {
    positions: [
      { account, market, side, size_usd, collateral_usd, leverage, opened_at, last_event_at },
      …
    ]
  }
```

All three behind `AuthDep` like every other Etherscope route. Caches:

- `/api/perps/summary` — Redis 30s TTL, key `perps:summary:24h`
- `/api/perps/largest-positions` — Redis 60s TTL
- `/api/perps/events` — uncached (cheap with index, and panel re-renders on filter change)

## What changes

### Backend

1. **New service: `arbitrum_realtime`** in `docker-compose.yml` — same image as `realtime`, different command:
   ```yaml
   arbitrum_realtime:
     build: ./backend
     command: python -m app.realtime.arbitrum_listener
     env_file: .env
     depends_on: [postgres, redis]
   ```
2. **New `app/realtime/arbitrum_listener.py`** — WS subscribe to GMX EventEmitter logs, reconnect loop mirroring the existing mainnet listener. ~250 lines.
3. **New `app/realtime/gmx_v2_decoder.py`** — pure decode function over `EventLog2` payloads. Returns a `GmxEvent` dataclass. ~200 lines incl. ABI tuple.
4. **New `app/realtime/gmx_v2_markets.py`** — hardcoded market_token → symbol registry (8 markets in v1).
5. **New `app/realtime/perp_writer.py`** — batched `INSERT … ON CONFLICT (tx_hash, log_index) DO NOTHING` against `onchain_perp_event`. Writes every 5s in a background task to keep WS callbacks fast.
6. **EOA resolution** — GMX events report a `msgSender` which is often the GMX router, not the user's EOA. The listener fetches the tx receipt (cached in Redis 1h by tx_hash) and uses `tx.from` as the canonical `account`. One extra HTTP RPC per event; with caching, ≤1k uncached calls/day, well within Alchemy free.
7. **New Alembic migration** — adds `onchain_perp_event` table.
8. **New API router `app/api/perps.py`** — three endpoints above. ~120 lines.
9. **`app/api/schemas.py`** — `PerpEvent`, `PerpSummary`, `PerpPosition`, response models.
10. **`app/main.py`** — register the perps router under `AuthDep`.
11. **Tests:**
    - `test_gmx_v2_decoder.py` — fixtures pulled from real Arbiscan event payloads (3 events: increase, decrease, liquidation), assert decoded fields match.
    - `test_perp_writer.py` — round-trip a batch through the writer with a testcontainers Postgres.
    - `test_perps_api.py` — endpoint contract tests using a seeded DB.

### Frontend

1. **`api.ts`** — types + fetchers for the three endpoints. 10s refetch on summary, 30s on positions, click-to-load on events feed.
2. **New `OnchainPerpsPanel.tsx`** — three-tab panel (matches `AlertsPanel` shape):
   - **Recent Events** — chronological feed, filter by `kind` (open / close / liquidation) and `min size`, click row → wallet drawer (`AddressLink`).
   - **Liquidations** — 24h liq summary tiles (long-liq $, short-liq $, biggest, count), then a chronological liquidation feed below.
   - **Open Positions** — top 20 currently-open positions, sortable by size or leverage. Click → wallet drawer.
3. **`panelRegistry.ts`** — register on the **Markets** page. Default size L (3 cols).
4. **Reuse:** `<AddressLink>`, `<PanelShell>`, asset-color palette, formatters all carry over.

### Docs / config

- New `docs/arbitrum-setup.md` — one-page operator guide ("paste your Alchemy key, restart `arbitrum_realtime` service"). Mirrors the existing `docs/dune-setup.md` shape.
- `.env.example` — add `ARBITRUM_WS_URL`, `ARBITRUM_HTTP_URL`.
- `CLAUDE.md` — add `v5-onchain-perps` (or graduate the post-vacation backlog item) status block. Move the `🟡 on-chain perps` backlog entry to `✅`.

## Risks / known limits

- **GMX V2 EventEmitter ABI is non-trivial.** The `EventLogData` struct is dynamic — strings, bytes32 arrays, address arrays, mixed-type kv pairs. The decoder is the meaningful engineering risk. Mitigation: lock down with three real-payload fixtures from Arbiscan, plus property-based tests against the decoded `key→value` map. Decoder is a pure function, easy to TDD.
- **Account ≠ msgSender.** GMX routes through proxy contracts. Without the receipt-fetch step, every event would be tagged to the router address. Mitigation explicit in the design — fetch + cache `tx.from` per tx hash. If Alchemy free starts rate-limiting under heavy GMX volume, fall back to batching multiple receipts per request via `eth_getBlockReceipts`.
- **Arbitrum WS reliability.** Third-party WS endpoints disconnect on average every few hours. The mainnet listener already proves the reconnect-with-backoff pattern; the new listener reuses it verbatim.
- **Wallet drawer has no Arbitrum data today.** Clicking an account address opens the wallet drawer, but its 30d ETH balance chart, 7d net-flow, and ERC-20 holdings are all mainnet-only. v1 accepts this — the drawer still surfaces the cluster + last-15-whale-moves sections, which add context. A follow-on can extend the drawer with Arbitrum balances.
- **Self-trading / inventory bots can spam events.** A market-maker repositioning every block would dominate the feed. Mitigation: panel filters apply a default `min_size_usd = 10_000` so the feed shows only meaningful positions; the underlying table records everything for completeness.
- **Cold start.** First few hours after deploy show very few events (only what's fired since the listener came up). Backfill is **out of scope for v1** — pulling historical EventEmitter logs is straightforward (`eth_getLogs` with chunked block ranges) but adds a one-shot script + careful reorg handling. Future-work item; v1 ships forward-only.

## Future work

- **Backfill script.** One-off `python -m app.scripts.backfill_gmx_v2 --days 30` that pages through historical `eth_getLogs` and populates `onchain_perp_event`. Not blocking v1, but the operator will eventually want a 30d history view.
- **Wallet drawer Arbitrum extension.** Add Arbitrum WETH/USDC balance + GMX-position summary to the drawer alongside the existing mainnet sections.
- **Vertex extension.** Vertex is also Arbitrum and the listener scaffolding (WS, reconnect, writer) reuses verbatim. Adding it = decoder + market registry + extending the `venue` enum. ~1 day of work once GMX V2 is stable.
- **Hyperliquid signal.** The operator shelved this (CLAUDE.md). If revived, the right path is Arbitrum bridge-event tracking — fits the same listener.
- **GMX V2 OI gauge.** A per-market open-interest sparkline (long $ vs. short $ over time), reconstructed from the same event stream by hourly aggregation. Slots into the existing v2 derivatives panel as a fourth row.
- **Liquidation alerts.** Reuse the v1 alerts engine — "notify me when a single liquidation > $1M happens" or "notify me when 24h liquidation total > $50M". One new rule type, ~30 lines in `evaluate_alerts`.
- **Mantle DEX listener (next backlog item).** Reuses the chain-config abstraction this work introduces — swap RPC URL, swap event registry, point at Mantle DEX pools instead of GMX EventEmitter.

## Rollout checklist

1. Operator pastes `ARBITRUM_WS_URL` + `ARBITRUM_HTTP_URL` into prod `.env` (Alchemy key reused).
2. Deploy lands → Alembic creates `onchain_perp_event` → new `arbitrum_realtime` container starts subscribing.
3. Verify within 10 min: at least one row in `onchain_perp_event`, panel renders without errors.
4. After 24h: confirm liquidation count + sizes match GMX V2's own dashboard within rounding.
5. Move the `🟡 on-chain perps` backlog line to ✅ in CLAUDE.md, update milestone status block.
