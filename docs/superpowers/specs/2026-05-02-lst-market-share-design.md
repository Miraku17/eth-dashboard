# LST Market Share — Design

**Status:** approved 2026-05-02
**Track:** v3 — DeFi & staking layer (sub-project B; sub-project A "Beacon Flows" shipped as PR #26)
**Related specs:**
- `2026-05-02-eth-staking-flows-design.md` (parent — explicitly defers LST market share to this follow-up)

## Goal

Surface the custody side of the staking story: which liquid-staking tokens (LSTs) hold the staked ETH, and how their relative market share is moving. Sub-project A shows ETH flowing into and out of the beacon chain in aggregate; this panel shows **who is holding the staked ETH** in tokenized form.

The hero visual is a **stacked area chart of LST `totalSupply()` over the last 30 days**, with one band per token. Lido (stETH) is the dominant share; we want the chart to make share shifts (e.g., a Coinbase/cbETH outflow into Lido, or a Mantle/mETH ramp) visible at a glance.

## Non-goals

- **Rate-ratio normalization to ETH-equivalent.** Share-tokens like rETH and sfrxETH have totalSupply slightly below ETH backing (each rETH ≈ 1.13 ETH today due to accumulated rewards). v1 shows raw `totalSupply()` as the metric, labeled "supply" — accurate enough for share visualization, easy to understand. Future work can add per-token exchange rates if precision becomes a customer ask.
- **wstETH.** It's just wrapped stETH; including it would double-count Lido. We track stETH and skip wstETH.
- **Restaking layer (EigenLayer LRTs).** Different layer, different question, different panel. Out of scope.
- **Per-validator-operator view.** A is the per-issuer breakdown of beacon flows (Lido / Coinbase / Rocket Pool / Solo). B is the per-token holdings view. They're complementary; this PR doesn't merge them.
- **Realtime listener.** Supply changes slowly enough that hourly snapshots are plenty.

## Tokens tracked (v1)

Seven LSTs, all on Ethereum mainnet, all 18 decimals:

| Symbol | Issuer | Contract address | Notes |
|---|---|---|---|
| stETH | Lido | `0xae7ab96520de3a18e5e111b5eaab095312d7fe84` | rebasing 1:1 to ETH |
| rETH | Rocket Pool | `0xae78736cd615f374d3085123a210448e74fc6393` | share-token (~1.13 ETH each) |
| cbETH | Coinbase | `0xbe9895146f7af43049ca1c1ae358b0541ea49704` | share-token |
| sfrxETH | Frax | `0xac3e018457b222d93114458476f3e3416abbe38f` | share-token |
| mETH | Mantle | `0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa` | share-token |
| swETH | Swell | `0xf951e335afb289353dc249e82926178eac7ded78` | share-token |
| ETHx | Stader | `0xa35b1b31ce002fbf2058d22f30f95d405200a15b` | share-token |

These cover ~95% of the active LST market by TVL.

## Data source

**Self-hosted Geth via JSON-RPC** (`ALCHEMY_HTTP_URL`, the same node used by the wallet-profile balance reads). One call per token per hour:

```
eth_call(to=token, data=0x18160ddd /* totalSupply() */, block='latest')
```

All seven calls fit in a single JSON-RPC batch request — same pattern as `batch_eth_call` already in `backend/app/clients/eth_rpc.py`. Network cost: 7 reads / hour × 24 hours = 168 calls/day to localhost. Negligible.

If `ALCHEMY_HTTP_URL` is unset (dev / cheap deploys), the cron is a no-op and the panel shows "no data yet — configure ALCHEMY_HTTP_URL".

## Architecture

```
hourly cron (arq)
   │
   ▼
batch eth_call → 7 LST contracts → totalSupply()
   │
   ▼
┌────────────────────────────┐
│  lst_supply table          │
│  (ts_bucket, token, supply)│
└────────────────────────────┘
   │
   ▼
/api/staking/lst-supply?hours=N
   │
   ▼
LstMarketSharePanel (stacked area, Recharts)
```

Each unit has one job: cron reads chain, table archives, endpoint serves, panel renders. Failure isolation: cron failure → table doesn't get a new row, panel renders with whatever's stored (with a "stale since" badge); RPC node down → cron logs and exits cleanly.

## Schema

New table `lst_supply`:

```sql
ts_bucket TIMESTAMPTZ NOT NULL,
token VARCHAR(10) NOT NULL,
supply NUMERIC(38, 18) NOT NULL,
PRIMARY KEY (ts_bucket, token)
```

One row per (token, hour). Composite PK makes upsert idempotent if the cron retries.

## Endpoint

`GET /api/staking/lst-supply?hours=720`:

```json
{
  "points": [
    { "ts_bucket": "2026-05-02T03:00:00Z", "token": "stETH",   "supply": 9876543.21 },
    { "ts_bucket": "2026-05-02T03:00:00Z", "token": "rETH",    "supply":  876543.21 },
    ...
  ]
}
```

Same response shape as the other flow endpoints (point list). Auth-gated via `AuthDep` like the rest of the dashboard.

## Frontend panel

`LstMarketSharePanel.tsx`. Layout:

```
┌─ LST market share · last 30d ────────────────[range]┐
│ stETH ████████████████░░░░░ 71.2%                    │  ← legend with current %
│ rETH  ███░░░░░░░░░░░░░░░░░░  9.8%                    │
│ cbETH ██░░░░░░░░░░░░░░░░░░░  6.3%                    │
│ ...                                                   │
│                                                       │
│  ┌──────────────────────────────────────────────┐   │
│  │ ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│   │  ← stacked area
│  │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│   │
│  │ ████████████████████████████████████████████│   │
│  └──────────────────────────────────────────────┘   │
│  30d ago                                       now   │
└───────────────────────────────────────────────────────┘
```

**Library:** Recharts is already a dependency (used by `OnchainVolumePanel`, `NetworkActivityPanel`). Use `<AreaChart>` with `stackId="lst"` per `<Area>`.

**Mode toggle (v1.5, optional):** an "Absolute / Share %" toggle that switches between raw supply (ETH units) and percentage stacking. v1 ships with absolute-only; share% is a tiny PR follow-up if the operator wants it.

**Color palette:** stable per-token color so eyes can track each layer over time. Use existing Tailwind tokens (slate / sky / emerald / amber / rose / violet / fuchsia) — one per token, ordered by typical market share descending.

## What changes

### Backend

1. **New `backend/alembic/versions/0010_lst_supply.py`** — `lst_supply` table.
2. **New `LstSupply` ORM class** in `models.py`.
3. **New `backend/app/services/lst_tokens.py`** — single source of truth for the LST registry: `(symbol, address, decimals)` tuple + the canonical 7-entry list. Mirrors `backend/app/realtime/tokens.py` style.
4. **New `backend/app/workers/lst_jobs.py`** — `async def sync_lst_supply(ctx)`. Builds a 7-call batch, parses uint256 hex results, writes one row per token at the current hour bucket.
5. **Wire into `arq_settings.py`** — add `cron(sync_lst_supply, minute={7}, run_at_startup=False)` (offset minute 7 to avoid colliding with the on-the-hour syncs).
6. **New `backend/app/services/lst_sync.py`** with `upsert_lst_supply` mirroring the existing flow_sync pattern.
7. **Extend `backend/app/api/staking.py`** with `GET /lst-supply` endpoint + `LstSupplyPoint` / `LstSupplyResponse` schemas.
8. **Tests:**
    - `test_lst_sync.py` — upsert round-trip + idempotency
    - `test_lst_jobs.py` — mock the eth_rpc client, assert N rows written, assert decode correctness on a known totalSupply hex value

### Frontend

1. **`frontend/src/api.ts`** — `LstSupplyPoint` type + `fetchLstSupply(hours)`.
2. **New `frontend/src/components/LstMarketSharePanel.tsx`** — Recharts stacked area + per-token legend with current % share.
3. **`frontend/src/lib/panelRegistry.ts`** — register the panel under "Onchain" page (or alongside `staking-flows`).

### Config

- No new env vars. Reuses `ALCHEMY_HTTP_URL` (already documented for the wallet-profile feature).
- `CLAUDE.md` adds a `v3-lst` line under v3-staking.

## Risks / known limits

- **Share-token undercount.** rETH / cbETH / sfrxETH / mETH / swETH / ETHx report supply that's a few % below ETH backing. v1 displays raw supply; chart still tells the right story since the dominant share is stETH (rebasing 1:1). Documented in the panel subtitle.
- **Cron skip on RPC failure.** If the node is down, that hour's row is missing. Recharts handles missing buckets cleanly (gaps render as missing data). The next successful run picks back up.
- **First-run history is sparse.** Until the cron has run for a few hours, the chart shows just one or two points. Acceptable — same UX pattern as the other Dune-backed panels at fresh deploy.
- **Token list goes stale.** New LSTs appear (LRTs, restaking variants, niche issuers). The 7-entry list lives in `lst_tokens.py` for easy extension; refresh ad-hoc when noteworthy.

## Tests

- **Backend unit:** `test_lst_sync.py` (3 tests — round trip, idempotent upsert, multi-token). `test_lst_jobs.py` (2 tests — mock RPC + assert correct row count, decode correctness).
- **Backend integration:** the cron registration adds one line; existing arq tests cover the framework.
- **Frontend:** `npm run build` is the gate. No new component test needed.

## Future work

- **Share % toggle** (Absolute / %) — small frontend follow-up.
- **ETH-equivalent normalization** — fetch per-token exchange rates (`getExchangeRate()` for rETH, etc.); convert supply to ETH-backed units. Unlocks "true" market share by ETH staked.
- **Restaking layer (LRTs)** — eETH / ezETH / rsETH / pufETH. Separate panel; same pattern.
- **Per-token mint/burn flow** — extend Beacon Flows panel to also surface 24h LST supply Δ next to validator deposits/exits, so the panel becomes "where staked ETH went and what wrapped it".
