# DeFi Protocol TVL — Design

**Status:** approved 2026-05-02
**Track:** v3 — DeFi & staking layer (sub-project C; A=Beacon Flows shipped, B=LST Market Share shipped)
**Related specs:**
- `2026-05-02-eth-staking-flows-design.md`
- `2026-05-02-lst-market-share-design.md`

## Goal

Answer the operator's question "how much ETH / USDC / USDT / DAI / GHO / USDe is locked in Aave / Sky / Morpho / Compound / Spark / EigenLayer / Pendle / Lido right now?" with a single panel that shows **per-protocol absolute TVL on Ethereum mainnet, broken down by asset**.

Today the dashboard surfaces *flows* (transfers, mints, burns, supply Δ). It does not surface *stocks* (current locked balances). This is the missing piece.

## Non-goals

- **Per-protocol flow events** (deposit/withdraw line-by-line) — stick to current snapshot. A future panel can layer on `lending.supply` event flows; this PR is only the stock view.
- **L2 TVL** — Ethereum mainnet only. L2-bridged TVL is a separate panel concept.
- **DEX LP TVL** (Uniswap pools, Balancer pools) — possible but messier; defer. v1 covers lending + staking + restaking.
- **Realtime updates** — TVL doesn't move fast enough to need realtime; hourly cron is plenty.
- **Self-derived TVL via on-chain reads** — DefiLlama already aggregates aToken / cToken / morphoVault totalSupply across protocols; rebuilding that is wasteful for this user.

## Data source

**DefiLlama public API** (`https://api.llama.fi`, no auth required, generous free tier). Specifically:

1. `GET /protocol/{slug}` returns the protocol's full breakdown including `chainTvls.Ethereum.tokensInUsd` (daily timeseries of per-asset TVL on Ethereum mainnet) and `chainTvls.Ethereum.tokens` (per-asset native units).
2. We sample the **latest** entry from each timeseries on each cron tick.

Rate limits: ~300 req/5min unauthenticated. We hit ~10 protocols/cron × 24 ticks/day = 240 calls/day. Well within budget.

## Protocols tracked (v1, 10 entries)

| Display name | DefiLlama slug | Why it's here |
|---|---|---|
| Aave v3 | `aave-v3` | Largest lending market on mainnet |
| Sky (Lending) | `sky-lending` | Rebranded MakerDAO; backs DAI + USDS |
| Morpho | `morpho` | Fastest-growing lending aggregator, $18B+ supplied 30d |
| Compound v3 | `compound-v3` | Newer Compound; isolated markets |
| Compound v2 | `compound-v2` | Legacy Compound; still has TVL |
| Spark | `spark` | MakerDAO-aligned lending, sDAI yield |
| Lido | `lido` | stETH issuance backbone; ~30% of staked ETH |
| EigenLayer | `eigenlayer` | Restaking layer; LST + native ETH locked |
| Pendle | `pendle` | Yield trading; major sUSDe / sUSDS holder |
| Uniswap v3 | `uniswap-v3` | Largest DEX; LP TVL is meaningful for stables |

This list lives in a hand-maintained Python tuple `DEFI_PROTOCOLS` mirroring the LST registry pattern. Adding a new protocol = appending one row.

## Architecture

```
hourly cron (arq, minute=17)
   │
   ▼
DefiLlama GET /protocol/{slug} × 10  (httpx async, 5 concurrent)
   │
   ▼
parse chainTvls.Ethereum.tokensInUsd[-1]  (latest daily snapshot)
   │
   ▼
┌─────────────────────────────────────────────┐
│  protocol_tvl table                          │
│  (ts_bucket, protocol, asset, tvl_usd)       │
└─────────────────────────────────────────────┘
   │
   ▼
GET /api/defi/tvl  (latest snapshot, all protocols)
   │
   ▼
DefiTvlPanel — protocol picker + horizontal bar by asset
```

Each unit has one job. Failure isolation: any single protocol failing doesn't halt the rest (per-call try/except, log + continue).

## Schema

New table `protocol_tvl`:

```sql
ts_bucket  TIMESTAMPTZ NOT NULL,
protocol   VARCHAR(32) NOT NULL,
asset      VARCHAR(20) NOT NULL,
tvl_usd    NUMERIC(38, 6) NOT NULL,
PRIMARY KEY (ts_bucket, protocol, asset)
```

Composite PK makes upsert idempotent across cron retries.

## Endpoints

`GET /api/defi/tvl?hours=N`:
```json
{
  "points": [
    { "ts_bucket": "2026-05-02T15:00:00Z", "protocol": "aave-v3", "asset": "USDC", "tvl_usd": 4_320_000_000.0 },
    ...
  ]
}
```

`GET /api/defi/tvl/latest`:
```json
{
  "ts_bucket": "2026-05-02T15:00:00Z",
  "protocols": [
    { "protocol": "aave-v3", "total_usd": 14_000_000_000.0,
      "assets": [
        {"asset": "USDC", "tvl_usd": 4_320_000_000.0},
        {"asset": "USDT", "tvl_usd": 3_100_000_000.0},
        ...
      ]
    },
    ...
  ]
}
```

The `/latest` shape is what the panel actually consumes — it pre-aggregates so the frontend doesn't have to re-derive.

## Frontend panel

`DefiTvlPanel.tsx`. Layout:

