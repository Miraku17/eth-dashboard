# CLAUDE.md

**Etherscope** — Ethereum trading & on-chain analytics dashboard. Solo/personal tool, cost-sensitive.

## What this project is

Professional dashboard for analyzing ETH market + on-chain data: price/volume, stablecoin flows, exchange flows, whale tracking, user-defined alerts, derivatives, DEX order flow, smart-money leaderboard, mempool whale tracking. v3 (planned) adds DeFi & staking layer.

**Design doc:** `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md` — authoritative source of truth for scope and architecture. Read it before making non-trivial decisions.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, `arq` (Redis queue), `web3.py`, `dune-client`, `httpx`, `pandas`
- **Frontend:** React 18 + Vite + TypeScript, TanStack Query, TradingView Lightweight Charts, Recharts, Tailwind, shadcn/ui
- **Data:** Postgres 16, Redis 7
- **Deploy:** Docker Compose on a single VPS (Hetzner target)

## Data sources

- **Self-hosted Geth + Lighthouse:** primary JSON-RPC + WebSocket source; required for `newPendingTransactions` (mempool) and beacon-chain reads. Configure via `ALCHEMY_WS_URL` (e.g. `ws://172.17.0.1:8546`).
- **Alchemy (free tier):** fallback WS endpoint when no self-hosted node is configured (used in dev / cheap deploys; mempool unavailable on free tier).
- **Dune Analytics:** labeled flow queries (exchange flows, stablecoin flows, DEX data) — ~5-minute freshness
- **CoinGecko + Binance public API:** price / OHLCV
- **Etherscan:** address labels / metadata

Cache aggressively in Redis. Respect free-tier rate limits; schedule syncs accordingly.

## Repository layout (target)

```
backend/
  api/         FastAPI app, routers, schemas
  workers/     arq tasks (price sync, Dune sync, alert eval)
  realtime/    Alchemy WS listener
  core/        shared models, db, config
  tests/
frontend/
  src/
docs/
  superpowers/specs/
docker-compose.yml
```

## Conventions

- Python: `ruff` + `ruff format`, type hints everywhere, `pytest` for tests
- Frontend: ESLint + Prettier, functional components, hooks over classes
- Never commit secrets — use `.env` (gitignored); `.env.example` documents required keys
- Prefer existing patterns in the codebase over introducing new ones

## Auth

Single-account session login (argon2 password, Redis-backed HttpOnly cookies)
gates the dashboard UI and all protected API routes. `/api/health` stays
public. Operator setup: see `docs/auth-setup.md`. Design: see
`docs/superpowers/specs/2026-04-30-login-auth-design.md`.

## Scope discipline

The design doc's v1 scope is fixed. Do **not** implement v2/v3 features (DEX leaderboard, order flow, clustering, derivatives, backtesting) until v1 is shipped and stable. If a change seems to pull in v2+ work, flag it instead of expanding scope.

## Milestone status

- M0 ✅ scaffold (docker compose, schema, health, React/Vite)
- M1 ✅ ETH price & volume (Binance klines sync → `/api/price/candles` → candlestick+volume chart with 1m/5m/15m/1h/4h/1d selector)
- M2 ✅ on-chain flows (3 Dune queries → `/api/flows/{exchange,stablecoins,onchain-volume}` → panels). Requires Dune query IDs in `.env` (see `docs/dune-setup.md`); panels show "no data yet" gracefully when unset.
- M3 ✅ whale tracking — Alchemy WS listener persists ETH + USDT/USDC/DAI transfers above threshold to `transfers`; `/api/whales/transfers` exposes them with CEX labels; live-refreshing panel. Needs `ALCHEMY_API_KEY`; thresholds via `WHALE_ETH_THRESHOLD` / `WHALE_STABLE_THRESHOLD_USD`.
- M4 ✅ alerts engine — arq cron `evaluate_alerts` every minute; 6 rule types (price above/below/change%, whale transfer, whale→exchange, exchange netflow); Telegram + HMAC-signed webhook delivery; `/api/alerts/{rules,events}` CRUD; tabbed dashboard panel (Events / Rules) with form-based create/edit + toast on fire. See `docs/telegram-setup.md`.
- M5 ✅ network activity + polish — realtime listener writes per-block gas/base-fee/tx-count to `network_activity`; `/api/network/{summary,series}` endpoints; dashboard panel with gas + tx-count charts; `/api/health` reports per-source freshness; Topbar dropdown shows data lag per source; ErrorBoundary wraps every panel.

**v1 complete.**

## v2 status

