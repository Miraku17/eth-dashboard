# Mantle DEX Flows — Design

**Date:** 2026-05-10
**Status:** Draft
**Track:** post-v4 backlog — "Mantle Network DEX flows"
**Predecessors:** v2-order-flow (mainnet WETH buy/sell pressure across Uniswap V2/V3 + Curve + Balancer) and v5-onchain-perps (Arbitrum sibling-listener scaffolding) — both shipping. This design ports the order-flow pattern to a second EVM chain.

## Goal

Surface **MNT buy vs. sell pressure** on Mantle DEXes — the directional, asset-centric signal the mainnet order-flow panel already shows for WETH, applied to MNT as Mantle's focal asset. v1 ships **Agni Finance only** (the largest Mantle DEX, Uniswap V3 fork, ~50% of chain TVL), with one new realtime listener, one new table, and one new dashboard panel.

The work also validates the chain-config-swap shape promised in the post-vacation backlog: same listener scaffolding as the Arbitrum perps work, with swapped RPC URL + native-token assumption + DEX pool registry. Adding additional Mantle DEXes (FusionX, Cleopatra, Butter, Merchant Moe) after v1 is registry work, not infrastructure work.

## Non-goals

- **Multi-DEX coverage.** v1 is Agni-only. Other Mantle DEXes are deferred to a follow-up that extends the registry.
- **Multi-asset flow.** Only MNT. WETH-on-Mantle, mETH, and stablecoin pairs are not surfaced as separate signals — they appear only as the *quote* side of MNT pools.
- **Mantle staking / mETH activity.** mETH is already covered by v3-lst (supply share) and v3-staking-yields (APR). This panel is intentionally about chain-DEX activity, not LST flow.
- **A generic chain foundation.** No `ChainListener` base class refactor. Mantle ships as a dedicated sibling listener mirroring `arbitrum_listener.py`; if a third chain is added later we revisit. (See "Decisions" below.)
- **Self-hosted Mantle node.** v1 connects to a public Mantle RPC. The user does not run their own Mantle node and is not signing up for one.
- **Backfill.** Forward-only from listener start. Historical Mantle DEX volume is available via DefiLlama / Dune if we ever want it; v1 doesn't.

## Decisions

Decisions reached during brainstorming, with one-line rationale:

| Decision                          | Choice                                                | Why                                                                                                          |
|-----------------------------------|-------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| Headline signal                   | **MNT buy/sell pressure** (signed, per-DEX)           | Direct port of the mainnet WETH panel. MNT is Mantle's focal asset; the mainnet pattern translates cleanly.  |
| DEX scope (v1)                    | **Agni only**                                         | ~50% of Mantle TVL in one V3-fork. Smallest scope that's still meaningful. Decoder is reused, not new.       |
| RPC source                        | **Public Mantle WS** via new `MANTLE_WS_URL` env var  | No paid Alchemy plan needed. Listener idles cleanly when env is unset (matches `arbitrum_realtime` pattern). |
| Persistence                       | **New `mantle_order_flow` table** (mirrors `order_flow`) | Cleanest semantics — `mnt_amount` is genuinely a different unit from mainnet's `weth_amount`. No migration risk to existing endpoint. |
| Chain abstraction                 | **None.** Sibling listener per chain.                  | YAGNI. Refactoring already-shipped Arbitrum code for a marginal third-chain signal is bigger blast radius than the value warrants. Revisit when a 3rd chain shows up. |

## Architecture

```
┌─────────────────────────────────┐    ┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│  realtime (mainnet)              │    │  arbitrum_realtime               │    │  mantle_realtime (NEW)           │
│  ───────────────                 │    │  ────────────────                │    │  ───────────────                 │
│  • OrderFlowAggregator (WETH)    │    │  • GMX V2 perp events            │    │  • MantleOrderFlowAggregator     │
│  • per-block eth_getLogs         │    │  • per-block eth_getLogs         │    │  • per-block eth_getLogs         │
│  • Uniswap V2/V3, Curve,         │    │  • PositionIncrease/Decrease     │    │  • Agni V3 Swap                  │
│    Balancer pool registry        │    │  • EventEmitter on Arbitrum      │    │  • Agni MNT pool registry        │
└────────────┬─────────────────────┘    └────────────┬─────────────────────┘    └────────────┬─────────────────────┘
             │                                       │                                        │
             ▼                                       ▼                                        ▼
       order_flow (PG)                       onchain_perp_event (PG)                   mantle_order_flow (PG)
             │                                       │                                        │
             ▼                                       ▼                                        ▼
   /api/flows/order-flow                /api/perps/{events,summary,…}            /api/flows/mantle-order-flow
             │                                       │                                        │
             ▼                                       ▼                                        ▼
   OrderFlowPanel                       OnchainPerpsPanel                          MantleOrderFlowPanel (NEW)
```

