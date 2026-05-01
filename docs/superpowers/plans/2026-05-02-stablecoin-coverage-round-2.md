# Stablecoin Coverage Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append EURCV, EURe, tGBP to the existing 9-stable registry. Same machinery as round 1; only registry/Literal/Dune-CTE/dropdown/test extensions.

**Architecture:** Round 1 already established `StableToken` (with `peg_currency` + `price_usd_approx`), the parser's FX-aware threshold path, the Dune `asset_alias` CTE pattern, and the frontend asset-filter dropdown. This task adds three more rows in each of those locations.

**Tech Stack:** Python (registry, schemas, test), TypeScript (api.ts, dropdown), Dune SQL (asset_alias CTE), Dune MCP (in-place query update).

**Spec:** `docs/superpowers/specs/2026-05-02-stablecoin-coverage-round-2-design.md`.

**File map:**
- Modify:
  - `backend/app/realtime/tokens.py` — append 3 entries to `STABLES`
  - `backend/app/api/schemas.py` — extend `WhaleAsset` Literal with `"EURCV"`, `"EURe"`, `"tGBP"`
  - `backend/tests/test_realtime_parser.py` — one new combined sanity test
  - `backend/dune/stablecoin_supply.sql` — append 3 rows to `asset_alias` CTE
  - `frontend/src/api.ts` — extend `WhaleAsset` type literal
  - `frontend/src/components/WhaleTransfersPanel.tsx` — extend `ASSET_OPTIONS` dropdown
  - `CLAUDE.md` — bump M3 description from "9 stables" to "12 stables"

Plus: update Dune query 7362750 in place via MCP (controller-side, post-merge).

---

## Task 1 — Add three entries everywhere

This is a single coherent task — five file edits that all together extend coverage by 3 stables. Doing them as one unit avoids the type-shape-mid-flux pattern from round 1's bento PR.

**Files:**
- Modify: `backend/app/realtime/tokens.py`
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/dune/stablecoin_supply.sql`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/WhaleTransfersPanel.tsx`

- [ ] **Step 1: Append 3 entries to `STABLES` in `tokens.py`**

In `backend/app/realtime/tokens.py`, find the existing `STABLES` tuple. Today it has 9 entries (USDT through ZCHF). Append these three lines INSIDE the tuple, before the closing `)`:

```python
    StableToken("EURCV", "0x5f7827fdeb7c20b443265fc2f40845b715385ff2", 18, "EUR", 1.08),
    StableToken("EURe",  "0x39b8b6385416f4ca36a20319f70d28621895279d", 18, "EUR", 1.08),
    StableToken("tGBP",  "0x27f6c8289550fce67f6b50bed1f519966afe5287", 18, "GBP", 1.27),
```

The full updated `STABLES` should have 12 entries.

- [ ] **Step 2: Extend `WhaleAsset` Literal in `schemas.py`**

In `backend/app/api/schemas.py`, find:

```python
WhaleAsset = Literal[
    "ETH",
    "USDT", "USDC", "DAI",
    "PYUSD", "FDUSD", "USDS", "GHO", "EUROC", "ZCHF",
    "ANY",
]
```

Replace with:

```python
WhaleAsset = Literal[
    "ETH",
    "USDT", "USDC", "DAI",
    "PYUSD", "FDUSD", "USDS", "GHO", "EUROC", "ZCHF",
    "EURCV", "EURe", "tGBP",
    "ANY",
]
```

- [ ] **Step 3: Append 3 entries to the Dune `asset_alias` CTE**

In `backend/dune/stablecoin_supply.sql`, find the `asset_alias` CTE values block. Today it has 9 rows. Append these three rows BEFORE the closing `)`:

```sql
    (0x5f7827fdeb7c20b443265fc2f40845b715385ff2, 'EURCV'),
    (0x39b8b6385416f4ca36a20319f70d28621895279d, 'EURe'),
    (0x27f6c8289550fce67f6b50bed1f519966afe5287, 'tGBP')
```

