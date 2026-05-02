# ETH Staking Flows — Design

**Status:** approved 2026-05-02
**Track:** v3 — DeFi & staking layer (sub-project A of two; sub-project B is a follow-up "LST market share" panel)
**Related specs:**
- `2026-04-23-eth-analytics-dashboard-design.md` (parent)

## Goal

Surface the most consequential post-merge ETH supply signal: **net ETH staked vs unstaked**. Today the dashboard tracks exchange flows, stablecoin flows, and DEX flows — but the beacon chain (the largest single sink/source of ETH on the network) is invisible. Add a `StakingFlowsPanel` that shows:

- Net ETH staked over the selected range (deposits − full validator exits)
- Both legs visible: deposits leg (green) + full-withdrawals leg (red)
- Partial withdrawals (validator rewards being skimmed) shown separately, smaller — they're income, not de-staking
- Headline tile: current active validator count (live, sub-minute fresh)

This is sub-project **A**. A follow-up PR (sub-project **B**) will add an `LstMarketSharePanel` showing stETH/wstETH/rETH/cbETH/sfrxETH/mETH `totalSupply` over time. B is deliberately deferred because it has a different shape (JSON-RPC reads, not Dune) and bundling them would create a 12-file PR with two infrastructure paths.

## Non-goals

- LST market share / per-protocol totalSupply — sub-project B
- Validator exit-queue length / queue clearance ETA — separate beacon-API endpoint, deferred
- Per-staking-pool deposit attribution surfaced in the UI (we capture the data — `entity` column — but v1 panel only shows aggregate; future PR can add a "Lido / Coinbase / Solo" stack)
- MEV / proposer rewards — derivative metric, not supply-side
- Realtime listener for deposit / withdrawal events — Dune already aggregates them and the data churns slowly enough that an 8h sync cadence is plenty

## Data source

**Dune spell `staking_ethereum.flows`** (verified via `searchTables` 2026-05-02). One table covers all three flow legs:

| Column | Type | Purpose |
|---|---|---|
| `block_time` | timestamp | bucket source |
| `amount_staked` | double | ETH deposited (validator created or topped up) |
| `amount_full_withdrawn` | double | ETH returned via validator exit |
| `amount_partial_withdrawn` | double | ETH skimmed as rewards (validator stays active) |
| `entity`, `sub_entity` | varchar | Lido / Coinbase / Rocket Pool / Kraken / Binance / Solo / etc. |
| `validator_index` | bigint | for distinct counts |
| `pubkey` | varbinary | validator pubkey |

Most rows have one of the three amount columns populated and the others = 0. We pivot into `(ts_bucket, kind, amount_eth, amount_usd)` rows where `kind ∈ {deposit, withdrawal_partial, withdrawal_full}`.

USD pricing: ETH price varies materially over 30d, so per-row USD is computed Dune-side using `prices.usd` (already a join we use in `order_flow.sql`). Falls back to current ETH price × eth_amount if the join is empty for a row.

## Live validator count

A separate, live signal: the current count of active validators. The beacon API has no dedicated count endpoint, so we call:

```
GET http://172.17.0.1:5052/eth/v1/beacon/states/head/validators?status=active_ongoing
```

…and use `len(data)`. The response is large (~1.5 MB at ~430k validators), but the call is localhost-to-localhost and cached 5 minutes in Redis (12 calls/hour worst case). Negligible cost.

If `BEACON_HTTP_URL` is unset (dev / cheap deploys), the validator-count tile hides; the deposit/withdrawal panel still renders from Dune.

## What changes

### Backend

1. **New file `backend/dune/staking_flows.sql`** — Dune query producing `(ts_bucket, kind, amount_eth, amount_usd)` rows over the last 30d. One query covers all three flow legs. Pricing via `prices.usd` join (`symbol='ETH'`, blockchain='ethereum') matched on hour-truncated minute.
2. **New alembic migration → table `staking_flows`**:
   ```
   ts_bucket TIMESTAMPTZ NOT NULL,
   kind TEXT NOT NULL CHECK (kind IN ('deposit','withdrawal_partial','withdrawal_full')),
   amount_eth NUMERIC(38, 18) NOT NULL,
   amount_usd NUMERIC(38, 6),
   PRIMARY KEY (ts_bucket, kind)
   ```
   PK on `(ts_bucket, kind)` makes upsert idempotent.
3. **Modify `backend/app/services/flow_sync.py`** — add `upsert_staking_flows`. Mirror `upsert_stablecoin_flows`.
4. **Modify `backend/app/workers/flow_jobs.py`** — add `("staking_flows", settings.dune_query_id_staking_flows, upsert_staking_flows)` to the `sync_dune_flows` job list. No new cron — same 8h cadence.
5. **New `backend/app/clients/beacon.py`** — minimal Lighthouse beacon-API client (one method: `active_validator_count() -> int`). 5-min Redis cache. Returns `None` on failure or when `BEACON_HTTP_URL` unset; callers degrade gracefully.
6. **New `backend/app/api/routes/staking.py`** — two endpoints:
   - `GET /api/staking/flows?hours=N` → `{ points: [{ts_bucket, kind, amount_eth, amount_usd}] }`
   - `GET /api/staking/summary` → `{ active_validator_count: int|null, total_eth_staked_30d: float, net_eth_staked_30d: float }`
