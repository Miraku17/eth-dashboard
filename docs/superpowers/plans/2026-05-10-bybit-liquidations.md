# Bybit Liquidations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Binance forceOrder source for the v2-liquidations panel with Bybit's V5 public `allLiquidation.ETHUSDT` stream so the panel populates from production (Cherry Servers NL VPS), where Binance now returns HTTP 403 on the WS handshake.

**Architecture:** Rewrite `backend/app/realtime/liquidations.py` in place — same sibling-task shape (still spawned by the realtime container's `run_loop`), same `perp_liquidation` row schema, same downstream consumers. Only the upstream provider, the WS protocol details (subscribe op, ping/pong), and the per-event parser change. Two label flips downstream (`'binance'` → `'bybit'` in the API response constant and the panel subtitle/empty-state copy) complete the swap. No schema migration.

**Tech Stack:** Python 3.12, asyncio + `websockets` library (already a dep), SQLAlchemy bulk insert, FastAPI; React 18 + TanStack Query (frontend label/copy edits only).

**Spec:** `docs/superpowers/specs/2026-05-10-bybit-liquidations-design.md`

---

## File map

**Modify:**
- `backend/app/realtime/liquidations.py` — rewrite in place (Tasks 1 + 2)
- `backend/app/api/derivatives.py:174` — venue label flip (Task 3)
- `frontend/src/components/LiquidationsPanel.tsx:58 + empty-state block` — subtitle fallback + copy (Task 4)
- `CLAUDE.md` — v2-liquidations status note (Task 5)

**Create:**
- `backend/tests/test_bybit_liquidation_parser.py` (Task 1)

**Untouched:**
- `backend/app/core/models.py` (`PerpLiquidation` schema — no change)
- `backend/alembic/versions/` (no migration)
- `backend/tests/test_derivatives_api.py` — its seed uses `venue="binance"` literally but no assertion reads the value back, so it stays green.

---

## Test runner

`cd backend && .venv/bin/pytest tests/test_X.py -v` for a single file, or `make backend-test` for the full suite. The parser tests are pure-compute (no DB, no network) so they run in <1s.

---

## Task 1: Bybit per-event parser + tests (TDD, additive only)

**Files:**
- Create: `backend/tests/test_bybit_liquidation_parser.py`
- Modify: `backend/app/realtime/liquidations.py` — ADD a new `parse_bybit_liquidation` function. Do NOT delete `_venue_side_to_position` or `_parse_event`; they go away in Task 2 as part of the listener-body rewrite. The new parser is unused at the end of Task 1; the listener still calls the old Binance parser. This intermediate state compiles, imports cleanly, and runs without crashing — same broken-against-Binance state as before this task, no new breakage.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_bybit_liquidation_parser.py`:

```python
"""Pure-compute tests for parse_bybit_liquidation.

Bybit V5 `allLiquidation.{symbol}` payload (per item in the `data` list):
    { "T": <unix_ms>, "s": "ETHUSDT", "S": "Buy" | "Sell",
      "v": "<qty_in_eth_string>", "p": "<price_usd_string>" }

Side inversion convention (matches the previous Binance forceOrder mapping):
    S="Buy"  → exchange BUYS to close a SHORT  → row.side = "short"
    S="Sell" → exchange SELLS to close a LONG  → row.side = "long"
"""
from datetime import datetime, timezone

import pytest

from app.realtime.liquidations import parse_bybit_liquidation


def _event(**overrides) -> dict:
    base = {
        "T": 1_715_339_000_000,  # 2026-05-10T11:03:20+00:00 (within plausible range)
        "s": "ETHUSDT",
        "S": "Buy",
        "v": "0.5",
        "p": "3000.0",
    }
    base.update(overrides)
    return base


def test_buy_event_maps_to_short_liquidation():
    row = parse_bybit_liquidation(_event(S="Buy", v="0.5", p="3000"))
    assert row is not None
    assert row["venue"] == "bybit"
    assert row["symbol"] == "ETHUSDT"
    assert row["side"] == "short"
    assert row["price"] == pytest.approx(3000.0)
    assert row["qty"] == pytest.approx(0.5)
    assert row["notional_usd"] == pytest.approx(1500.0)
    assert isinstance(row["ts"], datetime)
    assert row["ts"].tzinfo == timezone.utc


def test_sell_event_maps_to_long_liquidation():
    row = parse_bybit_liquidation(_event(S="Sell"))
    assert row is not None
    assert row["side"] == "long"


def test_missing_timestamp_returns_none():
    bad = _event()
    bad.pop("T")
    assert parse_bybit_liquidation(bad) is None


def test_non_numeric_price_returns_none():
    assert parse_bybit_liquidation(_event(p="abc")) is None


def test_unknown_side_returns_none():
    assert parse_bybit_liquidation(_event(S="Hold")) is None


def test_zero_qty_returns_none():
    assert parse_bybit_liquidation(_event(v="0")) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/test_bybit_liquidation_parser.py -v
```
Expected: FAIL with `ImportError: cannot import name 'parse_bybit_liquidation' from 'app.realtime.liquidations'`.

- [ ] **Step 3: ADD the new parser to `liquidations.py`**

Open `backend/app/realtime/liquidations.py`. Do NOT delete `_venue_side_to_position` or `_parse_event` yet (Task 2 removes them). ADD the following function at the end of the parser section, immediately after the existing `_parse_event` definition (around line 95) and before `_persist`:

```python
def parse_bybit_liquidation(event: dict) -> dict | None:
    """Map one Bybit V5 `allLiquidation` event entry to a PerpLiquidation row dict.

    Bybit V5 payload shape (per item in the `data` list of an
    allLiquidation.{symbol} frame):
      { "T": <unix_ms>, "s": "ETHUSDT", "S": "Buy" | "Sell",
        "v": "<qty_in_eth_string>", "p": "<price_usd_string>" }

    Side inversion (matches the previous Binance forceOrder convention so the
    panel and existing tests render identically):
      S="Buy"  → exchange buys to close a SHORT  → side='short'
      S="Sell" → exchange sells to close a LONG  → side='long'

    Returns None on any missing/malformed field — the listener loop logs at
    WARN and skips the event without raising.
    """
    venue_side = event.get("S")
    if venue_side == "Buy":
        side = "short"
    elif venue_side == "Sell":
        side = "long"
    else:
        return None

    symbol = event.get("s")
    if not symbol:
        return None

    transact_ms = event.get("T")
    if not transact_ms:
        return None

    try:
        price = float(event.get("p") or 0)
        qty = float(event.get("v") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0 or qty <= 0:
        return None

    ts = datetime.fromtimestamp(int(transact_ms) / 1000, tz=UTC)
    return {
        "ts": ts,
        "venue": "bybit",
        "symbol": symbol,
        "side": side,
        "price": price,
        "qty": qty,
        "notional_usd": price * qty,
    }
```

The imports at the top of the file (`datetime`, `UTC`, etc.) are already present; no new imports needed.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_bybit_liquidation_parser.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/liquidations.py backend/tests/test_bybit_liquidation_parser.py
git commit -m "feat(liquidations): bybit per-event parser (replaces forceOrder _parse_event)"
```

---

## Task 2: Replace listener body + delete old Binance parser

**Files:**
- Modify: `backend/app/realtime/liquidations.py` — module docstring, constants, `run_once` body. **Delete** `_venue_side_to_position` (currently around lines 50–56) and the OLD `_parse_event` (currently around lines 59–94) — they're orphaned once `run_once` switches to `parse_bybit_liquidation`. Keep `_persist`, `main`, `run_loop`, and the new `parse_bybit_liquidation` from Task 1 unchanged.

This task has no unit test (matches precedent — the existing `run_once` had no test either; lifecycle is verified manually).

- [ ] **Step 1: Replace the module docstring and constants**

Replace lines 1–47 of `backend/app/realtime/liquidations.py` (everything from the opening `"""` through the `STALL_TIMEOUT_S` constant) with:

```python
"""Bybit V5 public liquidations WebSocket listener.

Subscribes to `allLiquidation.ETHUSDT` on Bybit's public V5 perpetuals stream
(no auth required) and persists every ETH-USD perp liquidation event to
`perp_liquidation`. Replaced the previous Binance forceOrder source on
2026-05-10 after Binance began returning HTTP 403 on the WS handshake from
our VPS IP range.

Stream schema (per Bybit V5 docs, allLiquidation topic):
    {
      "topic": "allLiquidation.ETHUSDT",
      "type":  "snapshot",
      "ts":    <server_ms>,
      "data":  [
        { "T": <unix_ms>, "s": "ETHUSDT",
          "S": "Buy" | "Sell",
          "v": "<qty_in_eth>",
          "p": "<price_usd>" },
        ...
      ]
    }

Each frame is a 1-second aggregate carrying a list of individual liquidation
events for that bucket. We unpack the list and emit one `perp_liquidation`
row per event so the schema's per-event semantics are preserved.

Position-side mapping (same convention as the prior Binance source):
  Bybit "S=Buy"  -> short position liquidated (exchange buys to close)
  Bybit "S=Sell" -> long position liquidated  (exchange sells to close)

This task runs as a sibling to the on-chain newHeads listener inside the
realtime container. It has its own reconnect loop so a Bybit hiccup
can't take down the on-chain processing.
"""
import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import websockets

from app.core.db import get_sessionmaker
from app.core.models import PerpLiquidation

log = logging.getLogger("liquidations")

BYBIT_WS_URL    = "wss://stream.bybit.com/v5/public/linear"
SUBSCRIBE_TOPIC = "allLiquidation.ETHUSDT"
TRACKED_SYMBOLS = frozenset({"ETHUSDT"})
RECONNECT_DELAY_S    = 5.0
KEEPALIVE_INTERVAL_S = 20.0
# Bybit's public stream is reasonably chatty during active hours but can go
# quiet on a calm market. 5 min is the same threshold the previous Binance
# listener used; if a real outage happens we'll see persistent reconnects.
STALL_TIMEOUT_S = 300.0
```

The module-level structure is preserved: docstring, then imports, then constants. Only the substance changed.

- [ ] **Step 2: Replace `run_once` with the Bybit-shaped lifecycle**

Find the existing `async def run_once(sessionmaker) -> None:` function in the file (was lines 106–144 before any edits) and replace its entire body with:

```python
async def _keepalive(ws) -> None:
    """Send a client-side {"op":"ping"} every KEEPALIVE_INTERVAL_S seconds.

    Bybit's V5 public WS will close the connection if neither side sends
    traffic for ~30 s. We do BOTH client pings (here) AND respond to any
    server ping in the main loop — belt and suspenders against minor-version
    drift in Bybit's heartbeat behaviour.
    """
    try:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_S)
            await ws.send(json.dumps({"op": "ping"}))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("bybit keepalive failed; outer loop will reconnect")


async def run_once(sessionmaker) -> None:
    """One connection lifecycle: open WS, subscribe, drain liquidation
    frames, persist in small batches. Returns when the socket dies, stalls,
    or the subscription is rejected; the outer `run_loop` reconnects."""
    async with websockets.connect(
        BYBIT_WS_URL, ping_interval=20, ping_timeout=20
    ) as ws:
        log.info("bybit liquidations ws connected; subscribing %s", SUBSCRIBE_TOPIC)
        await ws.send(json.dumps({"op": "subscribe", "args": [SUBSCRIBE_TOPIC]}))

        # First frame should be the subscription ACK. If it isn't a successful
        # ACK, raise — the outer reconnect can't fix a config error and we
        # want it loud.
        ack_raw = await asyncio.wait_for(ws.recv(), timeout=STALL_TIMEOUT_S)
        try:
            ack = json.loads(ack_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"bybit subscribe non-JSON ack: {ack_raw!r}") from exc
        if ack.get("op") == "subscribe" and not ack.get("success", False):
            raise RuntimeError(f"bybit subscribe rejected: {ack!r}")
        # If the first frame is already a data frame (rare but possible),
        # let the main loop handle it on the next pass — fall through.

        keepalive_task = asyncio.create_task(_keepalive(ws))
        BATCH_N = 8
        FLUSH_INTERVAL_S = 2.0
        buffer: list[dict] = []
        last_flush = asyncio.get_event_loop().time()
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=STALL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    log.warning("bybit ws idle >%.0fs -- reconnecting", STALL_TIMEOUT_S)
                    if buffer:
                        _persist(buffer, sessionmaker)
                    return

                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue

                # Server-initiated ping → respond, do nothing else.
                if msg.get("op") == "ping":
                    await ws.send(json.dumps({"op": "pong"}))
                    continue
                # Pong reply (to our ping) → ignore.
                if msg.get("op") in ("pong", "subscribe"):
                    continue

                if msg.get("topic") != SUBSCRIBE_TOPIC:
                    continue
                events = msg.get("data") or []
                if not isinstance(events, list):
                    continue

                for event in events:
                    row = parse_bybit_liquidation(event)
                    if row is not None:
                        buffer.append(row)

                now = asyncio.get_event_loop().time()
                if len(buffer) >= BATCH_N or (now - last_flush) >= FLUSH_INTERVAL_S:
                    inserted = _persist(buffer, sessionmaker)
                    if inserted:
                        sample = buffer[-1]
                        log.info("liquidations persisted=%d (sample side=%s notional=%.0f)",
                                 inserted, sample["side"], sample["notional_usd"])
                    buffer = []
                    last_flush = now
        finally:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task
```

The `_persist`, `main`, and `run_loop` functions below `run_once` stay exactly as they are — same `sessionmaker = get_sessionmaker()` entry path, same outer reconnect loop. Only the body of `run_once` changes (and the new `_keepalive` helper above it).

- [ ] **Step 3: Delete the orphaned Binance parser functions**

The old `_venue_side_to_position` and `_parse_event` are no longer referenced (Step 2 swapped `run_once`'s call site to `parse_bybit_liquidation`). Delete both functions outright. They live between the constants block (now ending with `STALL_TIMEOUT_S = 300.0`) and the `_persist` definition. After deletion, the file's parser section contains only `parse_bybit_liquidation` (added in Task 1) and `_keepalive` (added in Step 2 above).

Verify with:
```bash
grep -n "_venue_side_to_position\|^def _parse_event\|^async def _parse_event" backend/app/realtime/liquidations.py
```
Expected: no output (both functions are gone). If anything matches, finish removing it.

- [ ] **Step 4: Verify the file imports cleanly**

```bash
cd backend && .venv/bin/python -c "import app.realtime.liquidations; print('ok')"
```
Expected: `ok` and no import errors.

- [ ] **Step 5: Verify the existing parser tests still pass**

```bash
cd backend && .venv/bin/pytest tests/test_bybit_liquidation_parser.py -v
```
Expected: 6 passed (the parser from Task 1 is untouched by this task; sanity check).

- [ ] **Step 6: Commit**

```bash
git add backend/app/realtime/liquidations.py
git commit -m "feat(liquidations): bybit V5 listener body + drop binance parser"
```

---

## Task 3: API venue label flip

**Files:**
- Modify: `backend/app/api/derivatives.py` — line 174 only.

- [ ] **Step 1: Flip the constant**

Open `backend/app/api/derivatives.py`. Find the `LiquidationSummary(...)` instantiation around line 167–177. Change:

```python
            venue="binance",
```

to:

```python
            venue="bybit",
```

That's the only edit in this file. The line number is approximate; locate by the `LiquidationSummary(` call inside the `liquidations` endpoint handler.

- [ ] **Step 2: Verify the existing API tests still pass**

```bash
cd backend && .venv/bin/pytest tests/test_derivatives_api.py -v
```
Expected: all tests pass. The test seed uses `venue="binance"` for the seeded `PerpLiquidation` rows but no assertion reads the value back from the API response, so the change is invisible to the test.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/derivatives.py
git commit -m "fix(liquidations): flip API venue label to bybit"
```

---

## Task 4: Frontend subtitle + empty-state copy

**Files:**
- Modify: `frontend/src/components/LiquidationsPanel.tsx` — line 58 (subtitle fallback) and the empty-state block I shipped in commit `c0fbd72` (the `summary?.listener_stale ? (...) : (...)` ternary).

- [ ] **Step 1: Read the current empty-state block**

The relevant block (from commit `c0fbd72`) looks roughly like:

```tsx
      {!isLoading && !error && (!data || rows.length === 0) && (
        summary?.listener_stale ? (
          <p className="p-5 text-sm text-slate-500">
            <span className="text-down font-medium">Stream unavailable from this network.</span>{" "}
            Binance's public futures WebSocket is reachable here but never
            delivers market-data frames — REST works, the data plane is
            silently filtered. The listener is healthy and will populate
            this panel automatically once deployed somewhere unfiltered
            (e.g. the Hetzner target).
          </p>
        ) : (
          <p className="p-5 text-sm text-slate-500">
            no liquidations in the last {range} — quiet market window. Listener
            subscribes to Binance forceOrder; events stream as they happen.
          </p>
        )
      )}
```

The Binance-specific copy is no longer accurate. With Bybit delivering reliably from this VPS, both branches collapse to a single neutral message.

- [ ] **Step 2: Replace the empty-state ternary with a single message**

Change the block to:

```tsx
      {!isLoading && !error && (!data || rows.length === 0) && (
        <p className="p-5 text-sm text-slate-500">
          no liquidations in the last {range} — quiet market window. Listener
          subscribes to Bybit's allLiquidation.ETHUSDT; events stream as they happen.
        </p>
      )}
```

- [ ] **Step 3: Update the subtitle fallback**

Find line 58 (or near it) of the same file:

```tsx
      subtitle={`Perp futures · ETH-USD · ${summary?.venue ?? "binance"}`}
```

Change `"binance"` to `"bybit"`:

```tsx
      subtitle={`Perp futures · ETH-USD · ${summary?.venue ?? "bybit"}`}
```

- [ ] **Step 4: Verify the build**

```bash
cd frontend && npm run build
```
Expected: build succeeds with no TS errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LiquidationsPanel.tsx
git commit -m "fix(liquidations): bybit subtitle + neutral empty-state copy"
```

---

## Task 5: CLAUDE.md status update

**Files:**
- Modify: `CLAUDE.md` — the `## v2 status` block, specifically the `v2-liquidations ✅` bullet.

- [ ] **Step 1: Find the v2-liquidations bullet**

Open `CLAUDE.md` and search for `v2-liquidations ✅`. The bullet currently describes the Binance source. It will look something like:

```
- v2-liquidations ✅ Perp liquidations heatmap — Binance USD-M Futures public WebSocket forceOrder stream (`!forceOrder@arr`, free, no auth) runs as a sibling task inside the realtime container; persists every ETH-USD liquidation event to `perp_liquidation` (one row per event, `ts`/`venue`/`side`(long|short)/`price`/`qty`/`notional_usd`). `/api/derivatives/liquidations?hours=N` returns hourly buckets + a 24h summary tile. `LiquidationsPanel` renders signed-stacked bars (longs above zero, red; shorts below zero, green) plus a long-liquidated/short-liquidated/skew-and-largest tile row. Sits on the Markets page beside the existing Derivatives panel. Single venue (Binance) for v1; the schema's `venue` column allows Bybit/OKX/Deribit to slot in without API change. Listener owns its own reconnect loop so a Binance outage can't disrupt on-chain processing.
```

- [ ] **Step 2: Replace the bullet with the post-swap version**

Replace it with:

```
- v2-liquidations ✅ Perp liquidations heatmap — Bybit V5 public `allLiquidation.ETHUSDT` stream (free, no auth) runs as a sibling task inside the realtime container; persists every ETH-USD liquidation event to `perp_liquidation` (one row per event, `ts`/`venue`/`side`(long|short)/`price`/`qty`/`notional_usd`). `/api/derivatives/liquidations?hours=N` returns hourly buckets + a 24h summary tile. `LiquidationsPanel` renders signed-stacked bars (longs above zero, red; shorts below zero, green) plus a long-liquidated/short-liquidated/skew-and-largest tile row. Sits on the Markets page beside the existing Derivatives panel. Single venue (Bybit) for v1; the schema's `venue` column allows OKX/Deribit to slot in without API change. **Provider swap (2026-05-10):** originally Binance forceOrder; switched to Bybit after Binance began returning HTTP 403 on the WS handshake from our datacenter IP range, leaving the panel permanently empty in production. Spec: `docs/superpowers/specs/2026-05-10-bybit-liquidations-design.md`. Listener owns its own reconnect loop so a Bybit outage can't disrupt on-chain processing.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): liquidations source swapped binance -> bybit"
```

---

## Final verification (manual, after deploy)

After all five tasks land and the deploy script ships them:

1. SSH into the VPS, `cd ~/etherscope`.
2. Confirm the realtime container picked up the new code:
   ```bash
   docker compose logs --tail 50 realtime | grep -iE "bybit liquidations|allLiquidation"
   ```
   Expected: `bybit liquidations ws connected; subscribing allLiquidation.ETHUSDT` within seconds of the redeploy.
3. Wait for actual market activity (typically <5 minutes during US/EU trading hours):
   ```bash
   docker compose exec postgres psql -U eth -d eth -c "SELECT count(*), max(ts) FROM perp_liquidation;"
   ```
   Expected: count > 0 with `max(ts)` recent.
4. Hard-refresh the dashboard's Markets page; the Liquidations panel populates within 60s once rows exist.
5. The summary tile reads `bybit` in the subtitle; the empty-state copy (if seen briefly) mentions Bybit, not Binance.

If after ~30 minutes of market hours the count is still 0, run the same direct WS handshake test we ran for Binance — substituting the Bybit URL — to confirm Bybit isn't also blocking us:

```bash
docker compose exec api python -c "from websockets.sync.client import connect; ws = connect('wss://stream.bybit.com/v5/public/linear'); ws.send('{\"op\":\"subscribe\",\"args\":[\"allLiquidation.ETHUSDT\"]}'); print('subscribed; waiting'); print(ws.recv(timeout=30)[:300])"
```

If that hangs or errors, Bybit is also filtering us and the open-follow-up "Add OKX or Deribit" from the spec becomes the next item.
