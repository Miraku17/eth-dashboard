# Stablecoin Coverage Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand whale-tracking + stablecoin-supply coverage from 3 USD stables (USDT/USDC/DAI) to 9 stables by adding PYUSD, FDUSD, USDS, GHO, EUROC, ZCHF — including FX-aware thresholds for the EUR-pegged EUROC and CHF-pegged ZCHF.

**Architecture:** Replace the `Token` dataclass for stables with a richer `StableToken` carrying `peg_currency` + `price_usd_approx`. Switch `parse_erc20_log`'s threshold compare from native amount to USD notional. Update the `WhaleAsset` Literal (backend + frontend), the asset-filter dropdown, and the stablecoin-supply Dune query SQL. No new dependencies, no migrations, no env vars.

**Tech Stack:** Python (backend dataclass + Pydantic Literal + parser logic + pytest), TypeScript (frontend type literal + dropdown), Dune SQL (one-line `IN (...)` change). Manual operator step: re-paste the updated Dune SQL into the existing `DUNE_QUERY_ID_STABLECOIN_SUPPLY` query and save — covered in Task 7's smoke section.

**Spec:** `docs/superpowers/specs/2026-05-01-stablecoin-coverage-design.md`.

**File map:**
- Modify:
  - `backend/app/realtime/tokens.py` — replace `Token`-for-stables with `StableToken`; add 6 new entries
  - `backend/app/realtime/parser.py` — switch threshold compare from `amount` to `usd` for the stable path (both confirmed + pending)
  - `backend/tests/test_realtime_parser.py` — append 3 new test functions
  - `backend/app/api/schemas.py` — expand `WhaleAsset` Literal
  - `backend/dune/stablecoin_supply.sql` — extend `IN (...)` clause in both CTEs
  - `frontend/src/api.ts` — expand `WhaleAsset` TypeScript type
  - `frontend/src/components/WhaleTransfersPanel.tsx` — add 6 entries to `ASSET_OPTIONS`
  - `CLAUDE.md` — update M3 milestone description with new stables + Dune-resave note

No new files. No backend tests for the parser break, schemas, or api.ts because all modifications are additive — the existing test suite must continue passing throughout.

---

## Task 1 — Token registry: `StableToken` dataclass + 9 entries

**Files:**
- Modify: `backend/app/realtime/tokens.py`

- [ ] **Step 1: Replace the file**

Replace the ENTIRE content of `backend/app/realtime/tokens.py` with this exact content:

```python
"""Token metadata for whale-tracking. ERC-20 Transfer topic + contract addresses.

Three tracked sets:

- STABLES: pegged tokens (USD/EUR/CHF). Threshold compare uses
  amount × price_usd_approx so non-USD pegs surface at the right USD
  notional. price_usd_approx is a hand-curated rate; refresh
  periodically (whale-detection isn't sensitive to ±10% drift).
- VOLATILE_TOKENS: price-floating, threshold is hardcoded per-token in
  native units, sized to approximate ~$250k USD at the time of authoring.
"""
from dataclasses import dataclass

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str  # lowercase 0x…
    decimals: int


@dataclass(frozen=True)
class StableToken(Token):
    peg_currency: str         # "USD" | "EUR" | "CHF" (display only)
    price_usd_approx: float   # 1.0 for USD pegs; ~1.08 for EUR; ~1.10 for CHF


@dataclass(frozen=True)
class VolatileToken(Token):
    threshold_native: float
    price_usd_approx: float


STABLES: tuple[StableToken, ...] = (
    StableToken("USDT",  "0xdac17f958d2ee523a2206206994597c13d831ec7", 6,  "USD", 1.00),
    StableToken("USDC",  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6,  "USD", 1.00),
    StableToken("DAI",   "0x6b175474e89094c44da98b954eedeac495271d0f", 18, "USD", 1.00),
    StableToken("PYUSD", "0x6c3ea9036406852006290770bedfcaba0e23a0e8", 6,  "USD", 1.00),
    StableToken("FDUSD", "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409", 18, "USD", 1.00),
    StableToken("USDS",  "0xdc035d45d973e3ec169d2276ddab16f1e407384f", 18, "USD", 1.00),
    StableToken("GHO",   "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", 18, "USD", 1.00),
    StableToken("EUROC", "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c", 6,  "EUR", 1.08),
    StableToken("ZCHF",  "0xb58e61c3098d85632df34eecfb899a1ed80921cb", 18, "CHF", 1.10),
)

STABLES_BY_ADDRESS: dict[str, StableToken] = {t.address: t for t in STABLES}


# Thresholds each target ~$250k USD notional; refresh as prices drift.
VOLATILE_TOKENS: tuple[VolatileToken, ...] = (
    VolatileToken("WETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18, 70, 3500),
    VolatileToken("WBTC", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8, 3.5, 70000),
    VolatileToken("LINK", "0x514910771af9ca656af840dff83e8264ecf986ca", 18, 16000, 15),
    VolatileToken("UNI",  "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", 18, 30000, 8),
    VolatileToken("AAVE", "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", 18, 2500, 100),
    VolatileToken("MKR",  "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", 18, 165, 1500),
    VolatileToken("CRV",  "0xd533a949740bb3306d119cc777fa900ba034cd52", 18, 600000, 0.40),
    VolatileToken("LDO",  "0x5a98fcbea516cf06857215779fd812ca3bef1b32", 18, 125000, 2.0),
    VolatileToken("COMP", "0xc00e94cb662c3520282e6f5717214004a7f26888", 18, 5000, 50),
    VolatileToken("SUSHI", "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2", 18, 250000, 1.0),
    VolatileToken("PEPE", "0x6982508145454ce325ddbe47a25d4ec3d2311933", 18, 16_000_000_000, 0.000015),
    VolatileToken("SHIB", "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce", 18, 11_000_000_000, 0.000022),
)

VOLATILE_BY_ADDRESS: dict[str, VolatileToken] = {t.address: t for t in VOLATILE_TOKENS}


ALL_TRACKED_ADDRESSES: list[str] = [t.address for t in STABLES] + [t.address for t in VOLATILE_TOKENS]
```

Key changes vs. today:
- `StableToken` extends `Token` with `peg_currency` + `price_usd_approx`.
- `STABLES` shape is `tuple[StableToken, ...]` (was `tuple[Token, ...]`).
- `STABLES_BY_ADDRESS` typed as `dict[str, StableToken]`.
- 6 new entries appended after the existing USDT/USDC/DAI.
- `VolatileToken` body slimmed: the docstring fields-as-comments are dropped (now only the type annotations remain), keeping the API identical.

- [ ] **Step 2: Verify the file imports cleanly**

```bash
cd backend && .venv/bin/python -c "from app.realtime.tokens import STABLES, STABLES_BY_ADDRESS, VOLATILE_TOKENS, ALL_TRACKED_ADDRESSES; print(len(STABLES), 'stables /', len(VOLATILE_TOKENS), 'volatiles')"
```

Expected: prints `9 stables / 12 volatiles`.

- [ ] **Step 3: Verify the parser still imports** (it consumes `STABLES_BY_ADDRESS`)

```bash
cd backend && .venv/bin/python -c "from app.realtime.parser import parse_erc20_log; print('ok')"
```

Expected: prints `ok`. (No assertion fired even though parser code still uses `stable.symbol`/`stable.decimals`/etc — those attributes exist on `StableToken` via inheritance from `Token`.)

- [ ] **Step 4: Existing parser tests still pass**

```bash
cd backend && .venv/bin/pytest tests/test_realtime_parser.py -v
```

