# Etherscope — Deployment Guide (Railway)

Step-by-step runbook for taking this repo from zero to a live, always-on
Etherscope instance on [Railway](https://railway.app). ~30–60 minutes for the
first deploy.

> **When to use this guide:** no self-hosted Ethereum node (v1). Alchemy covers
> all RPC needs. If/when you add mempool or order-flow features, migrate to
> a Hetzner VPS — see `docs/deployment-hetzner.md` (TBD).

---

## 1. What gets deployed

Six Railway resources, all in one project:

| Service | Type | Source | Start command |
|---|---|---|---|
| `api` | Docker | `backend/` | `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"` |
| `worker` | Docker | `backend/` | `arq app.workers.arq_settings.WorkerSettings` |
| `realtime` | Docker | `backend/` | `python -m app.realtime.listener` |
| `frontend` | Docker | `frontend/` (uses `Dockerfile.prod`) | default (`nginx`) |
| `postgres` | Railway plugin | — | — |
| `redis` | Railway plugin | — | — |

`api`, `worker`, and `realtime` all share the single `backend/Dockerfile`; only
the start command differs.

---

## 2. Prerequisites

Have these ready before you click anything:

1. **Alchemy API key** — create an app on [dashboard.alchemy.com](https://dashboard.alchemy.com)
   (Ethereum mainnet). Free tier is fine.
2. **Dune API key** — [dune.com](https://dune.com) → Settings → API. Plus the
   three query IDs (see `docs/dune-setup.md`).
3. **Etherscan API key** — [etherscan.io/myapikey](https://etherscan.io/myapikey).
4. **Telegram bot** — optional but recommended. See `docs/telegram-setup.md`
   (takes ~5 minutes).
5. **Webhook signing secret** — generate one now:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
6. **GitHub** account linked to Railway (easier auto-deploys on push).

---

## 3. Create the Railway project

1. Sign in at [railway.app](https://railway.app) with GitHub.
2. **+ New Project** → **Deploy from GitHub repo** → select the Etherscope repo.
3. Railway will scan the repo — ignore its first suggestion. We're going to
   add services manually.

## 4. Add Postgres and Redis

In your new project:

1. **+ New** → **Database** → **Add PostgreSQL**. Leave defaults.
2. **+ New** → **Database** → **Add Redis**. Leave defaults.

Railway injects connection vars automatically. You'll reference them in step 6.

## 5. Add the three backend services

For each of `api`, `worker`, `realtime` do:

1. **+ New** → **GitHub Repo** → pick the repo again.
2. Open the new service's **Settings**.
3. **Source → Root Directory**: `backend`
4. **Build → Builder**: Dockerfile (auto-detected — confirm the path is
   `backend/Dockerfile`).
5. **Deploy → Start Command**: use the correct one from the table in §1.
6. **Service name**: rename to `api` / `worker` / `realtime`.
7. Only the `api` service needs a **public domain** — click **Settings →
   Networking → Generate Domain**. Copy the URL; you'll need it for the
   frontend build.

## 6. Environment variables

Open each backend service's **Variables** tab and paste these. You can click
**+ Reference** to pull values from the Postgres/Redis plugins instead of
copy-pasting passwords.

Minimum set (worker and realtime need the same vars as api):

```
# DB — use Railway references
POSTGRES_USER       → ${{Postgres.PGUSER}}
POSTGRES_PASSWORD   → ${{Postgres.PGPASSWORD}}
POSTGRES_DB         → ${{Postgres.PGDATABASE}}
POSTGRES_HOST       → ${{Postgres.PGHOST}}
POSTGRES_PORT       → ${{Postgres.PGPORT}}
REDIS_URL           → ${{Redis.REDIS_URL}}

# Keys
ALCHEMY_API_KEY     = …
DUNE_API_KEY        = …
ETHERSCAN_API_KEY   = …

# Dune query IDs (see docs/dune-setup.md)
DUNE_QUERY_ID_EXCHANGE_FLOWS     = …
DUNE_QUERY_ID_STABLECOIN_SUPPLY  = …
DUNE_QUERY_ID_ONCHAIN_VOLUME     = …
DUNE_SYNC_INTERVAL_MIN           = 240

# Whale thresholds
WHALE_ETH_THRESHOLD         = 500
WHALE_STABLE_THRESHOLD_USD  = 1000000

# Alerts
TELEGRAM_BOT_TOKEN       = …        # optional
TELEGRAM_CHAT_ID         = …        # optional
WEBHOOK_SIGNING_SECRET   = …        # 64 hex chars from step 2.5
ALERT_DEFAULT_COOLDOWN_MIN = 15

APP_ENV   = prod
LOG_LEVEL = INFO
```

The full template lives at `.env.production.example` in the repo root.

## 7. Add the frontend service

1. **+ New** → **GitHub Repo** → pick the repo.
2. **Settings → Source → Root Directory**: `frontend`
3. **Settings → Build → Dockerfile Path**: `Dockerfile.prod`
4. **Settings → Variables**:
   ```
   VITE_API_URL = <your api service's public URL>
   ```
   (the one you copied at the end of step 5)
5. **Settings → Networking → Generate Domain**. This is the URL you share.

Because `VITE_API_URL` is baked into the bundle at build time, changing it
requires a redeploy. Railway re-builds automatically when the variable
changes — no manual step.

## 8. Deploy order & first-run

Railway deploys in parallel. On first boot:

- `api` runs `alembic upgrade head` automatically (part of the start command),
  which creates all tables in the fresh Postgres.
- `worker` enqueues `backfill_price_history` and `sync_dune_flows` at startup.
- `realtime` connects to Alchemy and subscribes to `newHeads`.

Watch each service's **Deployments → Logs**. Expected log lines:

- `api`: `INFO:uvicorn.error:Application startup complete.`
- `worker`: `Starting worker for N functions` and periodic `cron:` runs.
- `realtime`: `starting realtime listener thresholds eth>=500.0 ...` then
  `subscribed to newHeads`.
- `frontend`: nginx access logs appear as you load the page.

## 9. Verify

- `https://<frontend-url>` → dashboard loads, price hero populates within ~30s.
- `https://<api-url>/api/health` → `{"status":"ok", "sources":[...]}`
- Create a test alert rule (Alerts panel → Rules → + New rule → `price_above`
  with threshold `1`). Within 60s you should see the event fire and (if
  Telegram is configured) receive a DM.

---

## 10. Cost expectations

Typical monthly Railway bill for this workload:

| Resource | ~$/mo |
|---|---|
| api (always-on) | 3–5 |
| worker (always-on) | 3–5 |
| realtime (always-on) | 3–5 |
| frontend (nginx) | 0–2 |
| Postgres (512 MB) | 5 |
| Redis (256 MB) | 3 |
| **Total** | **~$17–25** |

Your first `$5` of usage per month is covered by the Hobby plan fee itself.

---

## 11. Operations

- **Updates**: `git push` to main → Railway rebuilds and rolls every service.
  Use a feature branch + PR + merge cycle for safer control.
- **Migrations**: `alembic upgrade head` runs on every `api` start. For manual
  runs use `railway run --service api alembic upgrade head`.
- **Viewing data**: `railway connect Postgres` opens a `psql` shell with the
  managed connection string pre-filled.
- **Backups**: Railway's Postgres plugin snapshots nightly on paid plans; for
  belt-and-braces, schedule a daily `pg_dump` → S3-compatible object store.
- **Scaling**: all three backend services are stateless except for the realtime
  listener — do **not** run two replicas of `realtime` against the same DB
  (they'd double-write). `api` and `worker` can be replicated.

---

## 12. Key security checklist

- [ ] Rotate any key that was ever pasted into chat, a PR comment, or this
      repo's git history — **including the Alchemy key shared in the dev
      conversation**.
- [ ] Verify Postgres and Redis are **not** exposed to the public internet
      (Railway's managed plugins default to internal-only — confirm in their
      Networking tab).
- [ ] `WEBHOOK_SIGNING_SECRET` is a fresh 32+ byte random value.
- [ ] Telegram bot token is stored only in Railway vars, not in `.env` files
      committed locally.
- [ ] Public `api` domain has no authentication yet — if you share the URL
      with anyone else, add a minimal auth layer first (see
      `docs/v1-status.md` → Improvements).

---

## 13. Common issues

| Symptom | Cause / fix |
|---|---|
| Frontend loads but all panels say "unavailable" | `VITE_API_URL` wrong or api service is crashed. Check CORS — if you see a browser console CORS error, enable CORS on the api (not configured yet in v1; see Improvements). |
| Alerts never fire | Check `worker` logs for `cron:evaluate_alerts`. If missing, the Redis connection string is wrong. |
| `realtime` idles and logs `ALCHEMY_API_KEY not set` | Variable missing or empty on the realtime service. Add it and redeploy. |
| Whale panel empty after an hour | Likely correct — 500 ETH / $1M transfers are sparse. Drop thresholds (`WHALE_ETH_THRESHOLD=50`, `WHALE_STABLE_THRESHOLD_USD=100000`) to sanity-check end-to-end. |
| Health says `degraded` | Open the topbar "Systems nominal" dropdown. The red dot tells you which source is stale. Usually Binance or Alchemy — check the relevant service's logs. |

---

## 14. Rolling back

Railway keeps the last 30 days of deployments per service. **Deployments →
Redeploy** on any previous deployment rolls back instantly. Schema migrations
are *not* auto-reverted — if a bad migration ships, create a new Alembic
revision to undo it rather than pointing the code at an older image.
