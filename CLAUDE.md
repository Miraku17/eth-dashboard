# CLAUDE.md

**Etherscope** — Ethereum trading & on-chain analytics dashboard. Solo/personal tool, cost-sensitive.

## What this project is

Professional dashboard for analyzing ETH market + on-chain data: price/volume, stablecoin flows, exchange flows, whale tracking, user-defined alerts. Later phases add DEX smart-money tracking and wallet clustering.

**Design doc:** `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md` — authoritative source of truth for scope and architecture. Read it before making non-trivial decisions.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, `arq` (Redis queue), `web3.py`, `dune-client`, `httpx`, `pandas`
- **Frontend:** React 18 + Vite + TypeScript, TanStack Query, TradingView Lightweight Charts, Recharts, Tailwind, shadcn/ui
- **Data:** Postgres 16, Redis 7
- **Deploy:** Docker Compose on a single VPS (Hetzner target)

## Data sources

- **Alchemy (free tier):** JSON-RPC + WebSocket for real-time block/transfer events
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

## Scope discipline

The design doc's v1 scope is fixed. Do **not** implement v2/v3 features (DEX leaderboard, order flow, clustering, derivatives, backtesting) until v1 is shipped and stable. If a change seems to pull in v2+ work, flag it instead of expanding scope.

## Milestone status

- M0 ✅ scaffold (docker compose, schema, health, React/Vite)
- M1 ✅ ETH price & volume (Binance klines sync → `/api/price/candles` → candlestick+volume chart with 1m/5m/15m/1h/4h/1d selector)
- M2 ✅ on-chain flows (3 Dune queries → `/api/flows/{exchange,stablecoins,onchain-volume}` → panels). Requires Dune query IDs in `.env` (see `docs/dune-setup.md`); panels show "no data yet" gracefully when unset.
- M3 ✅ whale tracking — Alchemy WS listener persists ETH + USDT/USDC/DAI transfers above threshold to `transfers`; `/api/whales/transfers` exposes them with CEX labels; live-refreshing panel. Needs `ALCHEMY_API_KEY`; thresholds via `WHALE_ETH_THRESHOLD` / `WHALE_STABLE_THRESHOLD_USD`.
- M4 ✅ alerts engine — arq cron `evaluate_alerts` every minute; 6 rule types (price above/below/change%, whale transfer, whale→exchange, exchange netflow); Telegram + HMAC-signed webhook delivery; `/api/alerts/{rules,events}` CRUD; tabbed dashboard panel (Events / Rules) with form-based create/edit + toast on fire. See `docs/telegram-setup.md`.
- M5 ✅ network activity + polish — realtime listener writes per-block gas/base-fee/tx-count to `network_activity`; `/api/network/{summary,series}` endpoints; dashboard panel with gas + tx-count charts; `/api/health` reports per-source freshness; Topbar dropdown shows data lag per source; ErrorBoundary wraps every panel.

**v1 complete.** Roadmap above is fully ✅. Next natural steps are deployment (Hetzner) and v2 scoping (smart-money tracking, clustering, mempool — each larger than all of v1 combined, plan with client first).

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
