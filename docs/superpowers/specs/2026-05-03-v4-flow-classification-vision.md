# v4 — Wallet identity + live flow classification

**Date:** 2026-05-03
**Status:** Vision / planning. No code yet.
**Source:** User vision message, 2026-05-03.

## Goal

Make every transfer in the system *legible* — not just "X moved $Y of asset Z"
but **where it's going and why**. Today the dashboard captures whale moves
but the destination's *meaning* (CEX deposit? DEX swap? bridge? Hyperliquid
deposit? wallet→wallet?) is discarded.

The user's stated weighting:

> "It's nice to know big moves from whales in general. But 20× more
> important is the flow to exchange possibilities — because this has price
> impact."

So the design optimizes for surfacing **CEX-bound flows** loudest, with
DeFi / staking / bridge / Hyperliquid as secondary signals, and pure
wallet↔wallet flows demoted to opt-in.

Hard constraints from the user:

- **Live, not delayed.** Reads come from the self-hosted Geth + Lighthouse
  feed. Avoid third-party APIs for the on-chain side. Seconds matter.
- **Filterable.** "Too much information" is the failure mode. The default
  view shows the high-signal flows (CEX in/out); other categories are
  toggleable.
- **AI is later-stage.** Performance-weighted wallet ranking and market-regime
  classification are explicitly long-term. Not v4-immediate.

## Architecture, three layers

### Layer 1 — `address_label` foundation

A single labeled-address registry. New table:

```sql
CREATE TABLE address_label (
  address       VARCHAR(42) PRIMARY KEY,         -- lowercase 0x…
  category      VARCHAR(24) NOT NULL,            -- enum below
  label         VARCHAR(80) NOT NULL,            -- e.g. "Binance hot 14"
  source        VARCHAR(16) NOT NULL,            -- 'curated' | 'heuristic' | 'etherscan'
  confidence    SMALLINT NOT NULL DEFAULT 100,   -- 0-100
  updated_at    TIMESTAMPTZ NOT NULL
);
```

Categories:

- `cex` — exchange hot wallets, deposit addresses
- `dex_router` — Uniswap V2/V3 router, 1inch, Curve registry, Balancer vault
- `dex_pool` — canonical pools for major pairs (USDC/WETH, DAI/USDC, etc.)
- `lending` — Aave V3 Pool, Compound V3 Comet, Sky DAI Join, Spark, Morpho
- `staking` — Beacon deposit contract, Lido stETH submit, Rocket Pool deposit, Coinbase, Frax, Mantle, Swell, Stader
- `lrt` — ether.fi mint, Renzo, Kelp, Puffer, Swell-LRT, Eigenpie
- `bridge_l1` — canonical L1 bridge inbox addresses (Arbitrum, Base, OP, zkSync, Linea, Scroll)
- `bridge_l2_gateway` — L2 token gateways (USDC, USDT, WETH per chain)
- `hyperliquid` — Hyperliquid bridge contracts (mostly Arbitrum-side, see Layer 2)
- `oracle` — Chainlink, Pyth, RedStone aggregators (rare in flow but worth labeling)
- `mev` — known MEV bot addresses (Flashbots searcher hot wallets)
- `treasury` — known DAO/protocol treasuries
- `smart_contract` — labeled but uncategorized contract (low-priority catch-all)

**Seed:** ~250 hand-curated addresses across the categories above. The CEX
list is the most important — Etherscope's existing exchange-flow logic
already has Binance/Coinbase/OKX/Bybit hot-wallet coverage; we generalize it.

**Heuristic import (later, optional):** any contract that emits >Nk ERC20
Transfer events as `from` over a 30-day window is a hot-wallet candidate;
manual review queue. Not v4-day-one.

### Layer 2 — Live flow classifier on the realtime listener

The realtime listener (`backend/app/realtime/`) already runs against the
self-hosted Geth WS feed. On every persisted whale transfer (and the
threshold-free stable transfers feeding `realtime_volume`), look up
`from_addr` and `to_addr` against `address_label` and tag the row:

```sql
ALTER TABLE transfers          ADD COLUMN flow_kind VARCHAR(24);
ALTER TABLE pending_transfers  ADD COLUMN flow_kind VARCHAR(24);
```

`flow_kind` enum:

- `wallet_to_cex` / `cex_to_wallet` — directly visible from labels
- `wallet_to_dex` / `dex_to_wallet` — same
- `lending_deposit` / `lending_withdraw`
- `staking_deposit` / `staking_unstake`
- `bridge_l2`
- `hyperliquid_in` / `hyperliquid_out` — see Hyperliquid wrinkle below
- `wallet_to_wallet` — default when neither side has a label

**Backfill:** one-shot job after the column lands, scoring the historical
`transfers` table against the seeded labels.

**Edge cases:**
- Contract-to-contract transfers (e.g. a DEX pool sends to a CEX deposit
  during a routed swap) — pick the more impactful side (CEX > DEX > everything
  else), or tag both sides as `composite` (TBD during build).
- Unknown contract on either side → `wallet_to_wallet` is the default
  fall-through. Better to under-classify than mislabel.