Three sibling listener processes, each fault-isolated. A Mantle public-RPC stall, an Agni decoder bug, or a Mantle-side malformed log cannot stop mainnet block ingestion.

## Components

Six new pieces, plus the `mantle_realtime` docker-compose service.

### 1. `backend/app/realtime/mantle_listener.py`

Entry point, modeled directly on `arbitrum_listener.py`. Subscribes to `newHeads` over the Mantle WS endpoint. Per block, calls `eth_getLogs` filtered to `(addresses: agni_pool_addresses, topics: [SWAP_TOPIC])`. Hands each decoded log to the aggregator. WS reconnect with exponential backoff, head-stall watchdog at 60s — public Mantle endpoints are known to silently drop subscriptions, so the watchdog is load-bearing here.

Idle mode: if `MANTLE_WS_URL` is unset, log once at INFO (`"MANTLE_WS_URL unset; mantle_realtime idle"`) and sleep forever. Container exit code 0; no restart loop.

### 2. `backend/app/realtime/mantle_dex_registry.py`

Curated list of Agni MNT pools. Each entry:

```python
class MantlePool(NamedTuple):
    address: str       # checksummed pool contract address
    dex: str           # 'agni' for v1
    token0_is_mnt: bool
    quote_symbol: str  # 'USDC', 'USDT', 'WETH', 'mETH', etc.
    fee_tier: int      # bps, for disambiguating multi-tier pools
```

v1 covers the top-5 Agni pools by 30d volume where MNT is one side. Concrete addresses resolved at implementation time via Agni's subgraph or DefiLlama's `/yields/pools` (chain=Mantle, project=agni-finance) and pinned in this file. The registry is a pure constant; changing it is a code change, not a config change.

### 3. `backend/app/realtime/mantle_swap_decoder.py`

Thin decoder. Takes a raw log and the matching `MantlePool` entry, parses the standard Uniswap V3 `Swap(sender, recipient, int256 amount0, int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick)` payload, and emits:

```python
class MantleSwap(NamedTuple):
    dex: str
    mnt_amount: float   # absolute MNT volume (always positive)
    side: str           # 'buy' if MNT flowed out of pool, else 'sell'
    ts: datetime
```

Sign convention (matches the existing mainnet decoder for WETH): if MNT is `token0` and `amount0 < 0`, MNT left the pool → user **bought** MNT. Inverse for `token1`. A malformed log (wrong topic count, truncated data, unknown pool) returns `None` and is logged at WARN with tx hash — never raises into the listener loop.

### 4. `backend/app/realtime/mantle_order_flow_agg.py`

`MantleOrderFlowAggregator`. In-memory `(dex, side) → (count, mnt_total)` per active hour, identical pattern to the mainnet `OrderFlowAggregator`:

- `add(swap)` accumulates into the buffer. If the swap's hour ≠ the buffered hour, flush previous, reset, accumulate.
- `flush()` runs `INSERT … ON CONFLICT (ts_bucket, dex, side) DO UPDATE SET count = count + EXCLUDED.count, mnt_amount = mnt_amount + EXCLUDED.mnt_amount`. Additive on_conflict makes partial flushes (graceful shutdown mid-hour) compose correctly.

Critically, the aggregator does **not** consult the price provider — it stores raw `mnt_amount`. USD valuation happens at read time. This keeps the writer simple and CoinGecko outage cannot drop swap data.

### 5. `backend/app/services/mnt_price.py`

`get_mnt_usd() -> float | None`. Redis-cached call to CoinGecko `/simple/price?ids=mantle&vs_currencies=usd`, 60s TTL. Returns `None` on HTTP error or rate limit. Used only by the read endpoint.

### 6. `backend/app/api/mantle_flows.py` + `frontend/src/components/MantleOrderFlowPanel.tsx`

New endpoint:

```
GET /api/flows/mantle-order-flow?hours=24
{
  "rows": [
    { "ts_bucket": "2026-05-10T15:00:00Z", "dex": "agni", "side": "buy",  "count": 142, "mnt_amount": 84321.5, "usd_value": 67457.2 },
    { "ts_bucket": "2026-05-10T15:00:00Z", "dex": "agni", "side": "sell", "count": 119, "mnt_amount": 71288.0, "usd_value": 57030.4 },
    …
  ],
  "summary": {
    "buy_usd": 1623441.0,
    "sell_usd": 1487023.0,
    "net_usd": 136418.0,
    "active_dexes": ["agni"],
    "mnt_usd": 0.80,
    "price_unavailable": false
  }
}
```

`usd_value` is `mnt_amount * mnt_usd` computed at request time. When the price provider returns `None`, `usd_value: null` and `summary.price_unavailable: true`.

Panel mirrors the existing `OrderFlowPanel`: buy/sell/net tile row, signed-stacked Recharts bars (buy above zero green, sell below zero red), per-DEX breakdown (one row in v1, room for more). Refetch every 60s. When the response is empty (idle mode), show "no data yet — set `MANTLE_WS_URL` and bring up the `mantle` profile" matching M2's empty-state pattern. When `price_unavailable`, show MNT-denominated bars + a small footer "USD pricing unavailable (CoinGecko)".

### 7. `docker-compose.yml` — new service

```yaml
mantle_realtime:
  build: ./backend
  profiles: ["mantle"]
  command: python -m app.realtime.mantle_listener
  env_file: .env
  depends_on:
    postgres: { condition: service_healthy }
    redis:    { condition: service_healthy }
  restart: unless-stopped
  dns: ["1.1.1.1", "8.8.8.8"]
```

Profile-gated, opt-in: `docker compose --profile mantle up -d mantle_realtime`. Mirrors `arbitrum_realtime`.

## Data flow

**Per-block (listener):**
```
newHeads
  ↓ block N
eth_getLogs { address: agni_pool_addresses, topics: [SWAP_TOPIC],
              fromBlock: N, toBlock: N }
  ↓ for each log
mantle_swap_decoder → MantleSwap | None
  ↓ if not None
MantleOrderFlowAggregator.add(swap)
  ├─ same hour as buffer  → accumulate
  └─ new hour              → flush previous, reset, accumulate
```

**Flush:** on hour rollover and on `SIGTERM` (graceful shutdown handler in `mantle_listener.py`). Flushing an in-memory `(dex, side) → (count, mnt_amount)` map is one `INSERT … ON CONFLICT` per row, additive.

**Read:** `GET /api/flows/mantle-order-flow?hours=24` runs `SELECT … WHERE ts_bucket >= NOW() - INTERVAL '24 hours'`, calls `get_mnt_usd()` once, multiplies. Single round-trip; response cacheable for 60s in Redis if read volume warrants (deferred until needed).

## Schema

Single new table:

```sql
CREATE TABLE mantle_order_flow (
    ts_bucket   TIMESTAMPTZ     NOT NULL,
    dex         TEXT            NOT NULL,
    side        TEXT            NOT NULL,
    count       INTEGER         NOT NULL,
    mnt_amount  NUMERIC(38, 18) NOT NULL,
    PRIMARY KEY (ts_bucket, dex, side)
);
CREATE INDEX ix_mantle_order_flow_ts ON mantle_order_flow (ts_bucket DESC);
```

USD value is **not** stored — see component §4 above. NUMERIC(38,18) matches the precision of the existing mainnet `order_flow.weth_amount`.

Alembic migration: one `op.create_table(...)`. No backfill needed.

## Error handling + idle mode

| Failure mode                         | Behavior                                                                                                    |
|--------------------------------------|-------------------------------------------------------------------------------------------------------------|
| `MANTLE_WS_URL` unset                | Listener logs once and sleeps. Endpoint returns empty rows. Panel shows empty-state copy.                   |
| WS connect failure                   | Exponential backoff (5s base, capped). Container `restart: unless-stopped` covers full process death.       |
| WS subscription stalls (no `newHeads`) | Watchdog at 60s force-closes and reconnects. Critical for public Mantle RPCs.                              |
| `eth_getLogs` rate-limit / 429       | Logged at WARN; that block's swaps are missed (no retry — next block's logs are independent). Aggregator state untouched. |
| Single malformed log                 | Decoder returns `None`, log WARN with tx hash, listener continues.                                          |
| Pool not in registry                 | Filtered out at `eth_getLogs` time (address filter). Defense-in-depth: decoder also rejects unknown addresses. |
| CoinGecko outage                     | `get_mnt_usd() → None`. Read endpoint returns `usd_value: null`, `price_unavailable: true`. Writer unaffected. |
| Aggregator partial flush (mid-hour crash) | Container restarts, buffer rebuilds from next swap, additive on_conflict makes the eventual row correct. At most one in-flight bucket is briefly out of sync. |
| Listener crash                       | Docker restarts. PG state is intact; in-memory buffer is lost (only the current hour, partially).           |

