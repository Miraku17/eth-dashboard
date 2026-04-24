# Etherscope — v1 Status

Snapshot of what is shipped, what is intentionally out of scope, and where the
realistic improvement opportunities are.

---

## What's in v1

### M0 — Scaffold
- Docker Compose stack: Postgres 16, Redis 7, FastAPI, arq worker, realtime
  listener, React + Vite frontend
- Alembic migrations; single initial revision creates all v1 tables
- Health endpoint stub; CI-ready `make` targets (`up`, `down`, `logs`,
  `migrate`, `backend-test`, `frontend-build`, `lint`)

### M1 — ETH price & volume
- Binance 1m/5m/15m/1h/4h/1d klines synced into `price_candles`
- Worker job backfills history on first boot and keeps the 1m stream fresh
  every minute
- `/api/price/candles` endpoint
- Dashboard candlestick + volume chart (TradingView Lightweight Charts) with
  timeframe selector, OHLC / volume hover legend, colored-by-direction
  change readout

### M2 — On-chain flows
- Three Dune queries synced every 4h (configurable):
  - Exchange inflow/outflow per CEX
  - Stablecoin supply delta (mint - burn)
  - On-chain transfer volume by asset
- `/api/flows/{exchange,stablecoins,onchain-volume}` endpoints
- Dashboard panels with `24h / 48h / 7d / 30d` range selector; graceful
  "no data yet" state when Dune query IDs aren't configured

### M3 — Whale tracking
- Realtime listener subscribes to Alchemy `newHeads`; for each block it pulls
  full transactions and ERC-20 Transfer logs for USDT/USDC/DAI
- Transfers above threshold (ETH ≥ 500, stables ≥ $1M default) persisted to
  `transfers` with per-tx dedup
- `/api/whales/transfers` endpoint with asset + time-window filter
- Dashboard table with asset badges, amber-pilled CEX labels (Binance,
  Coinbase, Kraken, OKX, Bitfinex, Bybit), Etherscan tx deeplinks, live
  15-second refresh

### M4 — Alerts engine
- Six rule types evaluated on a 1-minute cron:
  `price_above` / `price_below` / `price_change_pct` /
  `whale_transfer` / `whale_to_exchange` / `exchange_netflow`
- Cooldown gate for aggregate rules; per-transfer dedup for whale rules
- Delivery: **Telegram** (single bot) and **HMAC-SHA256 signed webhooks**
  (`X-Etherscope-Signature: sha256=…`)
- `/api/alerts/rules` full CRUD with discriminated-union Pydantic validation
- `/api/alerts/events` event feed joined with rule names
- Dashboard panel with **Events / Rules** tabs; form-based create/edit modal
  with per-type fields; real-time toast on every new fire

### M5 — Network activity + v1 polish
- Realtime listener writes per-block `network_activity` rows (gas price,
  base fee, tx count, block timestamp)
- `/api/network/summary` (latest + 15-min rolling avgs)
- `/api/network/series?hours=…` time series endpoint
- Dashboard panel with gas price area chart, tx-per-block line chart,
  and `1h / 6h / 24h / 7d` range picker
- `/api/health` now reports **per-source freshness** and flags stale
  sources; overall status degrades only when a *critical* source lags
- Topbar indicator is a dropdown showing lag per source
- `ErrorBoundary` wraps every panel — one bad endpoint can't blank the page

### Operational / design foundation (cross-cutting)
- Consistent UI primitives: `Card`, `Pill`, `Button`, `Modal`, `Toaster`,
  `StatTile`, `ErrorBoundary`
- Design system: Inter + JetBrains Mono, tabular-nums by default, custom
  surface/brand/up/down palette, ambient gradient background, subtle
  scrollbar
- 63 backend tests covering: parsers, evaluators (all 6 rule types), API
  integration, delivery (mocked httpx + HMAC), health, network endpoints

---

## What's intentionally **not** in v1

These were in the client brief but deferred to v2+; they are either much
larger than any v1 milestone or need infra we don't have yet.

- **Smart-money / top-500 DEX traders** — requires a dedicated Dune
  leaderboard query + backend aggregator. Plan with the client first.
- **Wallet clustering** — heuristics are doable on current data, but
  provider-grade clustering (Chainalysis/TRM) is licensed. Scope depends on
  the client's false-positive tolerance.
- **Order flow / mempool monitoring** — **needs a self-hosted Ethereum
  node**. Providers give very limited mempool visibility.
- **Derivatives data (OI, funding)** — not on-chain. Exchange APIs
  (Binance, Bybit, OKX, Deribit). Not hard, just scope creep for v1.
- **Multi-user, auth, ACLs** — single-user design. No login. See
  Improvements below if you plan to share the URL.
- **Historical replay / backtesting** — data is stored, but no backtest
  engine.

---

## Known limitations

1. **Alchemy free-tier rate limits.** ~300 M compute units / month is plenty
   for one user, but a public-shared dashboard could burn it in a week. Add
   server-side caching on the frontend-serving edge before going public.