Expected: all green. The parser hasn't been changed yet (Task 2), so the USD-pegged path still uses `amount` for the threshold compare; existing USDC/USDT/DAI tests behave identically.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/tokens.py
git commit -m "feat(stables): StableToken dataclass + 6 new entries (PYUSD, FDUSD, USDS, GHO, EUROC, ZCHF)"
```

---

## Task 2 — Parser: switch threshold compare from native amount to USD notional

**Files:**
- Modify: `backend/app/realtime/parser.py`

The parser has TWO paths that compare a stable transfer against the threshold: one in the confirmed-tx Transfer-log decoder (`parse_erc20_log`) and one in the pending-tx parallel decoder. Both must change identically.

- [ ] **Step 1: Locate the confirmed-tx stable path**

Inside `backend/app/realtime/parser.py`, find this block (around lines 108–123):

```python
    stable = STABLES_BY_ADDRESS.get(addr)
    if stable is not None:
        amount = raw / (10**stable.decimals)
        if amount < threshold_usd:
            return None
        return WhaleTransfer(
            tx_hash=log["transactionHash"],
            log_index=_parse_hex(log.get("logIndex")),
            block_number=_parse_hex(log.get("blockNumber")),
            ts=block_ts,
            from_addr=from_addr,
            to_addr=to_addr,
            asset=stable.symbol,
            amount=amount,
            usd_value=amount,
        )
```

Replace with:

```python
    stable = STABLES_BY_ADDRESS.get(addr)
    if stable is not None:
        amount = raw / (10**stable.decimals)
        usd = amount * stable.price_usd_approx
        if usd < threshold_usd:
            return None
        return WhaleTransfer(
            tx_hash=log["transactionHash"],
            log_index=_parse_hex(log.get("logIndex")),
            block_number=_parse_hex(log.get("blockNumber")),
            ts=block_ts,
            from_addr=from_addr,
            to_addr=to_addr,
            asset=stable.symbol,
            amount=amount,
            usd_value=usd,
        )
```

The two changes: introduce `usd = amount * stable.price_usd_approx`, then use `usd` for the threshold compare AND for `usd_value=usd`.

- [ ] **Step 2: Locate the pending-tx stable path**

Search the same file for the second occurrence — around lines 215–235 in a `parse_pending_erc20_log` (or similarly named) function. It has the same shape: a `STABLES_BY_ADDRESS.get(...)` lookup, followed by an `amount = raw / 10**decimals`, threshold compare, and a `WhaleTransfer`-like return setting `usd_value=amount`.

The exact existing code looks like:

```python
        amount = raw / (10**stable.decimals)
        if amount < threshold_usd:
            return None
        return PendingWhale(
            ...
            asset=stable.symbol,
            amount=amount,
            usd_value=amount,
            ...
        )
```

(The exact wrapper class — `PendingWhale` or similar — varies; what matters is the pattern.)

Replace the threshold compare and `usd_value` assignment the same way:

```python
        amount = raw / (10**stable.decimals)
        usd = amount * stable.price_usd_approx
        if usd < threshold_usd:
            return None
        return PendingWhale(
            ...
            asset=stable.symbol,
            amount=amount,
            usd_value=usd,
            ...
        )