7. **Modify `backend/app/core/config.py`** — add `BEACON_HTTP_URL: str | None = None`, `DUNE_QUERY_ID_STAKING_FLOWS: int = 0`.
8. **Modify `.env.example`** — add the two new keys with empty defaults + comments.
9. **Tests:** `test_staking_sync.py` (one happy path, one all-zero-rows-skipped, one entity-aware row mapping). `test_beacon_client.py` (mock httpx response, cache hit, error fallback).

### Frontend

1. **`frontend/src/api.ts`** — `fetchStakingFlows(hours)`, `fetchStakingSummary()`, types.
2. **New `frontend/src/components/StakingFlowsPanel.tsx`** — layout:
   ```
   ┌─ Beacon flows · last 48h ────────────────[range]┐
   │ 432,156 active   Net staked: +12,450 ETH        │
   │ ───────────────────────────────────────────────  │
   │ Deposits  ▰▰▰▰▰▰▰▰▰▰▰▰▰▰  +18.2k ETH ($63M)    │
   │           ╱╲╱╲                                    │  ← inline sparkline
   │ Full exits ▱▱▱▱▰▰▰▰  −5.7k ETH ($20M)           │
   │           ╲ ╱╲                                    │
   │ ─ Rewards skim (partial): +29 ETH ($101k) ─      │  ← muted
   └────────────────────────────────────────────────────┘
   ```
   Reuses `<Sparkline>` from PR #24. No new dependencies. Container-query responsive (hides muted sub-row at `@xs`).
3. **`frontend/src/lib/panelRegistry.ts`** — register the panel, default-place on the "Onchain" page.

### Migration / config

1. **One alembic migration** — creates `staking_flows`. Idempotent.
2. **Operator step** documented in CLAUDE.md: paste `backend/dune/staking_flows.sql` into a new Dune query, copy the ID into `.env` as `DUNE_QUERY_ID_STAKING_FLOWS`. Same operator pattern as the other Dune queries already shipped.
3. **CLAUDE.md** — add a v3-staking line under v2 (with ⚠️ until first sync runs, ✅ after).

## Architecture

```
Dune staking_ethereum.flows
        │
        ▼ (8h cron, sync_dune_flows)
┌──────────────────────────┐         ┌──────────────────────────┐
│  staking_flows table     │         │  Lighthouse beacon API   │
│  (ts_bucket, kind, eth,  │         │  /states/head/validators │
│   usd)                   │         │  (5min Redis cache)      │
└──────────────────────────┘         └──────────────────────────┘
        │                                       │
        └──────────┬────────────────────────────┘
                   ▼
       ┌────────────────────────────┐
       │  /api/staking/flows        │
       │  /api/staking/summary      │
       └────────────────────────────┘
                   │
                   ▼
       ┌────────────────────────────┐
       │  StakingFlowsPanel (React) │
       └────────────────────────────┘
```

Each piece has a single purpose: Dune is the historical archive, beacon API is the live counter, the panel composes them. They fail independently — beacon API down → tile hides; Dune sync down → panel shows the most recent stored data with a "stale since" badge.

## Risks / known limits

- **`staking_ethereum.flows` may have ingestion lag** — like all Dune spells, last hour or two may be incomplete. Acceptable: we already display "data is ~hourly" elsewhere. Users see a small `as of HH:MM UTC` label.
- **EIP-7251 max-effective-balance changes** — mainnet activation will introduce consolidations and partial-withdrawal-as-deposits. Our query just sums the columns Dune provides; if the spell incorporates the new event types, we get them for free.
- **Validator-count endpoint payload size** — ~1 MB / call. Cached 5 min in Redis = 12 calls/hour from localhost. Negligible.
- **Genesis-to-now total** — out of scope. The dashboard shows 30d max range; "total ETH staked" headline reflects the cumulative beacon-balance sum, **not** the 30d window. We expose 30d net + current active count; "total ETH staked" can be added in a future PR by reading `/eth/v1/beacon/states/head/finality_checkpoints` + balance aggregator (deferred).
- **Beacon API auth** — Lighthouse's HTTP API is unauthenticated by default but only listens on localhost. The `172.17.0.1` host bridge already used for Geth works the same way here. No new firewall config required.

## Tests

- **Backend unit:** `test_staking_sync.py` — round-trip a sample Dune row dict through `upsert_staking_flows`, assert table state. One test for entity-aware row mapping (we don't surface entity yet but capture it for future). One test for "all-zero amounts skipped" (defensive).
- **Backend unit:** `test_beacon_client.py` — mock httpx, assert active count parsed; assert cache hit avoids second call; assert `None` when `BEACON_HTTP_URL` unset.
- **Backend integration (existing pattern):** the `flow_jobs` integration test gets one extra job entry; verify it doesn't break existing assertions.
- **Frontend:** `npm run build` is the gate. No new component test required (Sparkline + Card are existing).

## Future work (sub-project B and beyond)

- **B (next PR):** LST market share panel — hourly JSON-RPC `totalSupply()` reads on stETH/wstETH/rETH/cbETH/sfrxETH/mETH/swETH. New `lst_supply` table, new realtime job, new panel.
- **C:** Per-entity stack — break the deposits leg into Lido/Coinbase/Rocket Pool/Solo using the `entity` column we already store in `staking_flows`.
- **D:** Exit queue length + clearance ETA — read from `/eth/v1/beacon/states/head/validators?status=active_exiting` and Lighthouse's churn-limit calculation.
- **E:** Total ETH staked headline — sum of validator balances at head, refreshed daily.