```
┌─ DeFi TVL · Ethereum mainnet ────────────[protocol▼]┐
│ Aave v3 · $14.0B locked                              │  ← total tile
│                                                       │
│ USDC  ████████████████████ $4.3B  31%               │
│ USDT  ███████████████░░░░░ $3.1B  22%               │
│ DAI   █████████░░░░░░░░░░░ $2.1B  15%               │
│ ETH   ████░░░░░░░░░░░░░░░░ $1.0B   7%               │
│ wstETH ███░░░░░░░░░░░░░░░░ $0.7B   5%               │
│ ...                                                   │
└───────────────────────────────────────────────────────┘
```

- **Protocol picker** (top right): shadcn `<Select>` with 10 options, defaults to "Aave v3".
- **Total tile**: protocol's total TVL.
- **Per-asset rows**: horizontal bar (% of protocol total) + USD label. Sorted desc by TVL_usd. Truncate to top 12 assets per protocol; "+N more" affordance for the long tail.
- **Empty state**: "no data yet — first hourly sync pending" until the cron has run once.
- **Container queries**: at `@xs`, hide the bar fill and percent column; just `ASSET — $X.YB`.

## What changes

### Backend

1. **alembic 0011** — `protocol_tvl` table.
2. **`backend/app/core/models.py`** — `ProtocolTvl` ORM class.
3. **New `backend/app/services/defi_protocols.py`** — `DEFI_PROTOCOLS` tuple (display name + DefiLlama slug + optional alias for short label).
4. **New `backend/app/clients/defillama.py`** — thin httpx async client. One method: `fetch_protocol_tvl(slug) -> dict[str, float]` returning `{asset_symbol: tvl_usd}` for Ethereum mainnet, latest snapshot. Returns `{}` on any error (caller skips that protocol's row).
5. **New `backend/app/services/defi_tvl_sync.py`** — `upsert_protocol_tvl` mirroring the existing flow_sync pattern.
6. **New `backend/app/workers/defi_jobs.py`** — `sync_defi_tvl` arq task. Iterates `DEFI_PROTOCOLS`, calls DefiLlama for each (with 5-way concurrency via `asyncio.gather`), upserts at top-of-hour bucket.
7. **`backend/app/workers/arq_settings.py`** — register `sync_defi_tvl` cron at minute 17.
8. **`backend/app/api/schemas.py`** — `DefiTvlPoint`, `DefiTvlAsset`, `DefiTvlProtocolSnapshot`, `DefiTvlLatestResponse`.
9. **New `backend/app/api/defi.py`** — router with `/defi/tvl` (raw points) and `/defi/tvl/latest` (pre-aggregated).
10. **`backend/app/main.py`** — register the router under auth.
11. **Tests:** `test_defi_tvl_sync.py` (3: round-trip, idempotent, multi-protocol same bucket). `test_defi_jobs.py` (3: mocked DefiLlama response decode, partial failure handling, end-to-end with mock httpx). `test_defillama_client.py` (3: success parse, network error returns empty, missing Ethereum chainTvls returns empty).

### Frontend

1. **`frontend/src/api.ts`** — `DefiTvlAsset`, `DefiTvlProtocolSnapshot`, `DefiTvlLatestResponse` types + `fetchDefiTvlLatest()`.
2. **New `frontend/src/components/DefiTvlPanel.tsx`** — protocol picker (shadcn Select), total tile, horizontal-bar per-asset rows.
3. **`frontend/src/lib/panelRegistry.ts`** — register under "Onchain" page, `defaultWidth: 2`.

### Config

- No new env vars (DefiLlama is unauthenticated public API).
- `CLAUDE.md` — add `v3-defi-tvl` line under v3-staking + v3-lst.

## Risks / known limits

- **DefiLlama uptime / API drift.** Public API; rare outages. The cron logs and skips per-protocol failures; the panel renders the most recent stored snapshot with a "stale since" badge if no fresh data has landed.
- **Asset symbol normalization.** DefiLlama uses its own symbol convention which mostly matches ours (USDC, USDT, DAI, GHO, ETH/WETH/stETH/wstETH). Edge cases (rebrands, wrapped variants) get raw passthrough; if the operator notices "USDB" or similar weirdness on a panel, we add a small alias map in `defi_protocols.py`.
- **TVL is a ~24h-old snapshot.** DefiLlama's `tokensInUsd` is daily granularity. Acceptable — TVL doesn't move fast and the operator is making weekly-scale decisions, not minute-scale.
- **DefiLlama doesn't break out per-asset for some L2 / niche protocols.** That's fine — our protocol list is curated to ten that DO have clean Ethereum mainnet token breakdowns. Future additions get vetted on add.
- **Rate limit / etiquette.** 240 calls/day across 10 slugs is ~10 calls/hour. Free tier handles this comfortably. We add `User-Agent: etherscope/3 (https://etherscope.duckdns.org)` so DefiLlama can identify the traffic.

## Tests

- **Unit:** see "Tests:" under Backend above. 9 new tests total.
- **Integration:** existing arq integration test gets one extra registered task; verify it doesn't break.
- **Frontend:** `npm run build` is the gate. Manual visual check after deploy.

## Future work

- **Per-asset flow overlay** — overlay the 30d net deposit (from Dune `lending.supply`) on top of the absolute TVL bar to show "where's the supply growing fastest."
- **Borrow side / utilization** — same shape using `lending.borrow`. Useful for "how much of supplied USDC is being borrowed in Aave."
- **DEX LP TVL** — Uniswap v3 + Balancer + Curve. Different shape (per-pool, not per-asset). Separate panel.
- **TVL trend sparkline** — per-protocol historical TVL chart, swap out the current snapshot for a 30d line. Cheap addition once we're storing rows hourly.