### Layer 3 — UX

Built in priority order matching the user's stated weighting:

**3a — CEX net-flow tile** (the 20× signal):

Top-of-Overview tile showing 1h / 24h ETH + stablecoin net flow into CEXes.
Big number, color-coded — green = exchange outflow (bullish), red = exchange
inflow (bearish). Optional drill-down per exchange (Binance, Coinbase, etc.).

**3b — Whale-panel filter chips:**

Multi-select pill row above the existing asset filter on `WhaleTransfersPanel`:

```
[→ Exchange]  [← Exchange]  [DEX]  [Lending]  [Staking]  [Bridge]  [Hyperliquid]  [Wallet ↔ Wallet]
```

URL-persisted (extends the existing `?asset=` pattern).
**Default = both CEX legs only** — matches the user's stated 20× priority and
solves the "too much information" problem out of the box.

Each table row gets a small `flow_kind` badge.

**3c — DeFi / Staking / Bridge net-flow tiles:**

Same shape as the CEX tile, lower in the page hierarchy. One tile per
category. Composes with the existing v3-bridge-flows panel.

## Hyperliquid wrinkle

User wants Hyperliquid leveraged-position visibility. Reality:
**Hyperliquid runs on Arbitrum, not Ethereum mainnet.** Its canonical
bridge contract lives on Arbitrum. From mainnet alone we cannot see
deposits to Hyperliquid directly.

Two options, both real:

- **(a) Proxy signal.** Tag mainnet→Arbitrum-canonical-bridge transfers
  whose ultimate destination matches Hyperliquid intent (e.g. funded
  shortly after by an Arbitrum→Hyperliquid bridge call). Cheap, lower
  fidelity. Ships under the existing realtime listener.
- **(b) High fidelity.** Add an Arbitrum L2 listener — separate WS
  connection to an Arbitrum node (self-hosted is ideal, third-party
  RPC acceptable as a fallback). Watch Hyperliquid bridge events
  directly. New infra, but the precision matches the user's
  intent cleanest.

**Default plan:** ship (a) under the live-flow-classifier first, evaluate
whether (b)'s precision is worth the infra add. Treat (b) as a separate
kanban card.

## AI layer (genuinely later)

**Wallet performance scoring:** extends the existing
`smart_money_leaderboard` (today: 30d realized PnL on WETH only) with:
- 30 / 90 / 365d FIFO PnL
- Win rate (txs where realized PnL > 0 / total)
- Volume rank
- Combined "smart-money score" (weighted)

**Visual importance weighting:** in `WhaleTransfersPanel`, render
high-score wallets prominently — bigger text, stronger color, sticky
highlight. A wallet with 80% win rate moving $5M ranks above a fresh
wallet moving $20M. Solves the user's explicit "20M loser dominates the
panel" anti-pattern.

**Market regime classifier:** train a model on aggregate features
(CEX flow direction, OI, funding, lending utilization, staking flows,
on-chain volume, smart-money score distribution) to label regime:
accumulation / distribution / euphoria / capitulation. Surface as a
single tile on Overview with model confidence. Ships only after Layers
1-3 give it the input feature set.

## Dependency graph

```
1  address-label-registry     ◀── nothing else works without this
2  live-flow-classifier       ◀── depends on 1
3  whale-flow-filter-ui       ◀── depends on 2
4  cex-net-flow-tile          ◀── depends on 2 (parallel to 3)
5  defi-net-flow-tiles        ◀── depends on 2
6  hyperliquid-bridge         ◀── independent infra; later
7  wallet-performance-score   ◀── independent; later
8  wallet-importance-weight   ◀── depends on 7
9  market-regime-classifier   ◀── depends on multiple; later
```

## What this does NOT do

- Doesn't replace the existing exchange-flows panel (which is Dune-sourced
  hourly aggregates). v4 adds **live** classification on top of the same
  underlying signal.
- Doesn't replace `wallet_clusters` (which is on-demand Etherscan-backed
  per-address profile data). v4's address_label is curated/heuristic
  *contract* labels, not per-wallet profiles. They coexist.
- Doesn't address mobile UX, light mode, or panel polish. Those stay on
  the existing `polish` track.

## Open design questions (resolve at build time)

1. **Backfill approach for `flow_kind`:** worker job vs. one-off SQL? Worker
   job lets us re-run after label additions; SQL is faster.
2. **Composite-side classification:** when both `from` and `to` are labeled
   contracts (DEX pool → CEX), pick one or tag both? Pick-the-more-impactful
   feels right but needs validation against real flows.
3. **Confidence threshold:** at what `confidence` score does a heuristic
   label become trustworthy enough to drive UX? Initial proposal: ≥80
   for CEX, ≥60 for everything else.
4. **Hyperliquid (a) vs (b):** ship (a) and measure fidelity, or commit
   straight to (b)? Depends on how much Arbitrum-listener infra cost is
   acceptable.

## Vacation note

The user is going on vacation. Cards 1-5 should be self-contained enough
that the work can be picked up cold, in order, without needing further
input. Cards 6-9 should not be started until 1-5 are stable in production.
