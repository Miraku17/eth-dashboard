# Bybit Liquidations — Design

**Date:** 2026-05-10
**Status:** Draft
**Track:** post-v5 fix — replaces the Binance forceOrder source for the v2-liquidations panel.
**Predecessors:** v2-liquidations (shipped earlier). The Binance `forceOrder` listener returns HTTP 403 from our Cherry Servers VPS — confirmed via direct `wss://fstream.binance.com/ws/!forceOrder@arr` handshake test on 2026-05-10 — so the panel never populates from production. This design swaps the upstream provider to Bybit and removes the Binance code path.

## Goal

Restore the liquidations panel by replacing the upstream WebSocket source with Bybit's public V5 perpetuals stream. Bybit doesn't blanket-block datacenter IPs the way Binance does, so the existing `realtime` container will receive frames and the existing `perp_liquidation` table will populate without schema or API contract changes.

## Non-goals

- **Multi-venue support.** v1 of liquidations was Binance-only; this revision is Bybit-only. The schema's `venue` column still exists for future expansion, but the API hard-codes the venue label and the panel renders single-venue data. Adding multi-venue plumbing would be plumbing for plumbing's sake.
- **A configurable / env-driven venue switch.** No `LIQUIDATION_VENUE` env var. Provider swap is a code change. (Provider swaps are once-per-year events at most; runtime config adds permanent surface area for a one-shot maneuver.)
- **Other Bybit symbols.** ETHUSDT only, matching the current scope of the liquidations panel.
- **Bybit private/auth streams.** The `allLiquidation.{symbol}` topic is on the public V5 channel, no API key needed.
- **Reconciliation with the Binance-era data.** Existing rows in `perp_liquidation` with `venue='binance'` (zero, on this VPS) stay untouched. No backfill from Bybit's REST.

## Why Bybit

| Provider | Public liquidations? | Datacenter IP filtering? | Auth? |
|---|---|---|---|
| **Binance** | yes (`!forceOrder@arr`) | **yes — 403 from Cherry Servers NL** | none |
| **Bybit** | yes (`allLiquidation.{symbol}` on V5 public WS) | not observed at this scale | none |
| OKX | yes (private channel only) | n/a | API key required |
| Deribit | yes | not blanket-blocked | none, but ETH/BTC notional much smaller |

Bybit gives the largest accessible ETH-USDT liquidation feed without paid data services or proxy infrastructure.

## Architecture

```
┌──────────────────────────────────┐
│  realtime (mainnet) container    │
│  ────────────────────────────    │
│  • mainnet listener (WETH+stables) │
│  • bybit_liquidations sibling task │ ◀── this design replaces the binance task
└──────┬───────────────────────────┘
       │ writes
       ▼
   perp_liquidation (PG)   ◀── existing schema, unchanged
       │
       ▼
   /api/derivatives/liquidations  ◀── one constant changed (venue label)
       │
       ▼
   LiquidationsPanel              ◀── empty-state copy refreshed
```

Single sibling task, same parent container, same row schema. The change is provider-side only.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Upstream provider | **Bybit V5 public** | Only viable free liquidation feed without datacenter-IP filtering or auth. |
| Symbol scope | **ETHUSDT only** | Matches the existing v2-liquidations scope. Other symbols are YAGNI. |
| Stream topic | **`allLiquidation.ETHUSDT`** | Bybit deprecated the per-event `liquidation.{symbol}` topic in mid-2024. `allLiquidation` is the documented current path; carries a list of per-event entries inside each 1-second message. |
| Per-event vs bucket storage | **Per-event** | We unpack the list inside each frame and emit one `perp_liquidation` row per liquidation. Schema semantics (one row = one liquidation event) are preserved. |
| Deployment shape | **Sibling task in `realtime` container** | Mirrors the previous Binance pattern. Fault isolation between mainnet listener and liquidations is preserved. No new docker service. |
| Binance code path | **Removed entirely** | No fallback, no env-var dispatch. Single provider per the multi-venue non-goal. |

## Components

Three pieces touched.