- v2-derivatives ✅ OI + funding rates for ETH perp across Binance/Bybit/OKX/Deribit.
- v2-order-flow ✅ Dune `dex.trades` aggregates WETH buy vs sell pressure across major DEXes, persists hourly to `order_flow`; `/api/flows/order-flow` endpoint; dashboard panel with buy/sell/net tiles + signed-stacked bar + net line. Runs on 8h cadence to stay within Dune free-tier credit budget. Requires `DUNE_QUERY_ID_ORDER_FLOW` in `.env` (SQL at `backend/dune/order_flow.sql`).
- v2-smart-money-leaderboard ✅ Daily Dune refresh of top 50 ETH DEX traders by 30d realized PnL on WETH; FIFO engine runs in Python over `dex.trades` candidate rows; persists snapshot per run to `smart_money_leaderboard`; `/api/leaderboard/smart-money` endpoint; dashboard panel. Requires `DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD` in `.env` (SQL at `backend/dune/smart_money_leaderboard.sql`).
- v2-mempool ✅ Self-hosted Geth + Lighthouse node; `backend/app/realtime/mempool.py` subscribes to `newPendingTransactions` concurrently with `newHeads`; whale-sized pending txs persist to `pending_transfers` (auto-cleaned at 30m or on confirm); `/api/whales/pending` endpoint; "Pending" section atop `WhaleTransfersPanel`. Spec: `docs/superpowers/specs/2026-04-28-mempool-tracking-design.md`.
- v2-volume-structure ✅ Hourly Dune refresh bucketing ETH DEX volume into retail (<$10k) / mid ($10k–100k) / large ($100k–1M) / whale (≥$1M); persists to `volume_buckets`; `/api/flows/volume-buckets` endpoint; `VolumeStructurePanel` with USD/% mode toggle. Requires `DUNE_QUERY_ID_VOLUME_BUCKETS` in `.env` (SQL at `backend/dune/volume_buckets.sql`).
- v2-wallet-clustering ✅ On-demand wallet drawer (Etherscan-backed, sync, 7d Postgres `wallet_clusters` cache); shared gas-funder + same-CEX-deposit heuristics with public-funder denylist (CEX hot wallets, Tornado, bridges) suppressing false positives; clickable addresses across whale + smart-money panels via shared `<AddressLink>` + Zustand drawer state; daily 03:11 UTC purge cron drops rows past the 7-day grace window. Requires `ETHERSCAN_API_KEY` in `.env`. Spec: `docs/superpowers/specs/2026-05-01-wallet-clustering-design.md`.
- v2-wallet-profile ✅ Wallet drawer now renders a full profile in one fetch: 30d ETH balance area chart (`wallet_balance_history` table populated lazily via JSON-RPC `eth_getBalance` on the self-hosted Geth archive node, ~30 calls in batches of 5 on first lookup; today's row recomputed each fetch), 7d net-flow bar chart from existing `transfers`, top 5 counterparties (30d), last 15 whale moves involving the address, plus the existing cluster + linked-wallets sections. New endpoint `GET /api/wallets/{address}/profile`. Configure `ALCHEMY_HTTP_URL=http://172.17.0.1:8545` in `.env` (or omit — falls back to Alchemy if `ALCHEMY_API_KEY` is set, or returns the profile without balance data if neither is configured).

**v2 complete.**

## UI polish

- Live chart ✅ Direct browser-to-Binance WebSocket (combined `@trade` + `@kline_<tf>` streams) drives the price-hero ticker and in-place candle updates via `series.update()`; backend wraps `/api/price/candles` in a 60s Redis cache for the bootstrap path. Spec: `docs/superpowers/specs/2026-05-01-live-chart-ws-design.md`.
- Customizable overview ✅ React Router 4-page split (`Overview · Markets · Onchain · Mempool`); overview supports drag-to-reorder, add/remove, and bento-grid resize (S/M/L/Full → 1/2/3/4 cols) via `dnd-kit/sortable` + a 4-col CSS grid, persisted to LocalStorage (schema v2); category pages are fixed-in-code, derived from a single `lib/panelRegistry.ts`. Desktop only (`≥md`); mobile renders a clean default stack. Specs: `docs/superpowers/specs/2026-05-01-customizable-layout-design.md`, `docs/superpowers/specs/2026-05-01-bento-grid-resize-design.md`.
- Panel-responsive content ✅ `@tailwindcss/container-queries` plugin + `<PanelShell>` wraps every panel in an `@container` div so inner Tailwind classes (`@xs:` / `@sm:` / `@md:` / `@2xl:`) react to the panel's own rendered width rather than the viewport. v1 ships narrow-mode passes for the 5 most pinch-sensitive panels (WhaleTransfers, SmartMoneyLeaderboard, AlertEvents, NetworkActivity, PriceHero); other 8 get the foundation only. Spec: `docs/superpowers/specs/2026-05-01-panel-responsive-design.md`.

## Environment note

Local ISP (dev machine) DNS-intercepts `api.binance.com` and other crypto-exchange domains, returning a fake "blocking-page-authority" cert. `docker-compose.yml` works around this by pinning container DNS to 1.1.1.1/8.8.8.8. In production (Hetzner/Railway) this override is harmless; remove it only if resolver performance matters.

## Commands

- `make up` — start the full stack (postgres, redis, api, worker, realtime, frontend)
- `make down` — stop stack
- `make logs` — tail logs
- `make migrate` — run alembic migrations inside the api container
- `make backend-test` — run pytest (uses testcontainers for DB)
- `make frontend-build` — production build of the frontend
- `make lint` — ruff + eslint

### Local development notes

- Backend Python 3.12 venv at `backend/.venv` (managed via `uv`). Activate with `source backend/.venv/bin/activate` or use `.venv/bin/python` directly.
- Frontend Node 20; deps installed under `frontend/node_modules`.
- Host: `http://localhost:8000/api/health` (API), `http://localhost:5173` (frontend).