2. **Dune free-tier execution budget** (~500/month) shared across all queries.
   The default sync cadence (4h × 3 queries = 18 executions/day ≈ 540/month)
   is right at the budget. If you add queries, raise `DUNE_SYNC_INTERVAL_MIN`
   or pay for a Dune tier.
3. **Address label list is hardcoded.** `app/realtime/labels.py` has ~25
   well-known CEX addresses. It ages — Binance adds new hot wallets; ours
   won't know about them until the file is updated. Acceptable for v1;
   replace with Etherscan label API / Dune lookup in v2.
4. **Realtime listener is single-instance.** Running two copies against the
   same DB would double-write (upsert on `ts` is idempotent for
   `network_activity`, but Transfer rows would cause write contention). If
   you ever want HA, add a leader election or put it behind a single-writer
   queue.
5. **No CORS config on the API.** The dev Vite proxy hides the problem. On
   Railway, the frontend and API are different origins — add
   `CORSMiddleware` to `app/main.py` and restrict it to your frontend's
   domain before public deploy.
6. **No authentication.** Anyone who hits the API can read data and write
   alert rules. Do **not** share the public URL before adding auth. See
   Improvements.

---

## Improvements (ordered by value ÷ effort)

### Cheap wins (hours each)

- **CORS middleware.** Ship before Railway deploy. ~20 lines in
  `app/main.py`; restrict origins to the frontend domain.
- **API token auth.** A single long-lived bearer token read from
  `API_AUTH_TOKEN` env, required on every non-public route. ~30 lines. Good
  enough for a personal tool.
- **Skeleton loaders** on the PriceHero, instead of `—` placeholders.
  Perceived load time ↓.
- **Mobile scroll affordance** on the whale + alerts tables (left/right
  shadow hint when horizontally scrollable).
- **Keyboard shortcut `n`** opens the "New rule" modal.
- **Wire the Topbar nav** (`Overview / Flows / Whales / Alerts`) to
  scroll-anchor each panel. Currently decorative only.
- **Address label refresh** — cron job that pulls the Etherscan / Dune CEX
  label list nightly and merges with the hardcoded set.
- **Lower default whale thresholds** — current 500 ETH / $1M filters out
  ~95% of interesting activity. `100 ETH / $250k` gives a much richer feed
  without drowning the user.

### Medium (a day each)

- **Per-rule UI for `cooldown_min`** that exposes it only for rule types
  where it applies (currently shown on all).
- **Alert history search** — the events feed caps at the last 24h via a
  range picker. Add `7d / 30d`, text filter, and a CSV export.
- **Sentry or equivalent error tracking.** Worker exceptions currently log
  to stdout only — invisible on Railway unless you tail logs.
- **Metrics surface.** Prometheus-format `/metrics` endpoint; Grafana Cloud
  has a free tier that scrapes over HTTPS.
- **Dune query caching tier.** Store the raw Dune response blob in Redis
  with a TTL; fall back to stale data if the latest execution fails.
- **Accessibility pass** (focus rings, aria labels on the toggle/buttons,
  keyboard traversal of the alerts tabs).
- **Test: frontend component tests** (Vitest + RTL) — none currently exist.

### Non-trivial (weeks)

- **v2 feature: smart-money leaderboard** via Dune. Separate Dune query
  ranks addresses by realized PnL over 30/90/365d; worker syncs into a new
  `trader_scores` table; panel shows top 100 with tag filters.
- **v2 feature: wallet clustering via heuristics.** Common-spend,
  funding-source, time-pattern. Needs an archive-RPC path or Dune's
  `transactions` table. Research project — scope with client first.
- **Self-hosted Ethereum node + mempool pipeline.** See
  `docs/deployment-hetzner.md` (TBD) when this becomes real.
- **Deployability as a multi-user SaaS.** Login, per-user alert rules,
  per-user API keys, billing hooks. Large.

### Things NOT worth doing

These come up in conversation but are bad uses of time:

- **Switching charts away from Lightweight Charts.** It's already the best
  free option.
- **Replacing FastAPI / SQLAlchemy.** The stack is fine and idiomatic.
- **Making the frontend a SPA with routes.** One-page is correct for a
  trading desk.
- **Building a node "for privacy" before shipping v2 features that need it.**
  A node is €50/mo sitting idle until mempool features exist.

---

## How to reason about the next step

Rough decision tree:

1. **Just want to use it daily?** → Deploy to Railway (see
   `docs/deployment.md`), rotate your Alchemy key, add Telegram, set up 2–3
   personal rules. That's v1 done.
2. **Want to let a friend / client try it?** → Ship the "Cheap wins" above
   first — especially **CORS + API token auth**. Skipping those on a public
   URL is reckless.
3. **Client green-lit v2?** → Pick **one** feature (probably
   smart-money leaderboard — it's the cheapest to build). Do not start
   three at once. Revisit this doc after it ships.
