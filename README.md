# Eth — On-Chain Analytics Dashboard

Personal Ethereum trading & on-chain analytics dashboard.

See `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md` for the full design.

## Quick start

```bash
cp .env.example .env
docker compose up --build
# API:      http://localhost:8000/health
# Frontend: http://localhost:5173
```

## Layout

- `backend/` — Python (FastAPI, workers, realtime listener)
- `frontend/` — React + Vite
- `docs/` — specs and plans
