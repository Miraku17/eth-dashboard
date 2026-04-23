# Ethereum Trading & On-Chain Analytics Dashboard — Design

**Date:** 2026-04-23
**Status:** Approved (v1 scope)
**Owner:** Solo developer / personal use

## Goal

A professional dashboard for analyzing Ethereum market and on-chain data. Enable real-time detection of market movements, transparency into whale/smart-money behavior, and informed trading decisions. Single-user tool, cost-sensitive (<~$50/month target).

## Non-Goals

- Multi-tenant SaaS, auth/billing, external users
- Sub-second / mempool front-running latency
- Institutional compliance, audit trails, SOC2
- Mobile app (responsive web is enough)

## v1 Scope (this document)

1. ETH price & volume across multiple timeframes (1m – 365d)
2. On-chain transaction volume (ETH + major stablecoins)
3. Stablecoin inflow/outflow monitoring
4. Exchange flows (CEX in/out) via labeled addresses
5. Whale wallet tracking — user-defined watchlist with real-time transfer alerts
6. User-defined alerts engine (threshold rules, Telegram + email delivery)
7. Network activity (tx count, gas)

## Out of Scope (deferred)

- **v2:** DEX trader leaderboard (top ~500), order-flow pressure, large-vs-small tx volume structure
- **v3:** Wallet clustering (graph analytics), derivatives integration (funding, OI), backtesting

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React + Vite frontend                                  │
│  TradingView Lightweight Charts, TanStack Query, shadcn │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + WebSocket
┌──────────────────────┴──────────────────────────────────┐
│  FastAPI (Python 3.12)                                  │
│  REST: /api/price /api/flows /api/whales /api/alerts    │
│  WS:   live transfers, alert fan-out                    │
└───┬─────────────┬────────────┬────────────┬─────────────┘
    │             │            │            │
