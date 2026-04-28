# Mempool Whale Tracking — Design

**Feature:** Detect whale-sized Ethereum transactions while they're still in the mempool (pending, not yet mined). Display them in the Whale Transfers panel with a clear "Pending" indicator, ahead of when they'd appear in any block-based explorer.

**Why now:** Etherscope just cut over from Alchemy's free tier to a self-hosted Geth + Lighthouse node. Geth exposes `newPendingTransactions` over WebSocket — a feed Alchemy's free tier did not provide. Mempool tracking is the first feature that genuinely requires our own node.

**User-visible benefit:** A ~12-second edge over Etherscan and other block-confirmation feeds — users see whales the moment they broadcast, not the moment they're mined.

---

## Goals

- Surface pending whale transfers in the existing `WhaleTransfersPanel` as a top "Pending" section.
- Keep the existing confirmed-whale flow unchanged. Pending tracking is additive.
- Auto-clean stale pending data: drop entries that don't confirm within 30 minutes.
- Reuse existing whale-detection thresholds (`WHALE_ETH_THRESHOLD=100`, `WHALE_STABLE_THRESHOLD_USD=250000`, per-token native thresholds for volatiles).

## Non-goals (explicit YAGNI)

- No animated "promote pending → confirmed" UI. When a tx confirms, the pending row disappears and it independently appears in the confirmed list.
- No replay protection beyond same-tx-hash idempotency. Reorgs are handled by the cleanup pass; we don't track reorg history.
- No mempool history for analytics. The `pending_transfers` table holds *currently pending* rows only; expired/confirmed rows are deleted.
- No alerts on pending events for v1. Existing alert engine still fires on confirmed-only data. Pending → alert is a separate v2.5 feature.
- No frontend animation or status transitions. Plain "yellow border = pending, list disappears once mined".

---

## Architecture

### Components

```
┌─────────────────────────┐         ┌──────────────────────┐
│ Geth (local node)       │         │ Postgres             │
│  ws://172.17.0.1:8546   │         │  pending_transfers   │
└─────────────────────────┘         │  transfers           │
            │                        └──────────────────────┘
            │ newPendingTransactions             ▲
            ▼                                    │
┌─────────────────────────┐                      │
│ MempoolListener         │ ─────────────────────┘
│  app/realtime/mempool.py│
└─────────────────────────┘
            │
            ▼
┌─────────────────────────┐
│ /api/whales/pending     │
│  GET endpoint           │
└─────────────────────────┘
            │
            ▼
┌─────────────────────────┐
│ WhaleTransfersPanel     │
│  Pending section (top)  │
│  Confirmed section      │
└─────────────────────────┘
```

### New files

- `backend/alembic/versions/0006_pending_transfers.py` — migration
- `backend/app/realtime/mempool.py` — pending-tx listener
- `backend/app/realtime/erc20_decode.py` — decode `transfer(address,uint256)` call data
- `backend/app/workers/pending_cleanup.py` — arq cron job (60s)
- `backend/tests/test_mempool_parser.py`
- `backend/tests/test_pending_cleanup.py`

### Modified files

- `backend/app/core/models.py` — add `PendingTransfer` ORM model
- `backend/app/api/whales.py` — add `GET /api/whales/pending` endpoint
- `backend/app/api/schemas.py` — add `PendingTransferOut` Pydantic schema
- `backend/app/workers/arq_worker.py` — register `cleanup_pending_transfers` cron job
- `frontend/src/components/WhaleTransfersPanel.tsx` — add Pending section
- `frontend/src/api.ts` — add `getPendingWhales()` client
- `backend/app/realtime/listener.py` — `main()` spawns the new mempool subscriber as a concurrent asyncio task alongside the existing `newHeads` task. Both share the same `AlchemyClient` instance and reconnect together if the WebSocket drops.
- `docker-compose.yml` — no structural change required; the existing `realtime` service runs both subscriptions in one Python process.

---

## Data model

### Table: `pending_transfers`

```sql
CREATE TABLE pending_transfers (
    tx_hash         TEXT PRIMARY KEY,
    from_addr       TEXT NOT NULL,
    to_addr         TEXT NOT NULL,
    asset           TEXT NOT NULL,
    amount          NUMERIC(78, 18) NOT NULL,
    usd_value       NUMERIC(20, 2),
    seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    nonce           BIGINT,
    gas_price_gwei  NUMERIC(20, 9)
);

CREATE INDEX idx_pending_seen_at ON pending_transfers(seen_at DESC);
CREATE INDEX idx_pending_sender_nonce ON pending_transfers(from_addr, nonce);
```

**Why a separate table** (not a `status` column on `transfers`):
- Pending data is short-lived (≤30 min) and high-churn. Cleanup deletes are frequent.
- Doing frequent deletes against the main `transfers` table risks index bloat and accidental confirmed-data corruption.
- The pending lifecycle (insert → optionally update on replacement → delete on confirm/expire) differs from the confirmed lifecycle (insert-only).
- Keeps the existing whale-detection code path untouched (zero regression risk).