## Testing

Three new test files, all backend, all isolated.

### `backend/tests/test_mantle_swap_decoder.py`
Pure compute, no DB, no network. Hand-crafted log fixtures:
- MNT-as-token0 buy (amount0 < 0) → `side='buy'`, `mnt_amount = abs(amount0) / 1e18`
- MNT-as-token0 sell (amount0 > 0) → `side='sell'`
- MNT-as-token1 buy + sell (inverse polarity)
- Wrong topic count → `None`
- Truncated data → `None`
- Unknown pool address → `None`

### `backend/tests/test_mantle_order_flow_agg.py`
Aggregator semantics with a mocked sessionmaker. Cases mirror existing `test_order_flow_agg.py`:
- Two swaps in the same hour → single row, summed `mnt_amount` and `count`
- Hour rollover → previous bucket flushed, new bucket clean
- `flush()` called twice on the same partial buffer → additive on_conflict produces correct totals (not doubled)
- Zero or negative `mnt_amount` → silently dropped
- Unknown side → silently dropped

### `backend/tests/test_mantle_flows_api.py`
Endpoint integration test against the testcontainers Postgres. Seeds rows directly into `mantle_order_flow`, asserts:
- `/api/flows/mantle-order-flow?hours=24` returns expected `rows` shape
- `summary.buy_usd / sell_usd / net_usd` correctly aggregated
- When the price provider is patched to return `None`, response carries `usd_value: null` and `summary.price_unavailable: true`
- `?hours=1` correctly windows the rows

### Out of scope (matches `arbitrum_listener.py` precedent)
- WS lifecycle / reconnect path (no test in mainnet or Arbitrum listener either; manually verified)
- Real Mantle RPC connectivity (manual smoke test only)

### Manual verification before declaring v1 done
1. Start `mantle_realtime` against the public WS, watch logs for the first decoded swap within ~5 minutes.
2. Wait for a clean hour rollover, verify a row appears in `mantle_order_flow`.
3. Open the panel, confirm bars render and USD valuation is live (CoinGecko reachable).
4. Disable the panel network briefly to confirm the empty-state copy displays.

## Operator setup

New env var (add to `.env.example` and `docs/mantle-setup.md`):

```
# Mantle public WS endpoint (e.g. wss://mantle-rpc.publicnode.com).
# Listener idles when unset; the panel will show empty-state copy.
MANTLE_WS_URL=
```

Run:
```
docker compose --profile mantle up -d mantle_realtime
```

To turn off, just stop the container — mainnet and Arbitrum are unaffected.

## Open follow-ups (not in v1)

- Add FusionX, Cleopatra, Butter to the Agni registry — pure registry work, no decoder change (all V3 forks).
- Add Merchant Moe — needs a Liquidity Book decoder, more substantial.
- Consider extracting a `ChainListener` base class only if a 4th chain is added; YAGNI now.
- Per-asset breakdown (MNT/USDC vs MNT/WETH vs MNT/mETH) inside Agni — registry already carries `quote_symbol`, would require one extra GROUP BY on the read path.
- Net-flow alert rule: `mantle_mnt_flow_move` analog to `wallet_score_move`. Defer until the operator has signal on whether this panel earns the screen real-estate.

## CLAUDE.md update (post-merge)

When v1 ships, append to the Backlog section:

```
- ✅ Mantle Network DEX flows — shipped 2026-05-XX. Sibling listener `mantle_realtime`
  (gated `mantle` profile) consuming Agni V3 swap events for MNT pools; per-DEX
  buy/sell flow persisted to `mantle_order_flow`; /api/flows/mantle-order-flow
  + MantleOrderFlowPanel on Onchain page. Public Mantle WS via MANTLE_WS_URL
  (idle when unset). v1 is Agni-only; broader DEX coverage is registry work.
```