┌───▼────┐  ┌─────▼────┐  ┌────▼────┐  ┌────▼─────┐
│Postgres│  │  Redis   │  │ arq     │  │ realtime │
│(history│  │(cache +  │  │workers  │  │ listener │
│ +state)│  │ pubsub)  │  │(Dune,   │  │(Alchemy  │
│        │  │          │  │ CEX)    │  │ WS)      │
└────────┘  └──────────┘  └─────────┘  └──────────┘
```

### Components

**Frontend (`/frontend`)**
- React 18 + Vite + TypeScript
- TanStack Query for server state
- TradingView Lightweight Charts for price/volume
- Recharts for secondary panels (flows, network activity)
- Tailwind + shadcn/ui for design system
- Single-page app; responsive but desktop-first

**API (`/backend/api`)**
- FastAPI, Pydantic v2
- REST endpoints for dashboard reads (paginated, cached)
- WebSocket endpoint `/ws` for live updates (server pushes JSON events over Redis pub/sub)
- No auth in v1 (bind to localhost or Cloudflare tunnel with access policy)

**Realtime listener (`/backend/realtime`)**
- Long-running process, one per chain
- Connects to Alchemy WebSocket, subscribes to new blocks + `alchemy_pendingTransactions` for watched addresses
- Decodes ERC-20 Transfer logs for watched whale wallets + global large-transfer threshold
- Publishes events to Redis (`ch:transfers`, `ch:alerts`)

**Worker pool (`/backend/workers`)**
- `arq` (Redis-backed task queue)
- Scheduled jobs:
  - `sync_price` (every 60s) — CoinGecko + Binance klines
  - `sync_dune_flows` (every 5m) — refresh materialized Dune query results (exchange flows, stablecoin flows, on-chain tx volume)
  - `sync_network_activity` (every 60s) — gas, tx count via RPC
  - `evaluate_alerts` (triggered on new data) — check rules, publish triggers
- Backfill jobs runnable on demand

**Data layer**
- **Postgres 16**: time-series tables (price, flows, network activity), whale watchlist, alert rules, alert history
- **Redis 7**: LRU cache for API reads, pub/sub for realtime fan-out, arq queue

## Data Sources

| Source | Purpose | Cost | Latency |
|---|---|---|---|
| Alchemy (free tier) | RPC + WebSocket, watched-wallet transfers | $0 | real-time |
| Dune Analytics | Labeled flows, CEX flows, stablecoin flows, DEX data | $0 free / $49 analyst | ~5m |
| CoinGecko | Price, market cap | $0 | ~1m |
| Binance public API | OHLCV, volume | $0 | ~1m |
| Etherscan | Address labels, metadata | $0 | on-demand |

Known limits: Alchemy free tier = 300 compute units/sec; Dune free = limited query executions/day. Plan sync cadences around these; upgrade Dune to Analyst ($49/mo) if hit ceiling.

## Data Flow

**Read path (dashboard loads chart):**
1. Frontend → `GET /api/price?tf=1h&range=30d`
2. FastAPI checks Redis cache → hit: return; miss: query Postgres → cache → return

**Write path (price sync):**
1. arq worker fires `sync_price` every 60s
2. Fetches from CoinGecko + Binance, upserts into `price_candles`
3. Invalidates relevant Redis cache keys
4. Publishes `ch:price_updated` → WS clients refetch

**Realtime path (whale transfer):**
1. Alchemy WS emits log for watched address
2. Listener decodes, writes to `transfers` table, publishes `ch:transfers`
3. API WS broadcasts to connected clients
4. `evaluate_alerts` triggered → matches rules → sends Telegram/email + writes `alert_events`

## Database Schema (v1, outline)

- `price_candles(symbol, timeframe, ts, open, high, low, close, volume)` — composite PK
- `onchain_volume(asset, ts_bucket, tx_count, usd_value)`
- `exchange_flows(exchange, direction, asset, ts_bucket, usd_value)`
- `stablecoin_flows(asset, direction, ts_bucket, usd_value)`
- `network_activity(ts, tx_count, gas_price_gwei, base_fee)`
- `watched_wallets(address, label, added_at, notes)`
- `transfers(tx_hash, log_index, block_number, ts, from_addr, to_addr, asset, amount, usd_value)` — indexed on `from_addr`, `to_addr`, `ts`
- `alert_rules(id, name, rule_type, params_jsonb, channels_jsonb, enabled)`
- `alert_events(id, rule_id, fired_at, payload_jsonb, delivered_jsonb)`

## Alert Rule Types (v1)

- `large_transfer` — any tx ≥ $X in asset Y
- `watched_wallet_activity` — any transfer in/out of wallets W
- `exchange_netflow_threshold` — net flow to/from CEX X exceeds $Y over period Z
- `price_change` — price move ≥ X% over window Y
- `gas_spike` — gas price above threshold

Delivery: Telegram bot (primary — free, instant), email via Resend (secondary). Logged with timestamp + delivery status.

## Deployment

- Docker Compose: `api`, `realtime`, `worker`, `frontend` (static build served by Caddy), `postgres`, `redis`
- Single VPS (Hetzner CX22, ~$8/mo) or Railway
- Postgres dumps to S3/R2 nightly (`pg_dump` + cron)
- Secrets via `.env` file, never committed
- Access: bind API to localhost + Cloudflare Tunnel with Access policy (email allowlist), OR Tailscale

## Cost Estimate

- VPS: $8/mo (Hetzner) – $20/mo (Railway)
- Alchemy: $0 (free tier sufficient for 1 user)
- Dune: $0 free tier to start, upgrade to $49/mo if needed
- CoinGecko/Binance/Etherscan: $0
- Resend email: $0 (3k emails/mo free)
- Telegram: $0
- **Total v1: $8–$30/mo**, scaling to ~$70/mo if Dune upgrade needed

## Testing Strategy

- Unit tests: data transforms, alert rule evaluation, Dune response parsers (`pytest`)
- Integration tests: API endpoints against a test Postgres (`pytest` + `testcontainers`)
- Contract tests: recorded Dune/CoinGecko responses via `vcrpy`
- Manual smoke test checklist for UI after each release
- No E2E automation in v1 (solo tool, cost/benefit doesn't justify)

## Milestones

1. **M0 — Skeleton (week 1):** repo layout, Docker Compose, Postgres schema, FastAPI hello-world, frontend scaffold
2. **M1 — Price/volume (week 2):** CoinGecko/Binance sync + chart panel
3. **M2 — On-chain flows (week 3):** Dune integration + exchange/stablecoin flow panels
4. **M3 — Whale tracking (week 4):** watchlist UI + Alchemy WS listener + live transfers panel
5. **M4 — Alerts (week 5):** rule CRUD + evaluator + Telegram delivery
6. **M5 — Polish & network activity (week 6):** gas/tx count panel, UX polish, backup automation

## Open Questions (to resolve during planning)

- Do we want multi-chain from day one (ETH L1 only v1, add L2s later) or just ETH L1? *Assumption: ETH L1 only for v1.*
- Exact whale-transfer USD threshold for the global alert (default $1M suggested).
- Telegram bot setup: user creates their own bot and provides token during onboarding.