**Notes on schema choices:**
- `tx_hash PRIMARY KEY` — Ethereum tx hashes are unique. Idempotent inserts via `ON CONFLICT DO NOTHING`.
- `from_addr + nonce` index — used to detect replaced txs (same sender + nonce, higher gas = replacement).
- `seen_at DESC` index — used to find stale rows for cleanup and to sort the API response.

---

## Listener: `app/realtime/mempool.py`

### Responsibilities

1. Subscribe to Geth's `newPendingTransactions` WebSocket method.
2. For each tx hash, call `eth_getTransactionByHash` to fetch full tx details.
3. Apply whale filter (native ETH or ERC-20 transfer to a tracked token).
4. Insert matching rows into `pending_transfers`.
5. Handle replaced txs: if a new tx arrives with same `(from_addr, nonce)` and higher `gas_price`, replace the old row.

### Reuse vs new code

- Reuses `STABLES_BY_ADDRESS` and `VOLATILE_BY_ADDRESS` from `app/realtime/tokens.py`.
- Reuses `_latest_eth_usd()` helper from `app/realtime/listener.py` for native-ETH USD valuation.
- New: `decode_erc20_transfer(input_data: str) -> tuple[str, int] | None` in `app/realtime/erc20_decode.py`. Decodes `0xa9059cbb`-prefixed call data into `(to_addr, amount)`. Returns `None` for any other selector.

### Decoding pending ERC-20 transfers

Confirmed transfers are detected via `Transfer` event logs (post-mining). Pending txs have no logs yet, so we decode the input data instead:

```
data = "0xa9059cbb"  +  pad32(to_addr)  +  pad32(amount)
                    └───── 4 bytes ────┘ └──── 32 bytes each ────┘
```

The decoder is small (~20 lines) and tested in isolation against known transfer call data.

### Filter pseudocode

```python
def whale_filter(tx) -> WhaleTransfer | None:
    # Native ETH
    if tx.value >= ETH_THRESHOLD_WEI and not is_contract_creation(tx):
        return native_whale(tx)

    # ERC-20 transfer to a tracked token
    if tx.to in TRACKED_TOKEN_ADDRESSES:
        decoded = decode_erc20_transfer(tx.input)
        if decoded is None:
            return None  # not a transfer call
        to_addr, amount = decoded
        if matches_whale_threshold(tx.to, amount):
            return erc20_whale(tx, to_addr, amount)

    return None
```

### Performance

- Mainnet mempool sees ~150-300 new pending tx hashes per second
- Each requires one `eth_getTransactionByHash` RPC call to localhost — sub-millisecond on the same box
- Filtering is cheap (in-memory dict lookup of `tx.to`, occasional input-data decode)
- Most txs filter out before any DB write
- Estimated whale-rate: a few per minute at most

No backpressure / queueing needed for v1.

### Crash recovery

- Listener is stateless — relies on Geth's subscription
- On reconnect (existing reconnect loop in `listener.py` pattern), re-subscribes; missed mempool entries that haven't been mined are still in Geth's mempool and will be re-emitted on subscription start
- `ON CONFLICT (tx_hash) DO NOTHING` in the insert prevents duplicates

---

## Cleanup job: `app/workers/pending_cleanup.py`

```python
async def cleanup_pending_transfers(ctx) -> dict:
    """Drop expired or confirmed rows from pending_transfers.

    Runs every 60 seconds.
    """
    deleted = await session.execute(text("""
        DELETE FROM pending_transfers
        WHERE seen_at < NOW() - INTERVAL '30 minutes'
           OR tx_hash IN (SELECT tx_hash FROM transfers WHERE ts > NOW() - INTERVAL '1 hour')
    """))
    return {"deleted": deleted.rowcount}
```

Two cleanup conditions:
1. **Stale:** seen >30 min ago and never confirmed → expired
2. **Confirmed:** tx hash now exists in `transfers` (meaning the existing confirmed-whale listener picked it up) → no longer pending

The `WHERE ts > NOW() - INTERVAL '1 hour'` on the subquery limits the index scan to recently-confirmed transfers — the only ones that can possibly still be pending.

Registered in `app/workers/arq_worker.py` as a cron task with `cron(minute='*')`.

---

## API: `GET /api/whales/pending`

### Request

```
GET /api/whales/pending
Authorization: Bearer <API_AUTH_TOKEN>   (if set)
```

### Response

```json
{
  "pending": [
    {
      "tx_hash": "0xabc...",
      "from_addr": "0xaaa...",
      "to_addr": "0xbbb...",
      "asset": "ETH",
      "amount": 250.5,
      "usd_value": 570000.0,
      "seen_at": "2026-04-28T09:15:23Z",
      "from_label": "Binance",
      "to_label": null
    }
  ]
}
```

- Sort: `seen_at DESC`
- Limit: 20 rows
- `from_label` / `to_label` populated from the existing `labels.py` lookup (same as confirmed transfers)

### Schema

```python
class PendingTransferOut(BaseModel):
    tx_hash: str
    from_addr: str
    to_addr: str
    asset: str
    amount: Decimal
    usd_value: Decimal | None
    seen_at: datetime
    from_label: str | None
    to_label: str | None

class PendingTransfersResponse(BaseModel):
    pending: list[PendingTransferOut]
```