(Watch comma placement — the previous-last row needs a trailing comma; the new last row doesn't.)

The full updated CTE should have 12 rows.

- [ ] **Step 4: Extend frontend `WhaleAsset` type in `api.ts`**

In `frontend/src/api.ts`, find:

```typescript
export type WhaleAsset =
  | "ETH"
  | "USDT" | "USDC" | "DAI"
  | "PYUSD" | "FDUSD" | "USDS" | "GHO" | "EUROC" | "ZCHF";
```

Replace with:

```typescript
export type WhaleAsset =
  | "ETH"
  | "USDT" | "USDC" | "DAI"
  | "PYUSD" | "FDUSD" | "USDS" | "GHO" | "EUROC" | "ZCHF"
  | "EURCV" | "EURe" | "tGBP";
```

- [ ] **Step 5: Extend `ASSET_OPTIONS` dropdown in `WhaleTransfersPanel.tsx`**

In `frontend/src/components/WhaleTransfersPanel.tsx`, find the `ASSET_OPTIONS` array. Today it has 11 entries (ALL + 10 assets). Append these three rows before the closing `]`:

```typescript
  { value: "EURCV", label: "EURCV" },
  { value: "EURe", label: "EURe" },
  { value: "tGBP", label: "tGBP" },
```

The full updated array should have 14 entries.

- [ ] **Step 6: Add a parser test for the new entries**

Append to `backend/tests/test_realtime_parser.py`:

```python
def test_parse_erc20_log_eurcv_uses_fx_threshold():
    """250k EURCV ≈ $270k notional; passes a $250k USD threshold."""
    log = {
        "address": "0x5f7827fdeb7c20b443265fc2f40845b715385ff2",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(250_000 * 10**18),  # 250k EURCV (18 decimals)
        "blockNumber": "0x20",
        "transactionHash": "0xeurcv1",
        "logIndex": "0x1",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "EURCV"
    assert row.amount == 250_000.0
    # 250000 × 1.08 ≈ 270k
    assert abs(row.usd_value - 270_000.0) < 1.0


def test_parse_erc20_log_tgbp_uses_fx_threshold():
    """200k tGBP ≈ $254k notional; passes a $250k USD threshold."""
    log = {
        "address": "0x27f6c8289550fce67f6b50bed1f519966afe5287",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(200_000 * 10**18),  # 200k tGBP (18 decimals)
        "blockNumber": "0x21",
        "transactionHash": "0xgbp1",
        "logIndex": "0x2",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "tGBP"
    assert row.amount == 200_000.0
    # 200000 × 1.27 = 254k
    assert abs(row.usd_value - 254_000.0) < 1.0
```

(Skipping a separate EURe test — the EUR FX path is already exercised by EURCV; redundant.)

- [ ] **Step 7: Run the full backend suite**

```bash
cd backend && .venv/bin/pytest tests/test_realtime_parser.py -v
```

Expected: 16 tests pass (14 existing + 2 new).

```bash
cd backend && .venv/bin/pytest -q 2>&1 | tail -10
```

Expected: no NEW failures vs. main. Pre-existing `test_flows_api` failures persist (unrelated, on main).

- [ ] **Step 8: Build frontend**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 9: Update CLAUDE.md M3 description**

In `CLAUDE.md`, find the M3 line. Today it reads:

```
- M3 ✅ whale tracking — Alchemy WS listener persists ETH + 9 stables (USDT/USDC/DAI/PYUSD/FDUSD/USDS/GHO/EUROC/ZCHF) ...
```

Replace `9 stables (USDT/USDC/DAI/PYUSD/FDUSD/USDS/GHO/EUROC/ZCHF)` with `12 stables (USDT/USDC/DAI/PYUSD/FDUSD/USDS/GHO/EUROC/ZCHF/EURCV/EURe/tGBP)`.

- [ ] **Step 10: Commit (single commit)**

```bash
git add backend/app/realtime/tokens.py \
        backend/app/api/schemas.py \
        backend/dune/stablecoin_supply.sql \
        backend/tests/test_realtime_parser.py \
        frontend/src/api.ts \
        frontend/src/components/WhaleTransfersPanel.tsx \
        CLAUDE.md
git commit -m "feat(stables): round 2 — add EURCV, EURe, tGBP (12 stables total)"
```

---

## Task 2 — Update the live Dune query (controller-side, post-merge)

After the PR merges, update Dune query `7362750` via MCP so the next worker sync picks up the new contracts. This step is performed by the controller using the Dune MCP `updateDuneQuery` tool, not by an implementer subagent.

The query SQL is whatever is in the merged `backend/dune/stablecoin_supply.sql` at that point. Use the same `description` update style as round 1.

---

## Self-review

**Spec coverage:**
- 3 new entries in `STABLES` → Step 1.
- Parser FX path already handles EUR/GBP/CHF — round 1 work.
- Backend Literal → Step 2.
- Frontend type + dropdown → Steps 4, 5.
- Dune asset_alias CTE → Step 3.
- New parser tests → Step 6.
- CLAUDE.md → Step 9.
- Live Dune query update → Task 2 (controller).

**Type consistency:**
- `WhaleAsset` literal mirrored backend ↔ frontend with same string casing (`"EURe"` and `"tGBP"` lowercase-prefix preserved).
- `peg_currency` and `price_usd_approx` consumed by parser — same shape as round 1's EUROC/ZCHF entries.

**Placeholder scan:** none — every step has runnable code.

---

## Execution Handoff

Single coherent task, ~10 file edits. **Recommend dispatching ONE subagent** to do all 10 steps, since they're tightly coupled (registry + Literal + dropdown changes must agree). Subagent-driven multi-task review for a 7-file mechanical extension is overkill.

**Or:** controller-inline execution. Same scope, same outcome.