```

If the pending path doesn't exist as a separate function (the file may use a single shared decoder), apply the change once. Search the file for `usd_value=amount` to find all candidate sites tied to stables; any line that pairs a stable threshold compare against `amount` becomes a USD compare.

- [ ] **Step 3: Existing tests still pass (USD-pegged sanity)**

```bash
cd backend && .venv/bin/pytest tests/test_realtime_parser.py -v
```

Expected: all green. USDC/USDT/DAI all have `price_usd_approx == 1.0` so `usd == amount`; the threshold compare gives identical answer; existing assertions still hold.

If a test fails because it asserts `usd_value == amount` but now compares to a coin with non-1.0 rate, that's NOT possible because all existing tests use USDT/USDC/DAI (1.0 rate). If a test fails for any other reason, STOP and report.

- [ ] **Step 4: Commit**

```bash
git add backend/app/realtime/parser.py
git commit -m "feat(stables): parser uses price_usd_approx for stable threshold + usd_value"
```

---

## Task 3 — Parser tests for EUROC, ZCHF, PYUSD

**Files:**
- Modify: `backend/tests/test_realtime_parser.py`

Append three new test functions at the end of the file. They cover:
- EUROC: 250k EUROC at €1 = $270k USD notional, threshold $250k → passes
- ZCHF: 230k ZCHF at CHF1 = $253k USD notional, threshold $250k → passes
- PYUSD: 1.5M PYUSD at $1 = $1.5M, threshold $1M → passes (USD-pegged sanity)

- [ ] **Step 1: Append the tests**

Append these three functions to the end of `backend/tests/test_realtime_parser.py`:

```python
def test_parse_erc20_log_euroc_uses_fx_threshold():
    """250k EUROC ≈ $270k notional; passes a $250k USD threshold."""
    log = {
        "address": "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(250_000 * 10**6),  # 250k EUROC (6 decimals)
        "blockNumber": "0x10",
        "transactionHash": "0xeur1",
        "logIndex": "0x1",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "EUROC"
    assert row.amount == 250_000.0
    # 250000 EUROC × 1.08 EUR→USD ≈ 270k. Use approx compare for float safety.
    assert abs(row.usd_value - 270_000.0) < 1.0


def test_parse_erc20_log_zchf_uses_fx_threshold():
    """230k ZCHF ≈ $253k notional; passes a $250k USD threshold."""
    log = {
        "address": "0xb58e61c3098d85632df34eecfb899a1ed80921cb",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(230_000 * 10**18),  # 230k ZCHF (18 decimals)
        "blockNumber": "0x11",
        "transactionHash": "0xchf1",
        "logIndex": "0x2",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=250_000.0)
    assert row is not None
    assert row.asset == "ZCHF"
    assert row.amount == 230_000.0
    # 230000 × 1.10 = 253k
    assert abs(row.usd_value - 253_000.0) < 1.0


def test_parse_erc20_log_pyusd_usd_pegged_sanity():
    """USD-pegged stable (PYUSD): amount == usd_value."""
    log = {
        "address": "0x6c3ea9036406852006290770bedfcaba0e23a0e8",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": hex(1_500_000 * 10**6),  # 1.5M PYUSD (6 decimals)
        "blockNumber": "0x12",
        "transactionHash": "0xusd1",
        "logIndex": "0x3",
    }
    row = parse_erc20_log(log, block_ts=BLOCK_TS, threshold_usd=1_000_000.0)
    assert row is not None
    assert row.asset == "PYUSD"
    assert row.amount == 1_500_000.0
    assert row.usd_value == 1_500_000.0
```

- [ ] **Step 2: Run the test file**

```bash
cd backend && .venv/bin/pytest tests/test_realtime_parser.py -v
```

Expected: all tests pass — the existing ones (USDT/USDC/DAI etc.) plus the 3 new ones.

If EUROC or ZCHF tests fail because `row is None`, the parser threshold compare didn't get switched in Task 2 — go back and fix.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_realtime_parser.py
git commit -m "test(stables): EUROC + ZCHF FX threshold + PYUSD USD-pegged sanity"
```

---

## Task 4 — Backend `WhaleAsset` Literal expansion

**Files:**
- Modify: `backend/app/api/schemas.py`

- [ ] **Step 1: Replace the WhaleAsset Literal**

In `backend/app/api/schemas.py` find (around line 78):

```python
WhaleAsset = Literal["ETH", "USDT", "USDC", "DAI", "ANY"]
```

Replace with:

```python
WhaleAsset = Literal[
    "ETH",
    "USDT", "USDC", "DAI",
    "PYUSD", "FDUSD", "USDS", "GHO", "EUROC", "ZCHF",
    "ANY",
]
```

- [ ] **Step 2: Verify the test suite still passes**

```bash
cd backend && .venv/bin/pytest -q 2>&1 | tail -10
```

Expected: no new failures. The pre-existing 2 `test_flows_api` failures (unrelated, exist on main) may still appear; ignore those.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/schemas.py
git commit -m "feat(stables): expand WhaleAsset Literal with 6 new symbols"
```

---

## Task 5 — Frontend: `WhaleAsset` type + asset-filter dropdown

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/WhaleTransfersPanel.tsx`

- [ ] **Step 1: Update the TS type literal**

In `frontend/src/api.ts` find (around line 122):

```typescript
export type WhaleAsset = "ETH" | "USDT" | "USDC" | "DAI";
```

Replace with:

```typescript
export type WhaleAsset =
  | "ETH"
  | "USDT" | "USDC" | "DAI"
  | "PYUSD" | "FDUSD" | "USDS" | "GHO" | "EUROC" | "ZCHF";
```

(The frontend's `WhaleAsset` doesn't include `"ANY"` — `"ALL"` is used as the dropdown's "no filter" sentinel and translated to `undefined` at fetch time. This stays unchanged.)

- [ ] **Step 2: Update the asset-filter dropdown**

In `frontend/src/components/WhaleTransfersPanel.tsx` find (around line 56):

```typescript
const ASSET_OPTIONS: readonly { value: WhaleAsset | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "ETH", label: "ETH" },
  { value: "USDT", label: "USDT" },
  { value: "USDC", label: "USDC" },
  { value: "DAI", label: "DAI" },
] as const;
```

Replace with:

```typescript
const ASSET_OPTIONS: readonly { value: WhaleAsset | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "ETH", label: "ETH" },
  { value: "USDT", label: "USDT" },
  { value: "USDC", label: "USDC" },
  { value: "DAI", label: "DAI" },
  { value: "PYUSD", label: "PYUSD" },
  { value: "FDUSD", label: "FDUSD" },
  { value: "USDS", label: "USDS" },
  { value: "GHO", label: "GHO" },
  { value: "EUROC", label: "EUROC" },
  { value: "ZCHF", label: "ZCHF" },
] as const;
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/WhaleTransfersPanel.tsx
git commit -m "feat(stables): expand frontend WhaleAsset + asset-filter dropdown"
```

---

## Task 6 — Dune SQL: include the 6 new symbols

**Files:**
- Modify: `backend/dune/stablecoin_supply.sql`

- [ ] **Step 1: Update both CTE clauses**

Open `backend/dune/stablecoin_supply.sql`. Find both occurrences of:

```sql
    and symbol in ('USDT','USDC','DAI')
```

(One occurrence in the `mints` CTE, one in the `burns` CTE.) Replace BOTH with:

```sql
    and symbol in ('USDT','USDC','DAI','PYUSD','FDUSD','USDS','GHO','EUROC','ZCHF')
```

- [ ] **Step 2: Commit**

```bash
git add backend/dune/stablecoin_supply.sql
git commit -m "feat(stables): Dune stablecoin_supply query covers 9 stables"
```

(The Dune query is the source of truth in our repo; it doesn't run against Dune from here. Operator action lives in Task 7.)

---

## Task 7 — CLAUDE.md note + manual smoke

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the M3 milestone description**

Open `CLAUDE.md`. Find the M3 milestone line (around line 67). Today it reads:

```markdown
- M3 ✅ whale tracking — Alchemy WS listener persists ETH + USDT/USDC/DAI transfers above threshold to `transfers`; `/api/whales/transfers` exposes them with CEX labels; live-refreshing panel. Needs `ALCHEMY_API_KEY`; thresholds via `WHALE_ETH_THRESHOLD` / `WHALE_STABLE_THRESHOLD_USD`.
```

Replace with:

```markdown
- M3 ✅ whale tracking — Alchemy WS listener persists ETH + 9 stables (USDT/USDC/DAI/PYUSD/FDUSD/USDS/GHO/EUROC/ZCHF) transfers above threshold to `transfers`; non-USD stables (EUROC, ZCHF) use `price_usd_approx` per token for FX-aware thresholds; `/api/whales/transfers` exposes them with CEX labels; live-refreshing panel. Needs `ALCHEMY_API_KEY`; thresholds via `WHALE_ETH_THRESHOLD` / `WHALE_STABLE_THRESHOLD_USD`. **After deploy:** re-paste `backend/dune/stablecoin_supply.sql` into the existing `DUNE_QUERY_ID_STABLECOIN_SUPPLY` query on Dune and click Save so the supply panel covers the new stables.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(stables): note expanded coverage + Dune-resave operator step in CLAUDE.md"
```

- [ ] **Step 3: Manual smoke (post-merge, on the running stack)**

This step is a checklist for the operator (you), not a subagent action — it runs against the live stack after the PR merges and `make down && make up` completes:

- [ ] **Whale Transfers panel asset-filter dropdown** shows 11 options: All, ETH, USDT, USDC, DAI, PYUSD, FDUSD, USDS, GHO, EUROC, ZCHF.
- [ ] Filter by `EUROC`, then `ZCHF`, then `PYUSD`. Each filter narrows correctly (no errors). With no recent activity, lists may be empty — that's fine; what matters is no client-side errors.
- [ ] Open Dune at `https://dune.com/queries/<DUNE_QUERY_ID_STABLECOIN_SUPPLY>` (the ID from your `.env`). Replace the query body with the new `backend/dune/stablecoin_supply.sql` content. Click **Save**. The query re-runs in the next worker `sync_dune_flows` cycle (~5 min).
- [ ] After the next sync, `<StablecoinSupplyPanel>` should render rows for the new 6 symbols (visible mint/burn data for any active coin). For coins with no recent activity in the 30-day window, the panel will show 0 — also fine.
- [ ] Tail the realtime listener to verify it doesn't crash on the new tokens:
  ```bash
  docker compose logs -f realtime --tail=50
  ```
  No `KeyError` or `AttributeError` related to the new tokens.

---

## Self-review

**Spec coverage:**
- Goal (9 stables tracked, FX-aware thresholds) → Tasks 1 + 2 ship the registry + parser change.
- `StableToken` dataclass with `peg_currency` + `price_usd_approx` → Task 1.
- 6 new entries with verified addresses + decimals → Task 1.
- Parser switches threshold compare to USD notional → Task 2 (both confirmed + pending paths).
- `WhaleAsset` Literal expanded backend + frontend → Tasks 4 + 5.
- Asset-filter dropdown options → Task 5.
- Dune SQL update → Task 6.
- Operator action (re-paste Dune SQL) → documented in Task 7's CLAUDE.md update + manual smoke.
- Tests for EUROC FX, ZCHF FX, PYUSD USD-pegged → Task 3.
- Existing USDT/USDC/DAI tests continue passing → asserted in Tasks 1, 2, 3 verify steps.
- "No new dependencies, no migrations, no env vars" → upheld across all tasks.

**Placeholder scan:** None — every step has runnable code or commands.

**Type consistency:**
- `StableToken` defined in Task 1; consumed (via `STABLES_BY_ADDRESS.get(addr).price_usd_approx`) in Task 2's parser change; consumed by tests in Task 3.
- `WhaleAsset` Literal: backend defined in Task 4, frontend mirrored in Task 5 (excludes `"ANY"` because the frontend uses `"ALL"` as the no-filter sentinel — see existing `ASSET_OPTIONS` shape).
- `STABLES_BY_ADDRESS` keys are lowercase 0x addresses — Task 1 enforces; Task 2 reads the same.
- Decimals: USDT/USDC/PYUSD/EUROC at 6, DAI/FDUSD/USDS/GHO/ZCHF at 18 — verified per spec.
- Test assertions use `abs(row.usd_value - ...) < 1.0` for float-safe FX compares.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-stablecoin-coverage.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