### 1. `backend/app/realtime/liquidations.py` (rewrite in place)

The file keeps its name (`liquidations.py`) since the public surface is unchanged: a coroutine the realtime listener spawns as a sibling task, persisting rows to `perp_liquidation`. Internals are replaced.

New constants:
```python
BYBIT_WS_URL    = "wss://stream.bybit.com/v5/public/linear"
SUBSCRIBE_TOPIC = "allLiquidation.ETHUSDT"
KEEPALIVE_INTERVAL_S = 20
```

Connection lifecycle (`run_once`):
1. Open WS to `BYBIT_WS_URL` (TLS, ping_interval/timeout from `websockets` library defaults).
2. Send `{"op": "subscribe", "args": [SUBSCRIBE_TOPIC]}`.
3. Await first frame; expect `{"op":"subscribe","success":true,...}`. If `success` is false, raise — the outer reconnect will not fix a config error and we want it loud.
4. Spawn `_keepalive_task` that sends `{"op":"ping"}` every 20s. Cancelled in `finally`.
5. Drain frames in a loop:
   - If incoming `{"op":"ping"}` → respond `{"op":"pong"}`.
   - If incoming `{"topic":"allLiquidation.ETHUSDT","data":[…]}` → for each item in `data`, call `parse_bybit_liquidation(item)`. Collect non-None rows.
   - On every iteration end, flush rows via the existing `_persist(rows, sessionmaker)` helper. (Same per-message flush as Binance — keeps PG in lockstep with the stream.)

Outer loop (`run_loop`): unchanged from the current Binance version structurally — try/except around `run_once`, exponential reconnect on disconnect.

The Binance constants, `_venue_side_to_position`, and Binance `_parse_event` are deleted. The new parser owns the side-inversion logic.

### 2. Per-event parser (in same file)

Pure function:

```python
def parse_bybit_liquidation(event: dict) -> dict | None:
    """Map one Bybit allLiquidation event entry to a perp_liquidation row dict.

    Bybit V5 payload shape (per item in `data`):
      { "T": <unix_ms>, "s": "ETHUSDT", "S": "Buy" | "Sell",
        "v": "<qty_in_eth>", "p": "<price_usd>" }

    Side inversion: Bybit's `S` is the side of the LIQUIDATION ORDER
    (the order the exchange uses to close the loser's position).
      S="Buy"  → exchange buys to close a SHORT  → side='short'
      S="Sell" → exchange sells to close a LONG  → side='long'

    Same convention Binance forceOrder used. Panel semantics unchanged.

    Returns None on missing/malformed fields (logged at WARN by caller).
    """
```

Field mapping:

| Row column | Bybit source | Transform |
|---|---|---|
| `ts` | `T` (ms) | `datetime.fromtimestamp(T/1000, tz=UTC)` |
| `venue` | constant | `"bybit"` |
| `side` | `S` | `"Buy"→"short"`, `"Sell"→"long"`, else None |
| `price` | `p` | `float(p)` |
| `qty` | `v` | `float(v)` |
| `notional_usd` | computed | `price * qty` (ETHUSDT is USDT-margined linear; qty is base-asset ETH, price is USDT/ETH; product is USD-equivalent notional) |

### 3. Hard-coded venue strings flipped

- `backend/app/api/derivatives.py:174` — `venue="binance"` → `venue="bybit"` in the summary tile builder.
- `frontend/src/components/LiquidationsPanel.tsx:58` — subtitle fallback `"binance"` → `"bybit"`. Also refresh the empty-state copy I shipped in commit `c0fbd72` ("Stream unavailable from this network…") which was Binance-specific and no longer accurate. Replace with neutral copy: `"no liquidations in the last <range> — quiet market window."` (the existing copy from before commit `c0fbd72`, which is honest now that Bybit delivers).

## Schema

**No change.** The existing `perp_liquidation` table (created in an earlier alembic revision, populated previously by Binance) is reused as-is. Existing columns: `(ts, venue, side, price, qty, notional_usd)`. The `venue` column already accommodates the new label.

No migration is part of this work.

## Data flow

