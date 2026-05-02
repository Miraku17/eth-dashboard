# DEX Pool TVL — Design

**Status:** approved 2026-05-02
**Track:** v3 — DeFi & staking layer (sub-project D; A=Beacon, B=LST, C=DeFi-protocol-TVL all shipped)

## Goal

Surface **top DEX pools by locked TVL on Ethereum mainnet** so the operator can answer "how much USDC / USDT / WETH / DAI / WBTC is locked in Uniswap (and Curve, Balancer) right now, and which pairs are the deepest." The lending-style DeFi TVL panel (PR #29) deliberately omitted DEXes because DefiLlama's `/protocol/{slug}` endpoint doesn't expose per-asset breakdowns for AMMs. This panel uses a different DefiLlama endpoint (`/yields/pools`) that does — per-pool, per-pair TVL across 2,200+ Ethereum pools.

## Non-goals

- Per-token aggregation across pools (the existing DeFi TVL panel covers lending; DEX LP isn't lending).
- Realtime updates — pool TVL moves slowly; hourly is fine.
- Per-LP wallet positions — out of scope.
- Custom pools / non-major DEXes — v1 limits to Uniswap V2/V3 + Curve + Balancer.

## Data source

**DefiLlama `/yields/pools`** (https://yields.llama.fi/pools, no auth). Single GET returns ~10k pools across all chains/protocols. We filter to:
- `chain == "Ethereum"`
- `project` ∈ {`uniswap-v3`, `uniswap-v2`, `curve-dex`, `balancer-v2`}
- top 100 by `tvlUsd` after filter

Each row has: `pool` (address), `chain`, `project`, `symbol` (e.g., "USDC-WETH"), `tvlUsd`. We persist a hourly snapshot of the top 100.

## Schema

New table `dex_pool_tvl`:

```sql
ts_bucket   TIMESTAMPTZ NOT NULL,
pool_id     VARCHAR(80) NOT NULL,   -- DefiLlama pool address/UUID
dex         VARCHAR(32) NOT NULL,   -- uniswap-v3 / uniswap-v2 / curve-dex / balancer-v2
symbol      VARCHAR(80) NOT NULL,   -- "USDC-WETH" or longer LP names
tvl_usd     NUMERIC(38, 6) NOT NULL,
PRIMARY KEY (ts_bucket, pool_id)
```

## Architecture

```
hourly cron (arq, minute=27)
   │
   ▼
GET /yields/pools  (single ~5MB JSON)
   │
   ▼
filter Ethereum + 4 DEX projects, sort by tvlUsd desc, top 100
   │
   ▼
┌────────────────────────────┐
│  dex_pool_tvl table        │
└────────────────────────────┘
   │
   ▼
GET /api/defi/dex-pools/latest
   │
   ▼
DexPoolTvlPanel — DEX picker + top-20 pool table
```

Reuses the existing `DefiLlamaClient` (extends with one new method `fetch_yield_pools()`). One new arq cron at minute 27 (so it doesn't collide with `sync_defi_tvl` at 17 or `sync_lst_supply` at 7). Endpoint added to the existing `/defi` router.

## Endpoint

`GET /api/defi/dex-pools/latest`:

```json
{
  "ts_bucket": "2026-05-02T16:00:00Z",
  "pools": [
    {"dex": "uniswap-v3", "pool_id": "0x...", "symbol": "USDC-WETH", "tvl_usd": 312_000_000.0},
    {"dex": "uniswap-v2", "pool_id": "0x...", "symbol": "WISE-WETH", "tvl_usd": 129_000_000.0},
    ...
  ]
}
```

Pre-sorted desc by tvl_usd. Auth-gated like all dashboard data.

## Frontend panel

`DexPoolTvlPanel.tsx`. Layout:

```
┌─ DEX pool TVL · Ethereum ───────────────[All DEXes ▼]┐
│ Top 20 pools by TVL · DefiLlama yields                 │
│                                                         │
│ Uniswap v3 · USDC-WETH         $312.4M ████████████    │
│ Uniswap v2 · WISE-WETH         $129.0M ██████          │
│ Uniswap v3 · WETH-USDT         $102.0M █████           │
│ Uniswap v3 · WBTC-WETH          $82.2M ████            │
│ Curve     · 3pool                $64.0M ███            │
│ Uniswap v3 · USDC-USDT 0.01%     $47.6M ███            │
│ ...                                                     │
└─────────────────────────────────────────────────────────┘
```

DEX picker: `All DEXes / Uniswap v3 / Uniswap v2 / Curve / Balancer`. Bar width is per-row pct of max in current view. Pool rows show DEX name + pair symbol + TVL + bar.

shadcn `SimpleSelect` for the picker (matches the DeFi TVL panel pattern).

## What changes

### Backend
1. **alembic 0013** — `dex_pool_tvl` table.
2. **`models.py`** — `DexPoolTvl` ORM class.
3. **Extend `clients/defillama.py`** — add `fetch_yield_pools()` method.
4. **New `services/dex_pool_sync.py`** — `upsert_dex_pool_tvl` (Postgres upsert, mirroring `defi_tvl_sync`).
5. **New `workers/dex_pool_jobs.py`** — `sync_dex_pool_tvl` arq task. Calls DefiLlama once, filters/sorts, writes top 100.
6. **`workers/arq_settings.py`** — register at minute 27.
7. **`api/schemas.py`** — `DexPoolTvlPoint`, `DexPoolTvlLatestResponse`.
8. **Extend `api/defi.py`** — add `GET /defi/dex-pools/latest`.
9. **Tests:** 3 sync tests + 3 jobs tests + 2 client tests.

### Frontend
1. **`api.ts`** — types + `fetchDexPoolTvlLatest()`.
2. **New `DexPoolTvlPanel.tsx`** — DEX picker + top-N pool list with horizontal bars.
3. **`panelRegistry.ts`** — register under "Onchain" page, `defaultWidth: 2`.

### Config
- No new env vars.
- `CLAUDE.md` — `v3-dex-pool-tvl` line.

## Risks / known limits

- **DefiLlama `/yields/pools` is large (~5MB)** — single call, hourly = 24/day. Well within DefiLlama's tolerance.
- **Pool symbol parsing**: DefiLlama returns LP names like "USDC-WETH" or longer ("3pool" for Curve, multi-asset Balancer pools). We pass through as-is.
- **Top-100 cutoff**: pools below #100 don't get tracked. Acceptable — long tail is by definition small.
- **Curve / Balancer pools may include LP token names that aren't immediately readable** ("3pool", "TriCryptoUSDC", "BAL-WETH-WBTC-USDC"). Display as-is for v1.

## Tests

- `test_defillama_client.py` — extended with 2 new tests (yield pools success + empty).
- `test_dex_pool_sync.py` — 3 tests (upsert, idempotent, multi-pool).
- `test_dex_pool_jobs.py` — 3 tests (filter Ethereum + 4 projects, top-100 cutoff, partial-failure handling).
- Frontend: `npm run build` is the gate.

## Future work

- **Per-token aggregation**: sum TVL across all pools containing USDC, USDT, WETH, etc. Cheap derivative once we have per-pool data.
- **Pool fee tier breakdown** for Uniswap V3 (currently the symbol field collapses fee tier into "USDC-WETH" without 0.05% / 0.3% labels — need to parse `pool` field for the fee).
- **Sushiswap / PancakeSwap** if the operator's portfolio shifts.
- **Curve gauge weights** + reward APRs.
