# Etherscope

Ethereum trading & on-chain analytics dashboard.

Live price/volume chart, labeled on-chain flows (exchange, stablecoin, volume),
real-time whale transfers with CEX annotations, a 6-rule-type alerts engine
(Telegram + signed webhooks), and network-state panels — all in one desk.

See `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md` for
the full design, or `docs/v1-status.md` for the shipped-vs-pending breakdown.

## Quick start (local)

```bash
cp .env.example .env          # fill in ALCHEMY_API_KEY + Dune query IDs
docker compose up --build
# API:      http://localhost:8000/api/health
# Frontend: http://localhost:5173
```

## Deploy

- **Railway** (managed, ~$20/mo, recommended for v1): `docs/deployment.md`
- **Hetzner VPS** (self-hosted, ~€10/mo, worth it once you add a node):
  TBD, sketch in deployment.md §Hetzner

## Layout

- `backend/` — FastAPI, arq worker, realtime Alchemy WebSocket listener
- `frontend/` — React + Vite + TradingView Lightweight Charts + Recharts
- `docs/` — specs, plans, deployment & operational notes