---

## Frontend: `WhaleTransfersPanel.tsx`

### Visual layout

```
┌─ Whale Transfers ─────────────────────────┐
│                                            │
│  ▶ PENDING (3)              ⚠ yellow accent │
│    250 ETH    Binance → 0xabc...   12s ago │
│    1.5M USDC  0xddd... → Coinbase   8s ago │
│    300 ETH    0xeee... → 0xfff...   2s ago │
│  ─────────────────────────────────────────  │
│                                            │
│  CONFIRMED                                 │
│    500 ETH    Binance → 0xggg...  block 24,977,892 │
│    [existing confirmed list...]            │
└────────────────────────────────────────────┘
```

### Polling

- New TanStack Query: `usePendingWhales()` polling `/api/whales/pending` every 5 seconds (matches the existing `useWhaleTransfers` cadence)
- When `pending.length === 0`, the entire Pending section is hidden (no empty header)

### Visual treatment

- Section header has a yellow dot (`bg-yellow-500`) and "PENDING (N)" label
- Each pending row has a faint yellow left border (`border-l-2 border-yellow-500/40`)
- "X seconds ago" timestamp uses relative time, updates client-side
- Otherwise styling matches confirmed rows for consistency

### Max display

- Show top 5 pending rows. If more exist (rare — usually <3), truncate with "…and N more pending"

---

## Edge cases

| Case | Behavior |
|---|---|
| Same tx hash seen twice | Insert is idempotent (`ON CONFLICT DO NOTHING`) |
| Replaced tx (same sender + nonce, higher gas) | New row replaces old — listener checks `(from_addr, nonce)` index, deletes old row before inserting new |
| Listener crashes mid-stream | systemd / docker restarts; re-subscribes; idempotent insert handles dupes |
| Geth restarts | Reconnect loop kicks in (existing pattern); brief pending-feed gap is acceptable |
| Reorg makes a confirmed tx pending again | Cleanup pass runs; tx is no longer in `transfers`, will be re-inserted on next mempool seen |
| Pending tx that never mines | Cleanup deletes after 30 min |
| Tx with malformed input data | `decode_erc20_transfer` returns `None`; tx skipped (no error) |
| Geth WebSocket port unreachable | Listener logs warning and idles (mirrors existing `listener.py` behavior when Alchemy URL is unset) |

---

## Testing

### Unit tests

- `test_mempool_parser.py`:
  - Decode known `transfer(address,uint256)` calldata → returns `(to, amount)`
  - Decode non-transfer calldata → returns `None`
  - Filter native ETH below threshold → `None`
  - Filter native ETH above threshold → `WhaleTransfer`
  - Filter ERC-20 transfer to USDT above $250k threshold → `WhaleTransfer`
  - Filter ERC-20 transfer below threshold → `None`
  - Filter transfer to non-tracked address → `None`

### Integration tests (testcontainers Postgres, mirroring existing patterns)

- `test_pending_cleanup.py`:
  - Insert pending row with `seen_at = now - 31 min` → cleanup removes it
  - Insert pending row with `seen_at = now - 5 min` → cleanup leaves it
  - Insert pending row with same `tx_hash` as a row in `transfers` → cleanup removes it
  - Insert pending row with `tx_hash` not in `transfers` and seen <30 min → cleanup leaves it
- `test_pending_api.py`:
  - Seed `pending_transfers` with N rows; `GET /api/whales/pending` returns them sorted by `seen_at DESC`
  - Empty table → returns `{"pending": []}`

### Manual smoke test

After deploy, confirm:
1. `docker compose logs realtime` shows `subscribed to newPendingTransactions`
2. Within 1-2 minutes, at least one whale-sized pending tx appears in `pending_transfers` table
3. `/api/whales/pending` returns it
4. Dashboard `WhaleTransfersPanel` shows the Pending section with the row

---

## Rollout

1. Implement and unit-test in a feature branch
2. Run migration locally + verify schema
3. Deploy to the production server (`84.32.176.155`)
4. Watch logs for 30 min — verify pending detections occur and cleanup works
5. Frontend deploys with the new section; if no pending rows, section is invisible (graceful degradation)

If any issue surfaces in production, the rollback is `docker compose stop realtime` (mempool listener stops, cleanup job continues to drain pending_transfers; existing confirmed flow is unaffected).

---

## Out of scope (future work)

- **Pending-event alert rules.** Currently alerts only fire on confirmed events. A new alert type "whale pending" could fire ~12s earlier. Pending-aware alerts are a v2.5 feature.
- **Mempool history analytics.** Could persist pending → confirmed/dropped transitions into a separate `mempool_history` table for "what % of whale txs drop?" analysis. Not v1.
- **Frontend "promote" animation.** When a pending tx confirms, animate the row sliding from Pending to Confirmed with the time delta visible. Polish, not core.
- **Wallet-specific mempool watching.** "Alert me on any pending tx from address X." Different feature.