**Per WS frame:**
```
ws.recv()
  ↓
parse JSON
  ↓
op == "ping"?           → ws.send({"op":"pong"});  continue
op == "subscribe"?      → assert success=True;     continue
topic == "allLiquidation.ETHUSDT"?
  ↓
for item in data:
  row = parse_bybit_liquidation(item)
  if row: rows.append(row)
  ↓
_persist(rows, sessionmaker)   # one PG round-trip per frame
```

**Read path:** unchanged. `/api/derivatives/liquidations?hours=N` queries `perp_liquidation` filtered to the window, builds hourly buckets and the summary tile (including `summary.listener_stale` from commit `c0fbd72`).

## Error handling

| Scenario | Behavior |
|---|---|
| Subscription `success=false` | Raise — the outer reconnect cannot fix a config-level issue. Visible failure forces a real fix. |
| WS disconnect | Outer `run_loop` catches, applies exponential reconnect (existing logic). Keepalive task cancelled in `finally`. |
| Server ping not responded to within ~30s | Bybit drops us; same path as a normal disconnect. The keepalive task makes this nearly impossible. |
| `parse_bybit_liquidation` returns None | Skip event, log WARN with truncated payload. Stream loop continues. |
| Per-frame `_persist` raises (DB issue) | Log exception, continue draining the WS so we don't pile up backpressure. Lost rows acceptable in a DB outage. |
| `listener_stale` (no rows in 6h despite no logged errors) | Existing API surface flags it; panel renders the empty state. |

## Testing

### `backend/tests/test_bybit_liquidation_parser.py` (new, pure compute, no DB)

Cases:
- `S="Buy"` event → row has `side="short"` (inversion correct)
- `S="Sell"` event → row has `side="long"`
- `T` missing → returns `None`
- `p` non-numeric (e.g. `"abc"`) → returns `None`
- `S` is `"Hold"` (unknown) → returns `None`
- All-fields-present happy path → row's `notional_usd` equals `price * qty`

Six tests, ~50 lines.

### Existing tests

If `backend/tests/test_liquidations_listener.py` exists and references Binance shapes, update its fixtures to Bybit shapes. If no listener-loop test exists today (likely), no new one is added — matches precedent.

The endpoint test `test_derivatives_api.py` already covers the API serialization shape; the venue-string change should pass through unchanged once `'binance'` literals are flipped to `'bybit'`.

### Manual verification before declaring done

1. `docker compose logs -f realtime` shows `bybit liquidations ws connected; subscribed to allLiquidation.ETHUSDT`.
2. Within ~5 minutes (depending on market activity), a parsed event is logged at INFO or DEBUG.
3. `SELECT count(*), max(ts) FROM perp_liquidation;` returns non-zero with `max(ts)` recent.
4. Dashboard panel populates within 60s. Hard-refresh to drop the stale empty-state.
5. The 24h tile updates with non-zero long/short USD totals during normal market hours.

## Operator setup

**None.** No env var, no profile flag, no docker-compose change. The listener becomes active on the next deploy. Bybit is free and unauthenticated.

## CLAUDE.md update (post-merge)

In `## v2 status`, replace the existing `v2-liquidations ✅` block's wording about the Binance source with a note about the provider swap. Reason: the milestone status block is the authoritative ledger for what's running; future-me reading this should see "Bybit" not "Binance" when checking the liquidations source.

Suggested edit (single line, in the v2-liquidations bullet):
> `…persists every ETH-USD liquidation event to perp_liquidation… Single venue (Bybit) for v1 (originally Binance — switched 2026-05-10 after Binance began 403'ing our VPS IP at the WS handshake)…`

## Open follow-ups (not in v1)

- Add OKX or Deribit as a parallel source if Bybit ever 403's us too. The schema is ready; we just don't do this preemptively.
- Per-venue panel breakdown if a second venue is added. Currently single-venue assumption is hard-coded in two places (`api/derivatives.py:174`, `LiquidationsPanel.tsx:58`).
- Multi-symbol support (BTCUSDT, SOLUSDT) if the dashboard's product scope expands beyond ETH.
