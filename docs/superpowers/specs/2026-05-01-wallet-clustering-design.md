# Wallet Clustering — Design

**Status:** approved 2026-05-01
**Track:** v2-final (closes the v2 milestone with mempool, derivatives, order-flow, smart-money leaderboard, volume structure, and now clustering)
**Related specs:**
- `2026-04-23-eth-analytics-dashboard-design.md` (parent — clustering was originally scoped to v3 there; promoted into v2 by user request)
- `2026-04-28-mempool-tracking-design.md`
- `2026-04-24-smart-money-leaderboard-design.md`

## Goal

On-demand wallet investigation. Any address rendered in the dashboard becomes
clickable; clicking opens a side drawer that shows what we know about the
wallet — labels, *probably-linked* wallets with explicit confidence, and
aggregate stats — within a second or two. The tool answers the question the
operator actually has when staring at a whale tx: **who is this?**

This is an *investigative aid*, not a labeller. We never claim "wallet A and
wallet B are the same person." We surface evidence with confidence and let the
operator judge.

## Non-goals

- Multi-tenant or shareable cluster IDs.
- Pre-computed batch clustering across the whole network.
- Multi-hop traversal (recursing into a linked wallet's links).
- Time-correlated transfer heuristics, counterparty Jaccard, multicall co-spend
  — explicitly deferred. v1 keeps the heuristic surface small and high-signal.
- Standalone "browse top clusters" panel — deferred to a future iteration.
- Manual address-search box in the topbar — deferred; if the operator wants
  to look up an arbitrary wallet they paste it into the URL or click an
  address that's already on screen.

## UX

1. Every wallet address rendered in the dashboard (whale transfers,
   smart-money leaderboard, mempool pending panel) is wrapped in a shared
   `<AddressLink>` component. Hover shows the address truncated +
   copy-to-clipboard; click opens the wallet drawer.
2. The drawer slides in from the right and shows:
   - **Header:** address (full, copy button), Etherscan link, refresh button.
   - **Labels:** Etherscan name tag(s), our local CEX label if any.
   - **Stats:** first seen, last seen, total tx count, last 7d ETH flow USD.
   - **Linked wallets:** up to 50 rows, each with `address`, `label` (if any),
     a `confidence` chip (`strong` green, `weak` amber), and a `reason` line
     (e.g. *"shared CEX deposit (binance · 0xabc…)"* or *"shared gas funder
     (0xdef…)"*).
   - **Empty state:** "No linked wallets found" — common for fresh wallets
     and for wallets funded only via public services.
3. The drawer's data is fetched via a new `GET /api/clusters/{address}` and
   cached for 7 days. The refresh button calls
   `POST /api/clusters/{address}/refresh` to bust the cache and recompute.

A cold lookup (no cache row) takes 1–3s — bounded by ~6 Etherscan calls in
parallel. A warm lookup is a single Postgres read.

## Data source

**Etherscan free-tier REST API.** Decision rationale:

- Vanilla Geth has no address-indexed tx history. The two heuristics we ship
  both require *"give me txs involving address X."* Without a separate
  indexer that's effectively impossible on a stock node.
- Etherscan provides exactly that index, free, with 5 req/s and 100 000
  calls/day. We already use Etherscan for label enrichment in earlier
  milestones, so the dependency is not new.
- Sub-second responses let us serve clusters synchronously instead of
  queueing through arq, which keeps the implementation small.
- Self-hosting an indexer (TrueBlocks, Erigon `trace_filter`, custom Postgres
  index over our node) is the long-term right answer, but it's a separate
  project of its own and out of scope.
- Dune is already credit-budgeted for the heavier batch jobs (smart-money
  leaderboard, order-flow, volume structure). Reusing Dune here would compete
  with those for credits and add 10–30 s latency per lookup.

Etherscan endpoints used:
- `account.txlist` — normal txs by address, paginated. We page once asc to
  find the first ETH inflow (gas funder), once desc to read recent stats.
- `account.tokentx` — ERC-20 transfers, used by the CEX-deposit heuristic
  for stablecoin outflows.
- `account.txlistinternal` — internal txs, used as a fallback when the first
  ETH inflow is contract-funded (e.g. a multisig payout).

A single fresh lookup: roughly 6 calls. With 7-day cache and ~50 unique
lookups/day this is ~300 calls/day, well inside the 100 000/day budget.

## Heuristics (v1)

### H1 — Shared gas funder

For wallet `X`, find the first ETH inflow tx (smallest block number with
`to == X` and non-zero `value`). The `from` of that tx is the **funder** `F`.

Two wallets `A`, `B` are linked by H1 iff:
- Both have the same funder `F`,
- *and* `F` is **not** on the public-funder denylist.

Confidence:
- `strong` if `F` has funded fewer than 50 distinct addresses (we sample
  this via Etherscan `txlistinternal` / `txlist` count on `F` itself,
  capped — see budget notes).
- `weak` otherwise.

Rationale: a private EOA that funds a small number of wallets is almost
certainly a single operator. A funder that has fanned out to thousands of
wallets without being a known public service is suspicious but lower
confidence — could be a market-maker treasury, an OTC desk, or a sybil
operation.

### H2 — Same CEX deposit address

CEX deposit addresses are unique per user — Binance, Coinbase, Kraken, OKX
each generate a fresh forwarder address per customer that empties into a
known hot wallet within minutes of receipt. If two wallets repeatedly send
funds to the same forwarder, they are with very high probability the same
CEX account holder.

Implementation:
- Maintain a static map `cex_hot_wallets.json` of CEX hot-wallet addresses
  per exchange (we already have this data for the whale-transfer label
  feature; reuse).
- For wallet `X`, fetch recent ETH + USDT/USDC transfers from `X`. For each
  unique `to` address `D`, check whether `D` later forwards to a known hot
  wallet. If yes, `D` is a deposit address for that exchange.
- Two wallets sharing any deposit address are linked by H2 with confidence
  `strong`.

Forwarder identification: we look up the deposit address `D`'s outbound txs
and see if a known hot wallet appears in the destinations within ~24h of the
incoming deposit. This is two extra Etherscan calls per candidate `D`; we
cap candidates at the top 10 by aggregate USD flow per wallet to bound cost.

### H3 — Label enrichment

Not clustering, just decoration. For the target wallet *and* every linked
wallet returned, fetch the Etherscan name tag (cached in Redis at
`labels:eth:{addr}` with 30-day TTL — same machinery as existing label
fetches). Layer our local CEX label list on top.

## Public-funder denylist

`backend/app/services/clustering/public_funders.json` — seeded with ~30
known addresses:

- CEX hot wallets (Binance 7/14/15, Coinbase, Kraken, OKX, Bitfinex, Bybit,
  …) — these fund withdrawals to thousands of unrelated users.
- Tornado Cash pools (0.1 / 1 / 10 / 100 ETH) — funding from these breaks
  the trail by design and any "shared funder" match is meaningless.
- Major bridges (Hop, Stargate, Across, Synapse, Wormhole token bridge).
- Common faucets and airdrop distributors.
- MEV builders that occasionally appear as funders via direct sends.

Format:

```json
{
  "addresses": [
    { "address": "0x...", "label": "Binance 14", "kind": "cex" },
    { "address": "0x...", "label": "Tornado 10 ETH",  "kind": "mixer" }
  ]
}
```

The list is checked into the repo, hand-curated, easy to extend by PR. Any
H1 match where `F` is on the list is **suppressed** (not surfaced as a weak
match — the signal is genuinely zero).

## Architecture

### Backend layout

```
backend/app/
  clients/
    etherscan.py                       # NEW: thin async client, paged, retry, rate-limit budget
  services/clustering/                 # NEW
    __init__.py
    cluster_engine.py                  # orchestrates H1+H2+H3, returns ClusterResult
    gas_funder.py                      # H1 logic
    cex_deposit.py                     # H2 logic
    public_funders.py                  # loader for the static JSON list
    public_funders.json                # the list itself
  api/
    clusters.py                        # NEW: GET / POST /api/clusters/...
  core/
    models.py                          # +WalletCluster row
```

### Cluster engine flow

```
cluster_engine.compute(address):
  1. fetch first ETH inflow → funder F (gas_funder.first_funder)
  2. fetch top-N outbound destinations (eth + tokentx) → identify CEX deposit addresses
     (cex_deposit.find_deposits)
  3. if F not on denylist: fetch txs sent FROM F via Etherscan `txlist`
     (ordered by block, capped at `cluster_funder_strong_threshold + 1` rows
     so we know whether F's fan-out crosses the strong/weak boundary).
     The unique `to` addresses are the candidate co-funded wallets. Score
     each by F's total fan-out (count of unique recipients seen).
  4. fetch wallets sharing any of our deposit addresses: for each deposit
     address D found in step 2, query `txlist` on D and collect unique
     `from` addresses (other depositors). Cap candidates per D at 50.
  5. union (3) + (4) → linked_wallets, sort by combined evidence, cap at 50
  6. label-enrich target + all linked wallets (services/clustering uses existing
     labels client; cached separately in Redis)
  7. compute stats (first_seen, last_seen, tx_count, eth_flow_7d_usd)
  8. assemble ClusterResult, upsert wallet_clusters row with
     ttl_expires_at = now + 7d, return
```

The engine is pure-async and parallel where it can be — funder lookup and
top-destination fetch can run concurrently; co-funded-wallet expansion runs
after we know `F`.

### API

```
GET /api/clusters/{address}
  → 200 ClusterResult     (cache hit OR computed inline)
  → 400  if address malformed (not 0x + 40 hex)
  → 404  reserved (we always return a result, even empty)
  → 503  if Etherscan unreachable AND no cache row exists

POST /api/clusters/{address}/refresh
  → 200 ClusterResult     (cache invalidated and recomputed inline)
  → 503  same fallback as above
```

Both routes are auth-gated via the existing `require_auth` dependency.

`ClusterResult` schema:

```python
class LinkedWallet(BaseModel):
    address: str
    label: str | None
    confidence: Literal["strong", "weak"]
    reasons: list[str]   # e.g. ["shared_cex_deposit:binance:0xabc…"]

class ClusterStats(BaseModel):
    first_seen: datetime | None
    last_seen: datetime | None
    tx_count: int
    eth_flow_7d_usd: float | None

class ClusterResult(BaseModel):
    address: str
    computed_at: datetime
    stale: bool = False              # true when served from an expired row during Etherscan outage
    labels: list[str]
    gas_funder: GasFunderInfo | None
    cex_deposits: list[CexDepositInfo]
    linked_wallets: list[LinkedWallet]
    stats: ClusterStats
```

## Data model

```python
class WalletCluster(Base):
    __tablename__ = "wallet_clusters"
    address: Mapped[str]            = mapped_column(String(42), primary_key=True)
    computed_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True))
    ttl_expires_at: Mapped[datetime]= mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict]           = mapped_column(JSONB)
```

Migration: `0010_wallet_clusters.py` (next free number; verify at write time).

`payload` is the full serialized `ClusterResult`. We store the whole thing
rather than normalizing because:
- Reads are 100% by primary key (`address`); no analytical queries against
  cluster contents.
- The shape is tied to the engine version; serializing as JSONB means we
  can evolve the engine without schema migrations (we'd just bump a
  `schema_version` field if needed).

## Frontend

```
frontend/src/
  components/
    AddressLink.tsx           # NEW — wraps an address, click opens drawer
    WalletDrawer.tsx          # NEW — right-side slide-out panel
  hooks/
    useWalletDrawer.ts        # NEW — global drawer state (Zustand or context)
  api.ts                      # +fetchCluster, +refreshCluster, +Cluster types
```

Integration points (replace raw address rendering with `<AddressLink>`):
- `components/WhaleTransfersPanel.tsx` (from + to columns, both confirmed and pending sections)
- `components/SmartMoneyLeaderboardPanel.tsx` (wallet column)
- Any address rendered inside the alerts panel payloads

The drawer uses `useQuery(['cluster', address])` against
`fetchCluster(address)` with `refetchOnWindowFocus: false`. The refresh
button calls `refreshCluster(address)` and invalidates the query.

Loading state: skeleton rows for the linked-wallets table during the 1–3s
cold lookup. Error state: a small inline error with retry button.

## Caching

- **Postgres `wallet_clusters`** is the system of record for cluster results,
  TTL 7 days. After `ttl_expires_at`, rows are kept for an additional 7 days
  as a last-resort fallback served when Etherscan is down (response carries
  a `stale: true` flag and the original `computed_at`). Cleanup job
  `purge_expired_clusters` runs daily via arq cron and deletes rows where
  `ttl_expires_at < now() - interval '7 days'` (i.e. 14 days after
  computation). Total worst-case retention per row: ~14 days.
- **Redis label cache** at `labels:eth:{addr}` (already used by existing
  features) — 30-day TTL.
- **No Redis cache for cluster results.** Postgres reads on a primary key
  are <1 ms; an additional cache layer adds invalidation complexity for
  no measurable win.

## Etherscan client

`backend/app/clients/etherscan.py` — async, single shared httpx client,
rate-limited via an internal `asyncio.Semaphore` capped at 4 concurrent
requests (well under the 5 req/s ceiling). Retries on 429 / 5xx with
exponential backoff up to 3 attempts. Surfaces a typed error
(`EtherscanRateLimited`, `EtherscanUnavailable`) that the engine and API
layer translate into the `503` fallback.

API key from env `ETHERSCAN_API_KEY` (already present in `.env.example`).

## Configuration

Add to `backend/app/core/config.py`:
- `etherscan_api_key: str = ""` — already present in some form, verify
  reuse vs. add.
- `cluster_cache_ttl_days: int = 7`
- `cluster_max_linked_wallets: int = 50`
- `cluster_max_deposit_candidates: int = 10`
- `cluster_funder_strong_threshold: int = 50` (max fan-out for `strong`
  classification)

No new env vars required beyond `ETHERSCAN_API_KEY`.

## Tests

Backend (pytest, testcontainers for DB):

- `test_etherscan_client.py` — mocks HTTP, verifies pagination handling,
  429 retry pacing, and 5xx escalation.
- `test_gas_funder.py` — fixtures of canned `txlist asc` responses;
  verifies first-funder detection, denylist suppression, fan-out scoring.
- `test_cex_deposit.py` — fixtures with synthetic forwarder + hot-wallet
  flows; verifies deposit-address detection and cross-wallet matching.
- `test_cluster_engine.py` — end-to-end with a stub Etherscan client;
  golden tests for: known cluster shape, public-funder suppression,
  empty-history wallet, wallet linked by H2 only, wallet linked by H1+H2.
- `test_clusters_api.py` — cache hit, cache miss (computes), refresh,
  Etherscan-down fallback (stale row served), Etherscan-down + no-cache
  503, malformed address 400, auth required.

Frontend (vitest + RTL):

- `WalletDrawer.test.tsx` — renders cluster shape, confidence chip
  styling, empty-linked-wallets state, refresh button calls API.
- `AddressLink.test.tsx` — opens drawer on click, copies address,
  Etherscan link is correct.

## Milestones / commit shape

Sequenced PR-sized commits (rough — the writing-plans pass will sharpen
ordering and dependencies):

1. `feat(clusters): WalletCluster model + 0010 migration`
2. `feat(clusters): Etherscan async client with rate limit + retry`
3. `feat(clusters): public-funder denylist + loader`
4. `feat(clusters): gas-funder heuristic`
5. `feat(clusters): CEX-deposit heuristic`
6. `feat(clusters): cluster engine orchestrator`
7. `feat(clusters): /api/clusters routes + auth gate`
8. `feat(clusters): purge-expired arq cron`
9. `feat(clusters): AddressLink + WalletDrawer + api.ts`
10. `feat(clusters): wire AddressLink into whale / smart-money / pending panels`
11. `docs(clusters): operator notes + close v2 in CLAUDE.md`

Tests land alongside each commit, not at the end.

## Risks and known limits

- **False positives are unavoidable.** Clustering without proprietary data
  has a hard ceiling. Mitigation: the public-funder denylist, explicit
  `strong`/`weak` chips, never claiming "same person."
- **Forwarder list staleness.** The CEX-deposit heuristic only catches the
  exchanges in our static hot-wallet map. New exchanges or rotated hot
  wallets silently drop out until we update. Documented as a known
  limitation; a future iteration could pull a fresher list from a
  third-party source.
- **Etherscan downtime.** Cold lookups during a Etherscan outage return
  503; cached lookups still serve from Postgres with `stale: true`. We
  do not fall back to Dune — the latency profile is incompatible with
  synchronous lookup.
- **Adversarial wallets** (those funded via Tornado, fresh wallets with no
  CEX relationship) will return empty clusters. That is correct — we have
  no signal — but operators should not interpret "no linked wallets" as
  "this wallet stands alone." The drawer copy makes that explicit.
- **Cost growth** if a cluster-of-the-day pattern emerges (e.g. an
  influencer posts an address and 1k people look it up). Postgres cache
  absorbs this — only the first hit pays Etherscan. Worst case, a viral
  address is ~6 calls; we have 100k/day headroom.

## Open questions

None remaining at design time.

## Future work (not v2)

- Multi-hop traversal (cluster a wallet's wallets recursively, with depth
  limit and confidence decay).
- Counterparty-Jaccard heuristic.
- Multicall / Disperse co-spend heuristic.
- Pre-computed batch clustering for the smart-money leaderboard
  (annotate each leaderboard row with its cluster size).
- Standalone "top clusters by 7d flow" panel (the v3-discovery angle).
- Manual address-search box in the topbar.
- Self-hosted address-tx indexer to drop the Etherscan dependency.
