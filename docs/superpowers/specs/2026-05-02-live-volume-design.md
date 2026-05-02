# Live On-Chain Volume — Design

**Status:** approved 2026-05-02
**Track:** v3 polish

## Goal

Surface **per-minute on-chain volume** for the 15 tracked stables across Ethereum mainnet, in close-to-realtime. Today the dashboard has hourly/daily volume from Dune (8h cron); this gives operators the *immediate* view they get from Binance for ETH price, but applied to the **on-chain stable transfer flow** they actually care about.

## Non-goals

- DEX swap volume per pool (heavier — separate listener, different shape).
- ETH native volume (already covered by Binance WS at the top of the dashboard, and the existing onchain-volume panel).
- Realtime LST/restaking volume (low signal, defer).
- Per-block resolution (12s buckets are too granular for visual signal; 1m is the right size).

## Approach

The **existing realtime listener** at `backend/app/realtime/listener.py` already subscribes to every block's logs via Alchemy WS, decodes each ERC-20 Transfer log, and persists whales above threshold. We extend it: in the same iteration, **every** transfer involving a token in `STABLES_BY_ADDRESS` also gets added to an in-memory minute-aggregator. When the minute boundary changes, the aggregator flushes one row per (minute, asset) to the new `realtime_volume` table.

Cost: trivial. The listener already iterates these logs. Adding a sum + counter per asset is negligible. Flush is one batch upsert per minute.

## Schema

```sql
CREATE TABLE realtime_volume (
    ts_minute      TIMESTAMPTZ NOT NULL,
    asset          VARCHAR(16) NOT NULL,
    transfer_count INTEGER NOT NULL,
    usd_volume     NUMERIC(38, 6) NOT NULL,
    PRIMARY KEY (ts_minute, asset)
);
```

One row per (minute, asset). Composite PK for idempotent upserts.

## Architecture

```
Alchemy WS  ──► listener.py  ──► parse_erc20_log ──► WhaleTransfer (existing path)
                    │
                    ▼ NEW
               MinuteAggregator
                    │
                    ▼ flushes on minute-rollover (in-memory → batch upsert)
              realtime_volume  table
                    │
                    ▼
        /api/volume/realtime?hours=N
                    │
                    ▼
              LiveVolumePanel
              (per-asset 60-minute chart, ~5s refresh)
```

The aggregator lives in `backend/app/realtime/volume_agg.py` as a small standalone class. The listener owns one instance and calls `agg.add(asset, amount, price_usd_approx)` for each Stable transfer. The aggregator decides when to flush (minute changed) and gets the `Session` injected so it can write.

## What changes

### Backend

1. **alembic 0014** — `realtime_volume` table.
2. **`backend/app/core/models.py`** — `RealtimeVolume` ORM class.
3. **New `backend/app/realtime/volume_agg.py`** — `MinuteAggregator` class. ~50 lines.
4. **Modify `backend/app/realtime/listener.py`** — instantiate the aggregator at startup, feed it stable-transfer rows in the existing `_handle_block` loop.
5. **New `backend/app/api/volume.py`** — `GET /api/volume/realtime?hours=1` returns per-asset minute rows, ordered ts asc.
6. **`backend/app/api/schemas.py`** — `RealtimeVolumePoint`, `RealtimeVolumeResponse`.
7. **`backend/app/main.py`** — register the new router under `AuthDep`.
8. **Tests:** `test_volume_agg.py` (5 tests: add accumulates, flush-on-minute-rollover, empty flush no-op, multi-asset, idempotent on retry).

### Frontend

1. **`frontend/src/api.ts`** — `RealtimeVolumePoint` type + `fetchRealtimeVolume(hours)`.
2. **New `frontend/src/components/LiveVolumePanel.tsx`** — multi-line chart (Recharts) showing top-N stables' 1-minute USD volume over the selected window. Asset legend + range selector (15m / 1h / 4h). Auto-refreshes every 5s.
3. **`frontend/src/lib/panelRegistry.ts`** — register under "Onchain" page.

### Config

- No new env vars (uses existing `ALCHEMY_WS_URL` infrastructure).
- `CLAUDE.md` — `v3-live-volume` line.

## Risks / known limits

- **Listener restart loses the in-flight minute.** When the realtime container restarts, the in-memory aggregate of the current minute is lost. Acceptable — restarts are rare and the previous minute is already flushed. Worst case: one minute of slightly low data right after a restart.
- **WS reconnect storms.** If the listener reconnects mid-minute, multiple aggregator instances could try to write the same (minute, asset) row. The `on_conflict_do_update` PK handles this — last-write-wins is fine for a sum-counter.
- **Token not priced.** All 15 stables have a `price_usd_approx` from `STABLES_BY_ADDRESS`, so `usd_volume` is always defined. New stables without a peg rate would silently contribute 0; flag in code with a guard.
- **No backfill on first deploy.** The panel starts empty and fills as new blocks arrive. Within ~5 minutes operators see meaningful data.

## Tests

5 unit tests on `MinuteAggregator`. Frontend `npm run build` is the gate.

## Future work

- Per-DEX swap volume (Uniswap / Curve / Balancer Swap events) — separate listener, different shape.
- ETH native per-minute volume — sum every block's tx values; cheap addition.
- 5-second resolution mode (toggle) — same machinery, just a smaller bucket.
