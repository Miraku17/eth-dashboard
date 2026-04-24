# Smart-Money Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a daily-refreshed leaderboard of the top 50 ETH traders on mainnet DEXes, ranked by 30-day realized USD PnL on WETH trades, surfaced as a dashboard panel backed by a Dune-sourced Postgres snapshot.

**Architecture:** A single Dune query returns raw WETH trade rows for the top 500 wallets by 30d volume. A pure-Python FIFO engine computes per-wallet realized PnL, win rate, and unrealized mark-to-market. Results land in a new `smart_money_leaderboard` table as one snapshot per daily run, exposed read-only via `/api/leaderboard/smart-money` and rendered as a table panel in the React dashboard.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, arq (Redis queue), Dune Analytics REST API, React 18 + Vite + TypeScript, TanStack Query, Tailwind, pytest with testcontainers.

**Spec:** `docs/superpowers/specs/2026-04-24-smart-money-leaderboard-design.md`

---

## File Structure

Files to create:

- `backend/dune/smart_money_leaderboard.sql` — Dune SQL
- `backend/app/services/pnl_engine.py` — pure FIFO PnL engine
- `backend/app/services/leaderboard_sync.py` — orchestration (Dune call → engine → persistence)
- `backend/app/workers/leaderboard_jobs.py` — arq job wrapper
- `backend/alembic/versions/0004_smart_money_leaderboard.py` — schema migration
- `backend/app/api/leaderboard.py` — read endpoint
- `frontend/src/components/SmartMoneyLeaderboard.tsx` — dashboard panel
- `backend/tests/test_pnl_engine.py` — pure unit tests
- `backend/tests/test_leaderboard_sync.py` — integration test
- `backend/tests/test_leaderboard_api.py` — API test
- `backend/tests/fixtures/dune_smart_money_sample.json` — fixture file

Files to modify:

- `backend/app/core/config.py` — add `dune_query_id_smart_money_leaderboard`
- `backend/app/core/models.py` — add `SmartMoneyLeaderboard` SQLAlchemy model
- `backend/app/api/schemas.py` — add leaderboard response schemas
- `backend/app/main.py` — register the new router
- `backend/app/workers/arq_settings.py` — add daily cron + startup enqueue
- `backend/app/api/health.py` — add `smart_money` freshness entry
- `frontend/src/api.ts` — add `fetchSmartMoneyLeaderboard`
- `frontend/src/App.tsx` — mount `SmartMoneyLeaderboard` panel
- `CLAUDE.md` — mark milestone status
- `docker-compose.yml` or `.env.example` (if present) — document new env var

---

## Task 1: Schema — Alembic migration for `smart_money_leaderboard`

**Files:**
- Create: `backend/alembic/versions/0004_smart_money_leaderboard.py`

- [ ] **Step 1: Create the migration file**

```python
"""smart money leaderboard snapshots

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_money_leaderboard",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_days", sa.SmallInteger, nullable=False),
        sa.Column("rank", sa.SmallInteger, nullable=False),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("trade_count", sa.Integer, nullable=False),
        sa.Column("volume_usd", sa.Numeric(24, 2), nullable=False),
        sa.Column("weth_bought", sa.Numeric(36, 18), nullable=False),
        sa.Column("weth_sold", sa.Numeric(36, 18), nullable=False),
    )
    op.create_index(
        "ix_leaderboard_latest",
        "smart_money_leaderboard",
        ["window_days", sa.text("snapshot_at DESC"), "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_leaderboard_latest", table_name="smart_money_leaderboard")
    op.drop_table("smart_money_leaderboard")
```

- [ ] **Step 2: Verify migration applies cleanly**

Run:
```bash
cd backend && .venv/bin/alembic upgrade head
.venv/bin/alembic downgrade -1
.venv/bin/alembic upgrade head
```

Expected: no errors, three clean upgrade/downgrade/upgrade cycles.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0004_smart_money_leaderboard.py
git commit -m "feat(v2-smart-money): add smart_money_leaderboard table"
```

---

## Task 2: SQLAlchemy model for `smart_money_leaderboard`

**Files:**
- Modify: `backend/app/core/models.py`
- Test: `backend/tests/test_db_schema.py` (add an assertion)

- [ ] **Step 1: Add the model**

Append to `backend/app/core/models.py` (at the end of the file, after `OrderFlow`):

```python
import uuid as _uuid

from sqlalchemy.dialects.postgresql import UUID


class SmartMoneyLeaderboard(Base):
    """Per-wallet realized-PnL ranking snapshot. One `run_id` per daily refresh. (v2)"""
    __tablename__ = "smart_money_leaderboard"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    realized_pnl_usd: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    unrealized_pnl_usd: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_usd: Mapped[float] = mapped_column(Numeric(24, 2), nullable=False)
    weth_bought: Mapped[float] = mapped_column(Numeric(36, 18), nullable=False)
    weth_sold: Mapped[float] = mapped_column(Numeric(36, 18), nullable=False)
```

Also update the top-of-file imports to include `Numeric` (already there), `BigInteger` (already there), and `String`, `Integer` (already there). Add `Mapped, mapped_column` (already imported). Nothing else new at module-level — add the `import uuid as _uuid` and `from sqlalchemy.dialects.postgresql import UUID` either next to the existing imports or just above the class (prefer file top).

- [ ] **Step 2: Add a schema smoke test**

Append to `backend/tests/test_db_schema.py`:

```python
def test_smart_money_leaderboard_table_exists(migrated_engine):
    from sqlalchemy import inspect
    insp = inspect(migrated_engine)
    cols = {c["name"] for c in insp.get_columns("smart_money_leaderboard")}
    assert cols == {
        "id", "run_id", "snapshot_at", "window_days", "rank",
        "wallet_address", "label",
        "realized_pnl_usd", "unrealized_pnl_usd", "win_rate",
        "trade_count", "volume_usd", "weth_bought", "weth_sold",
    }
    idx = {i["name"] for i in insp.get_indexes("smart_money_leaderboard")}
    assert "ix_leaderboard_latest" in idx
```

- [ ] **Step 3: Run the test — expect PASS**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_db_schema.py::test_smart_money_leaderboard_table_exists -v
```

Expected: PASS. (Migration already exists from Task 1; this just confirms ORM + migration agree.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/models.py backend/tests/test_db_schema.py
git commit -m "feat(v2-smart-money): add SmartMoneyLeaderboard ORM model"
```

---

## Task 3: Config — add `dune_query_id_smart_money_leaderboard`

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py` (add assertion)

- [ ] **Step 1: Add the setting**

In `backend/app/core/config.py`, add inside the `Settings` class next to the other `dune_query_id_*` fields (around line 25):

```python
    dune_query_id_smart_money_leaderboard: int = 0
```

- [ ] **Step 2: Extend config test**

In `backend/tests/test_config.py`, find the existing test that inspects Dune query ID defaults and add an assertion for the new field. If no such test exists, add:

```python
def test_smart_money_query_id_defaults_to_zero(monkeypatch):
    # Explicitly ensure env var is absent so we observe the default.
    monkeypatch.delenv("DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD", raising=False)
    from app.core.config import Settings
    s = Settings()
    assert s.dune_query_id_smart_money_leaderboard == 0
```

- [ ] **Step 3: Run the test — expect PASS**

```bash
cd backend && .venv/bin/pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(v2-smart-money): add dune_query_id_smart_money_leaderboard setting"
```

---

## Task 4: Dune SQL — `smart_money_leaderboard.sql`

**Files:**
- Create: `backend/dune/smart_money_leaderboard.sql`

This SQL runs on Dune, not in our test suite. Correctness is validated manually after the query is registered (see Task 11). This task is just the checked-in artifact.

- [ ] **Step 1: Write the SQL**

Create `backend/dune/smart_money_leaderboard.sql`:

```sql
-- Smart-money leaderboard candidate feed (v2).
-- Returns raw WETH trade rows for the top 500 wallets by 30d WETH volume on
-- Ethereum mainnet DEXes. The backend reconstructs per-wallet FIFO realized
-- PnL from these rows.
--
-- Semantics:
--   side='buy'  → wallet bought WETH (spent something for ETH exposure)
--   side='sell' → wallet sold WETH  (closed out ETH exposure)
--   weth_amount is the WETH leg of the trade; amount_usd is Dune's USD tag.
--
-- Router/aggregator EOAs are excluded so the leaderboard surfaces
-- end-user wallets rather than 1inch, KyberSwap, etc.

WITH router_exclusions (address) AS (
  VALUES
    (0x1111111254EEB25477B68fb85Ed929f73A960582),  -- 1inch v5 router
    (0x6131B5fae19EA4f9D964eAc0408E4408b66337b5),  -- KyberSwap MetaAggregator
    (0xdef1c0ded9bec7f1a1670819833240f027b25eff),  -- 0x Exchange Proxy
    (0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45),  -- Uniswap Universal Router
    (0xE592427A0AEce92De3Edee1F18E0157C05861564),  -- Uniswap V3 SwapRouter
    (0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD),  -- Uniswap Universal Router v1_2
    (0x9008D19f58AAbD9eD0D60971565AA8510560ab41)   -- CoW Protocol GPv2Settlement
),
windowed_trades AS (
  SELECT
    tx_from AS trader,
    block_time,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN 'buy'
      ELSE 'sell'
    END AS side,
    CASE
      WHEN token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 THEN token_bought_amount
      ELSE token_sold_amount
    END AS weth_amount,
    amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    -- Partition pruning: both date and timestamp predicates so DuneSQL skips
    -- irrelevant daily partitions AND bounds the rolling window to 30d.
    AND block_date >= current_date - interval '30' day
    AND block_time > now() - interval '30' day
    AND (
      token_bought_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
      OR token_sold_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
    )
    AND amount_usd IS NOT NULL
    AND amount_usd > 0
    AND tx_from NOT IN (SELECT address FROM router_exclusions)
),
candidates AS (
  SELECT trader
  FROM windowed_trades
  GROUP BY trader
  ORDER BY SUM(amount_usd) DESC
  LIMIT 500
)
SELECT
  CAST(t.trader AS VARCHAR) AS trader,
  t.block_time,
  t.side,
  CAST(t.weth_amount AS VARCHAR) AS weth_amount,
  CAST(t.amount_usd AS VARCHAR) AS amount_usd,
  l.name AS label
FROM windowed_trades t
JOIN candidates c USING (trader)
LEFT JOIN labels.addresses l
  ON l.address = t.trader AND l.blockchain = 'ethereum'
ORDER BY t.trader, t.block_time;
```

Casting numeric/address columns to `VARCHAR` in the final projection forces Dune to serialize as strings, which we then parse with `Decimal(str(...))` in Python — avoiding float roundtrip loss. `tx_from` is the EOA that signed the transaction; `taker` would include router contracts.

- [ ] **Step 2: Commit**

```bash
git add backend/dune/smart_money_leaderboard.sql
git commit -m "feat(v2-smart-money): add Dune SQL for leaderboard candidate feed"
```

---

## Task 5: FIFO PnL engine — failing test for single round-trip

**Files:**
- Create: `backend/tests/test_pnl_engine.py`
- (Referenced, does not yet exist): `backend/app/services/pnl_engine.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pnl_engine.py`:

```python
"""Unit tests for the FIFO realized-PnL engine (pure, no I/O)."""
from decimal import Decimal

import pytest

from app.services.pnl_engine import WalletPnL, compute_realized_pnl


def _row(trader, side, weth, usd, *, t="2026-04-01T00:00:00Z", label=None):
    return {
        "trader": trader,
        "block_time": t,
        "side": side,
        "weth_amount": str(weth),
        "amount_usd": str(usd),
        "label": label,
    }


def test_single_round_trip_profit():
    rows = [
        _row("0xaaa", "buy",  Decimal("10"), Decimal("30000"), t="2026-04-01T00:00:00Z"),
        _row("0xaaa", "sell", Decimal("10"), Decimal("35000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    assert len(result) == 1
    r = result[0]
    assert isinstance(r, WalletPnL)
    assert r.wallet == "0xaaa"
    assert r.realized_pnl_usd == Decimal("5000.00")
    assert r.unrealized_pnl_usd is None        # no open position
    assert r.win_rate == Decimal("1.0000")     # 1/1 winning sell
    assert r.trade_count == 2
    assert r.volume_usd == Decimal("65000.00")
    assert r.weth_bought == Decimal("10")
    assert r.weth_sold == Decimal("10")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/bin/pytest tests/test_pnl_engine.py::test_single_round_trip_profit -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.pnl_engine'`.

- [ ] **Step 3: Create the minimal implementation**

Create `backend/app/services/pnl_engine.py`:

```python
"""Pure FIFO realized-PnL engine.

Takes raw Dune trade rows for multiple wallets (already sorted by
(trader, block_time)) and produces a ranked list of per-wallet PnL records.
No I/O — fully deterministic given its inputs.
"""
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque


@dataclass(frozen=True)
class WalletPnL:
    wallet: str
    label: str | None
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal | None
    win_rate: Decimal | None
    trade_count: int
    volume_usd: Decimal
    weth_bought: Decimal
    weth_sold: Decimal


def _d(x) -> Decimal:
    """Safe conversion from Dune output (str/float/int) to Decimal."""
    return Decimal(str(x))


def _process_wallet(
    wallet: str,
    label: str | None,
    trades: list[dict],
    window_end_eth_price: Decimal | None,
) -> WalletPnL:
    lots: Deque[list[Decimal]] = deque()  # each lot is [weth_remaining, usd_cost_remaining]
    realized = Decimal("0")
    wins = 0
    losses = 0
    volume_usd = Decimal("0")
    weth_bought = Decimal("0")
    weth_sold = Decimal("0")

    for tr in trades:
        weth = _d(tr["weth_amount"])
        usd = _d(tr["amount_usd"])
        volume_usd += usd
        side = tr["side"]

        if side == "buy":
            weth_bought += weth
            lots.append([weth, usd])
        elif side == "sell":
            weth_sold += weth
            to_close = weth
            sell_price = usd / weth if weth > 0 else Decimal("0")
            sell_realized = Decimal("0")
            consumed_any = False
            while to_close > 0 and lots:
                lot_weth, lot_cost = lots[0]
                consumed = min(lot_weth, to_close)
                cost_basis = lot_cost * (consumed / lot_weth) if lot_weth > 0 else Decimal("0")
                proceeds = sell_price * consumed
                sell_realized += proceeds - cost_basis
                lot_weth -= consumed
                lot_cost -= cost_basis
                to_close -= consumed
                consumed_any = True
                if lot_weth == 0:
                    lots.popleft()
                else:
                    lots[0] = [lot_weth, lot_cost]
            # Any leftover `to_close` > 0 here is pre-window inventory: skip.
            if consumed_any:
                realized += sell_realized
                if sell_realized > 0:
                    wins += 1
                else:
                    losses += 1

    # Unrealized mark-to-market on any open position.
    unrealized: Decimal | None = None
    if lots and window_end_eth_price is not None:
        open_weth = sum((lot[0] for lot in lots), Decimal("0"))
        open_cost = sum((lot[1] for lot in lots), Decimal("0"))
        if open_weth > 0:
            avg_cost_per_weth = open_cost / open_weth
            unrealized = (window_end_eth_price - avg_cost_per_weth) * open_weth

    total_closed = wins + losses
    win_rate = (Decimal(wins) / Decimal(total_closed)) if total_closed > 0 else None

    return WalletPnL(
        wallet=wallet,
        label=label,
        realized_pnl_usd=realized.quantize(Decimal("0.01")),
        unrealized_pnl_usd=unrealized.quantize(Decimal("0.01")) if unrealized is not None else None,
        win_rate=win_rate.quantize(Decimal("0.0001")) if win_rate is not None else None,
        trade_count=len(trades),
        volume_usd=volume_usd.quantize(Decimal("0.01")),
        weth_bought=weth_bought,
        weth_sold=weth_sold,
    )


def compute_realized_pnl(
    rows: list[dict],
    window_end_eth_price: Decimal | None,
) -> list[WalletPnL]:
    """Group rows by wallet, compute FIFO PnL, return a list.

    Caller is responsible for sorting `rows` by (trader, block_time). The
    Dune query's `ORDER BY t.trader, t.block_time` clause handles this.
    """
    out: list[WalletPnL] = []
    if not rows:
        return out

    current_trader = rows[0]["trader"]
    current_label = rows[0].get("label")
    buf: list[dict] = []
    for r in rows:
        if r["trader"] != current_trader:
            out.append(_process_wallet(current_trader, current_label, buf, window_end_eth_price))
            current_trader = r["trader"]
            current_label = r.get("label")
            buf = []
        buf.append(r)
    out.append(_process_wallet(current_trader, current_label, buf, window_end_eth_price))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && .venv/bin/pytest tests/test_pnl_engine.py::test_single_round_trip_profit -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pnl_engine.py backend/tests/test_pnl_engine.py
git commit -m "feat(v2-smart-money): add FIFO PnL engine with single-round-trip test"
```

---

## Task 6: FIFO engine — cover remaining branches

**Files:**
- Modify: `backend/tests/test_pnl_engine.py`

All tests below should pass against the engine from Task 5. If any fail, fix the engine (do not weaken the test).

- [ ] **Step 1: Add loss-case test**

```python
def test_single_round_trip_loss():
    rows = [
        _row("0xbbb", "buy",  Decimal("10"), Decimal("35000")),
        _row("0xbbb", "sell", Decimal("10"), Decimal("30000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3000"))
    assert result[0].realized_pnl_usd == Decimal("-5000.00")
    assert result[0].win_rate == Decimal("0.0000")
```

- [ ] **Step 2: Add partial-close test**

```python
def test_partial_close_leaves_open_position():
    rows = [
        _row("0xccc", "buy",  Decimal("10"), Decimal("30000")),
        _row("0xccc", "sell", Decimal("4"),  Decimal("14000"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3600"))
    r = result[0]
    # Cost basis of 4 WETH = 4/10 * 30000 = 12000. Proceeds = 14000. Realized = 2000.
    assert r.realized_pnl_usd == Decimal("2000.00")
    # 6 WETH open at avg cost 3000. Mark at 3600. Unrealized = 6 * 600 = 3600.
    assert r.unrealized_pnl_usd == Decimal("3600.00")
    assert r.weth_bought == Decimal("10")
    assert r.weth_sold == Decimal("4")
```

- [ ] **Step 3: Add multi-lot FIFO ordering test**

```python
def test_multi_lot_fifo_order():
    rows = [
        _row("0xddd", "buy",  Decimal("5"), Decimal("10000"),  t="2026-04-01T00:00:00Z"),
        _row("0xddd", "buy",  Decimal("5"), Decimal("15000"),  t="2026-04-02T00:00:00Z"),
        _row("0xddd", "sell", Decimal("7"), Decimal("21000"),  t="2026-04-03T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3100"))
    r = result[0]
    # First lot fully consumed: cost=10000, proceeds=5/7*21000=15000, pnl=+5000.
    # Next 2 WETH from second lot: cost=2/5*15000=6000, proceeds=2/7*21000=6000, pnl=0.
    # Realized = 5000. Open = 3 WETH at cost 9000 (3/5*15000). Mark 3100 → 9300. Unrealized = 300.
    assert r.realized_pnl_usd == Decimal("5000.00")
    assert r.unrealized_pnl_usd == Decimal("300.00")
```

- [ ] **Step 4: Add pre-window-inventory (skipped sell) test**

```python
def test_sell_without_prior_buy_skipped():
    rows = [
        # This sell has no preceding buy in the window — pre-window inventory.
        _row("0xeee", "sell", Decimal("10"), Decimal("35000"), t="2026-04-01T00:00:00Z"),
        _row("0xeee", "buy",  Decimal("5"),  Decimal("15000"), t="2026-04-02T00:00:00Z"),
        _row("0xeee", "sell", Decimal("5"),  Decimal("17500"), t="2026-04-03T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    # Only the second round-trip counts: cost=15000, proceeds=17500 → 2500.
    # First sell hit empty deque, fully skipped, not counted toward win_rate.
    assert r.realized_pnl_usd == Decimal("2500.00")
    assert r.win_rate == Decimal("1.0000")  # 1 counted sell, 1 win
    assert r.trade_count == 3               # all rows counted as activity
    assert r.unrealized_pnl_usd is None     # no open position at end
```

- [ ] **Step 5: Add buy-only wallet test**

```python
def test_buy_only_wallet():
    rows = [
        _row("0xfff", "buy", Decimal("3"), Decimal("9000"), t="2026-04-01T00:00:00Z"),
        _row("0xfff", "buy", Decimal("2"), Decimal("6200"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3200"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.win_rate is None               # no closed round-trips
    # 5 WETH open at avg cost (9000+6200)/5 = 3040. Mark 3200 → 16000. Unrealized = 800.
    assert r.unrealized_pnl_usd == Decimal("800.00")
```

- [ ] **Step 6: Add sell-only wallet test (all skipped)**

```python
def test_sell_only_wallet():
    rows = [
        _row("0x111", "sell", Decimal("3"), Decimal("10500"), t="2026-04-01T00:00:00Z"),
        _row("0x111", "sell", Decimal("2"), Decimal("7000"),  t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3500"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("0.00")
    assert r.win_rate is None           # 0 counted closed round-trips
    assert r.unrealized_pnl_usd is None # nothing opened in window
    assert r.trade_count == 2
    assert r.weth_sold == Decimal("5")
    assert r.weth_bought == Decimal("0")
```

- [ ] **Step 7: Add flipper (many round-trips) test**

```python
def test_flipper_win_rate_arithmetic():
    rows = [
        _row("0x222", "buy",  Decimal("1"), Decimal("3000"), t="2026-04-01T00:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3100"), t="2026-04-01T01:00:00Z"),  # +100
        _row("0x222", "buy",  Decimal("1"), Decimal("3100"), t="2026-04-01T02:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3050"), t="2026-04-01T03:00:00Z"),  # -50
        _row("0x222", "buy",  Decimal("1"), Decimal("3050"), t="2026-04-01T04:00:00Z"),
        _row("0x222", "sell", Decimal("1"), Decimal("3200"), t="2026-04-01T05:00:00Z"),  # +150
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3200"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("200.00")
    assert r.win_rate == Decimal("0.6667")  # 2 wins / 3 sells
    assert r.trade_count == 6
    assert r.unrealized_pnl_usd is None
```

- [ ] **Step 8: Add precision test (18-decimal WETH)**

```python
def test_decimal_precision_preserved():
    rows = [
        _row("0x333", "buy",  Decimal("1.123456789012345678"), Decimal("3500.00")),
        _row("0x333", "sell", Decimal("1.123456789012345678"), Decimal("3600.00"),
             t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3600"))
    r = result[0]
    assert r.realized_pnl_usd == Decimal("100.00")
    # weth_bought/sold preserve 18-decimal precision unchanged
    assert r.weth_bought == Decimal("1.123456789012345678")
    assert r.weth_sold == Decimal("1.123456789012345678")
```

- [ ] **Step 9: Add multi-wallet input test**

```python
def test_multi_wallet_produces_one_record_per_wallet():
    rows = [
        _row("0xaaa", "buy",  Decimal("1"), Decimal("3000"), t="2026-04-01T00:00:00Z"),
        _row("0xaaa", "sell", Decimal("1"), Decimal("3100"), t="2026-04-02T00:00:00Z"),
        _row("0xbbb", "buy",  Decimal("2"), Decimal("6000"), t="2026-04-01T00:00:00Z"),
        _row("0xbbb", "sell", Decimal("2"), Decimal("5800"), t="2026-04-02T00:00:00Z"),
    ]
    result = compute_realized_pnl(rows, window_end_eth_price=Decimal("3000"))
    by_wallet = {r.wallet: r for r in result}
    assert set(by_wallet) == {"0xaaa", "0xbbb"}
    assert by_wallet["0xaaa"].realized_pnl_usd == Decimal("100.00")
    assert by_wallet["0xbbb"].realized_pnl_usd == Decimal("-200.00")
```

- [ ] **Step 10: Run all engine tests**

```bash
cd backend && .venv/bin/pytest tests/test_pnl_engine.py -v
```

Expected: all tests PASS. If any fail, fix the engine (e.g. wrap-around FIFO bug, precision quantize issue), re-run until green.

- [ ] **Step 11: Commit**

```bash
git add backend/tests/test_pnl_engine.py backend/app/services/pnl_engine.py
git commit -m "feat(v2-smart-money): cover FIFO edge cases (partial close, skipped sells, flipper)"
```

---

## Task 7: Leaderboard sync — orchestration service

**Files:**
- Create: `backend/app/services/leaderboard_sync.py`
- Create: `backend/tests/fixtures/dune_smart_money_sample.json`
- Create: `backend/tests/test_leaderboard_sync.py`

- [ ] **Step 1: Build the test fixture**

Create `backend/tests/fixtures/dune_smart_money_sample.json`:

```json
[
  {"trader": "0xaaa", "block_time": "2026-04-01T00:00:00Z", "side": "buy",  "weth_amount": "10", "amount_usd": "30000", "label": null},
  {"trader": "0xaaa", "block_time": "2026-04-02T00:00:00Z", "side": "sell", "weth_amount": "10", "amount_usd": "35000", "label": null},
  {"trader": "0xbbb", "block_time": "2026-04-01T00:00:00Z", "side": "buy",  "weth_amount": "5",  "amount_usd": "15000", "label": "Jump Trading"},
  {"trader": "0xbbb", "block_time": "2026-04-02T00:00:00Z", "side": "sell", "weth_amount": "5",  "amount_usd": "14000", "label": "Jump Trading"},
  {"trader": "0xccc", "block_time": "2026-04-01T00:00:00Z", "side": "buy",  "weth_amount": "3",  "amount_usd": "9000",  "label": null},
  {"trader": "0xccc", "block_time": "2026-04-02T00:00:00Z", "side": "sell", "weth_amount": "3",  "amount_usd": "10500", "label": null}
]
```

- [ ] **Step 2: Write the sync test (failing)**

Create `backend/tests/test_leaderboard_sync.py`:

```python
"""Integration tests for leaderboard_sync: Dune rows → FIFO engine → Postgres."""
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import SmartMoneyLeaderboard
from app.services.leaderboard_sync import persist_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "dune_smart_money_sample.json"


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(SmartMoneyLeaderboard).delete()
        s.commit()
        yield s


def test_persist_snapshot_ranks_by_realized_pnl(session):
    rows = json.loads(FIXTURE.read_text())
    run_id = persist_snapshot(
        session,
        rows=rows,
        window_days=30,
        window_end_eth_price=Decimal("3500"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    assert run_id is not None
    records = (
        session.query(SmartMoneyLeaderboard)
        .order_by(SmartMoneyLeaderboard.rank)
        .all()
    )
    assert len(records) == 3
    # 0xaaa: +5000, 0xccc: +1500, 0xbbb: -1000
    assert records[0].wallet_address == "0xaaa"
    assert records[0].rank == 1
    assert float(records[0].realized_pnl_usd) == 5000.00
    assert records[1].wallet_address == "0xccc"
    assert records[2].wallet_address == "0xbbb"
    assert float(records[2].realized_pnl_usd) == -1000.00
    # All rows share the same run_id + snapshot_at.
    assert len({r.run_id for r in records}) == 1
    assert len({r.snapshot_at for r in records}) == 1
    # Label denormalization preserved.
    bbb = next(r for r in records if r.wallet_address == "0xbbb")
    assert bbb.label == "Jump Trading"


def test_persist_snapshot_truncates_to_top_50(session):
    # Build 75 synthetic wallets with decreasing PnL.
    rows = []
    for i in range(75):
        w = f"0x{i:040x}"
        rows.append({
            "trader": w, "block_time": "2026-04-01T00:00:00Z",
            "side": "buy", "weth_amount": "1",
            "amount_usd": str(3000),
            "label": None,
        })
        rows.append({
            "trader": w, "block_time": "2026-04-02T00:00:00Z",
            "side": "sell", "weth_amount": "1",
            # Decreasing profit as i increases: wallet 0 makes +74, wallet 74 makes +0.
            "amount_usd": str(3000 + (74 - i)),
            "label": None,
        })
    persist_snapshot(
        session, rows=rows, window_days=30,
        window_end_eth_price=Decimal("3000"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    rows_written = session.query(SmartMoneyLeaderboard).count()
    assert rows_written == 50
    top = session.query(SmartMoneyLeaderboard).filter_by(rank=1).one()
    assert top.wallet_address == f"0x{0:040x}"


def test_persist_snapshot_skips_on_empty_rows(session):
    run_id = persist_snapshot(
        session, rows=[], window_days=30,
        window_end_eth_price=Decimal("3500"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    assert run_id is None
    assert session.query(SmartMoneyLeaderboard).count() == 0
```

- [ ] **Step 3: Run the tests — expect FAIL**

```bash
cd backend && .venv/bin/pytest tests/test_leaderboard_sync.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.leaderboard_sync'`.

- [ ] **Step 4: Write `leaderboard_sync.py`**

Create `backend/app/services/leaderboard_sync.py`:

```python
"""Orchestrate a Dune-backed smart-money leaderboard refresh.

- Takes raw Dune rows (list[dict]).
- Runs the pure PnL engine.
- Persists the top 50 wallets as a single snapshot (one run_id).

The whole persistence is one transaction — either all rows for a run_id land or
none do. That keeps readers from observing partial snapshots.
"""
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.models import SmartMoneyLeaderboard
from app.services.pnl_engine import WalletPnL, compute_realized_pnl

log = logging.getLogger(__name__)

TOP_N = 50


def persist_snapshot(
    session: Session,
    *,
    rows: list[dict],
    window_days: int,
    window_end_eth_price: Decimal | None,
    snapshot_at: datetime,
) -> uuid.UUID | None:
    """Compute ranking from `rows`, insert a snapshot, return its run_id.

    Returns None when `rows` is empty (so the caller can leave the previous
    snapshot in place and flag the sync as a no-op).
    """
    if not rows:
        log.info("leaderboard sync: empty input, skipping persistence")
        return None

    pnls: list[WalletPnL] = compute_realized_pnl(rows, window_end_eth_price)
    ranked = sorted(pnls, key=lambda p: p.realized_pnl_usd, reverse=True)[:TOP_N]
    run_id = uuid.uuid4()
    session.add_all(
        SmartMoneyLeaderboard(
            run_id=run_id,
            snapshot_at=snapshot_at,
            window_days=window_days,
            rank=rank,
            wallet_address=p.wallet,
            label=p.label,
            realized_pnl_usd=p.realized_pnl_usd,
            unrealized_pnl_usd=p.unrealized_pnl_usd,
            win_rate=p.win_rate,
            trade_count=p.trade_count,
            volume_usd=p.volume_usd,
            weth_bought=p.weth_bought,
            weth_sold=p.weth_sold,
        )
        for rank, p in enumerate(ranked, start=1)
    )
    session.commit()
    log.info(
        "leaderboard sync: wrote %d rows for run_id=%s (top=%s @ $%s)",
        len(ranked), run_id,
        ranked[0].wallet if ranked else None,
        ranked[0].realized_pnl_usd if ranked else None,
    )
    return run_id
```

- [ ] **Step 5: Re-run tests — expect PASS**

```bash
cd backend && .venv/bin/pytest tests/test_leaderboard_sync.py -v
```

Expected: all three tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/leaderboard_sync.py \
        backend/tests/test_leaderboard_sync.py \
        backend/tests/fixtures/dune_smart_money_sample.json
git commit -m "feat(v2-smart-money): add leaderboard_sync service with snapshot persistence"
```

---

## Task 8: arq worker job + cron wiring

**Files:**
- Create: `backend/app/workers/leaderboard_jobs.py`
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Write the job**

Create `backend/app/workers/leaderboard_jobs.py`:

```python
"""arq task entrypoint for the smart-money leaderboard Dune sync."""
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select

from app.clients.dune import DUNE_BASE_URL, DuneClient, DuneExecutionError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import PriceCandle
from app.core.sync_status import record_sync_ok
from app.services.leaderboard_sync import persist_snapshot

log = logging.getLogger(__name__)

WINDOW_DAYS = 30


def _latest_eth_price(session) -> Decimal | None:
    """Use the most recent 1h close as the window-end mark. None if unavailable."""
    row = session.execute(
        select(PriceCandle)
        .where(PriceCandle.symbol == "ETHUSDT", PriceCandle.timeframe == "1h")
        .order_by(PriceCandle.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return Decimal(str(row.close))


async def sync_smart_money_leaderboard(ctx: dict) -> dict:
    """Execute the Dune leaderboard query and persist a fresh snapshot.

    Skips cleanly when the query ID is not configured (matches existing
    flow-sync conventions). Leaves the previous snapshot in place on any
    error so the API keeps serving stale-but-valid data.
    """
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping leaderboard sync")
        return {"skipped": "no api key"}
    if settings.dune_query_id_smart_money_leaderboard == 0:
        log.info("leaderboard query ID not configured — skipping")
        return {"skipped": "not configured"}

    SessionLocal = get_sessionmaker()

    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=600.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)
        try:
            rows = await client.execute_and_fetch(
                settings.dune_query_id_smart_money_leaderboard,
                max_wait_s=600.0,
            )
        except (DuneExecutionError, httpx.HTTPError) as e:
            log.error("smart-money leaderboard dune query failed: %s", e)
            return {"error": str(e)}

    with SessionLocal() as session:
        eth_price = _latest_eth_price(session)
        run_id = persist_snapshot(
            session,
            rows=rows,
            window_days=WINDOW_DAYS,
            window_end_eth_price=eth_price,
            snapshot_at=datetime.now(UTC),
        )

    if run_id is None:
        return {"skipped": "no rows returned"}

    record_sync_ok("smart_money")
    return {"run_id": str(run_id), "rows": len(rows)}
```

- [ ] **Step 2: Register the job in arq settings**

Modify `backend/app/workers/arq_settings.py`. Add an import:

```python
from app.workers.leaderboard_jobs import sync_smart_money_leaderboard
```

Add a startup enqueue (inside the existing `startup` function, after the other enqueues):

```python
    await ctx["redis"].enqueue_job("sync_smart_money_leaderboard")
```

Add it to `WorkerSettings.functions`:

```python
    functions = [
        backfill_price_history,
        sync_price_latest,
        sync_dune_flows,
        evaluate_alerts,
        sync_derivatives,
        sync_order_flow,
        sync_smart_money_leaderboard,
    ]
```

Add a daily cron. `_cron_from_minutes` does not handle "once per day at a specific hour" cleanly, so use `cron()` directly. Add to `cron_jobs`:

```python
        # Smart-money leaderboard: once a day at 03:00 UTC. The query is
        # meaningfully heavier than order-flow (30d vs 7d window), so a
        # single refresh per day keeps us inside the Dune free-tier budget.
        cron(sync_smart_money_leaderboard, hour={3}, minute={0}, run_at_startup=False),
```

- [ ] **Step 3: Smoke-test the import chain**

```bash
cd backend && .venv/bin/python -c "from app.workers.arq_settings import WorkerSettings; print(len(WorkerSettings.functions), 'jobs')"
```

Expected: prints `7 jobs` with no ImportError.

- [ ] **Step 4: Commit**

```bash
git add backend/app/workers/leaderboard_jobs.py backend/app/workers/arq_settings.py
git commit -m "feat(v2-smart-money): wire daily arq cron for leaderboard sync"
```

---

## Task 9: API endpoint `/api/leaderboard/smart-money`

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/api/leaderboard.py`
- Create: `backend/tests/test_leaderboard_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add response schemas**

Append to `backend/app/api/schemas.py`:

```python
# ---------- Smart-money leaderboard (v2) ----------


class SmartMoneyEntry(BaseModel):
    rank: int
    wallet: str
    label: str | None = None
    realized_pnl_usd: float
    unrealized_pnl_usd: float | None = None
    win_rate: float | None = None
    trade_count: int
    volume_usd: float
    weth_bought: float
    weth_sold: float


class SmartMoneyLeaderboardResponse(BaseModel):
    snapshot_at: datetime | None
    window_days: int
    entries: list[SmartMoneyEntry]
```

Rationale for `float` (not `Decimal`) in the response: the project's existing panels use `float` in response models (see `OrderFlowPoint`, `ExchangeFlowPoint`). Dashboard consumers need JSON numbers, not strings. Internal storage stays `Numeric` for precision.

- [ ] **Step 2: Write failing API test**

Create `backend/tests/test_leaderboard_api.py`:

```python
"""API tests for /api/leaderboard/smart-money."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import SmartMoneyLeaderboard
from app.main import app


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(SmartMoneyLeaderboard).delete()
        s.commit()
        yield s


def _seed(session, *, run_id, snapshot_at, entries):
    for rank, (wallet, pnl) in enumerate(entries, start=1):
        session.add(SmartMoneyLeaderboard(
            run_id=run_id,
            snapshot_at=snapshot_at,
            window_days=30,
            rank=rank,
            wallet_address=wallet,
            label=None,
            realized_pnl_usd=Decimal(str(pnl)),
            unrealized_pnl_usd=None,
            win_rate=Decimal("0.5000"),
            trade_count=2,
            volume_usd=Decimal("100000.00"),
            weth_bought=Decimal("10"),
            weth_sold=Decimal("10"),
        ))
    session.commit()


def test_returns_latest_snapshot_only(session):
    old_run = uuid.uuid4()
    new_run = uuid.uuid4()
    old_ts = datetime(2026, 4, 23, 3, 0, tzinfo=UTC)
    new_ts = datetime(2026, 4, 24, 3, 0, tzinfo=UTC)
    _seed(session, run_id=old_run, snapshot_at=old_ts,
          entries=[("0xold1", 100.00), ("0xold2", 50.00)])
    _seed(session, run_id=new_run, snapshot_at=new_ts,
          entries=[("0xnew1", 500.00)])

    r = TestClient(app).get("/api/leaderboard/smart-money")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_at"].startswith("2026-04-24")
    assert body["window_days"] == 30
    assert len(body["entries"]) == 1
    assert body["entries"][0]["wallet"] == "0xnew1"
    assert body["entries"][0]["rank"] == 1
    assert body["entries"][0]["realized_pnl_usd"] == 500.0


def test_empty_when_no_snapshots(session):
    r = TestClient(app).get("/api/leaderboard/smart-money")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_at"] is None
    assert body["entries"] == []


def test_limit_clamps(session):
    run = uuid.uuid4()
    ts = datetime(2026, 4, 24, 3, 0, tzinfo=UTC)
    _seed(session, run_id=run, snapshot_at=ts,
          entries=[(f"0x{i:040x}", 100.00 - i) for i in range(20)])

    r = TestClient(app).get("/api/leaderboard/smart-money?limit=5")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 5

    # Max is 50
    r = TestClient(app).get("/api/leaderboard/smart-money?limit=9999")
    assert r.status_code == 422  # pydantic validation error
```

- [ ] **Step 3: Run the test — expect FAIL**

```bash
cd backend && .venv/bin/pytest tests/test_leaderboard_api.py -v
```

Expected: FAIL — 404 on the route (not registered yet).

- [ ] **Step 4: Implement the router**

Create `backend/app/api/leaderboard.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    SmartMoneyEntry,
    SmartMoneyLeaderboardResponse,
)
from app.core.db import get_session
from app.core.models import SmartMoneyLeaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/smart-money", response_model=SmartMoneyLeaderboardResponse)
def smart_money_leaderboard(
    session: Annotated[Session, Depends(get_session)],
    window_days: int = Query(30, ge=30, le=30, description="v1 supports only 30d"),
    limit: int = Query(50, ge=1, le=50),
) -> SmartMoneyLeaderboardResponse:
    # Find the run_id of the most recent snapshot for this window.
    latest = session.execute(
        select(SmartMoneyLeaderboard.run_id, SmartMoneyLeaderboard.snapshot_at)
        .where(SmartMoneyLeaderboard.window_days == window_days)
        .order_by(SmartMoneyLeaderboard.snapshot_at.desc(), SmartMoneyLeaderboard.id.desc())
        .limit(1)
    ).first()

    if latest is None:
        return SmartMoneyLeaderboardResponse(
            snapshot_at=None, window_days=window_days, entries=[],
        )

    run_id, snapshot_at = latest
    rows = session.execute(
        select(SmartMoneyLeaderboard)
        .where(SmartMoneyLeaderboard.run_id == run_id)
        .order_by(SmartMoneyLeaderboard.rank)
        .limit(limit)
    ).scalars().all()

    entries = [
        SmartMoneyEntry(
            rank=r.rank,
            wallet=r.wallet_address,
            label=r.label,
            realized_pnl_usd=float(r.realized_pnl_usd),
            unrealized_pnl_usd=float(r.unrealized_pnl_usd) if r.unrealized_pnl_usd is not None else None,
            win_rate=float(r.win_rate) if r.win_rate is not None else None,
            trade_count=r.trade_count,
            volume_usd=float(r.volume_usd),
            weth_bought=float(r.weth_bought),
            weth_sold=float(r.weth_sold),
        )
        for r in rows
    ]
    return SmartMoneyLeaderboardResponse(
        snapshot_at=snapshot_at, window_days=window_days, entries=entries,
    )
```

- [ ] **Step 5: Register the router**

Modify `backend/app/main.py`. Add import near the other routers:

```python
from app.api.leaderboard import router as leaderboard_router
```

Add the `include_router` call after the derivatives router (line 39):

```python
app.include_router(leaderboard_router, prefix="/api", dependencies=[AuthDep])
```

- [ ] **Step 6: Run the tests — expect PASS**

```bash
cd backend && .venv/bin/pytest tests/test_leaderboard_api.py -v
```

Expected: all three tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas.py \
        backend/app/api/leaderboard.py \
        backend/tests/test_leaderboard_api.py \
        backend/app/main.py
git commit -m "feat(v2-smart-money): add /api/leaderboard/smart-money endpoint"
```

---

## Task 10: Health freshness entry for `smart_money`

**Files:**
- Modify: `backend/app/api/health.py`

- [ ] **Step 1: Add the freshness entry**

In `backend/app/api/health.py`, update the `STALE_S` dict:

```python
STALE_S: dict[str, int] = {
    "binance_1m": 120,
    "dune_flows": 6 * 3600,
    "alchemy_blocks": 180,
    "whale_transfers": 6 * 3600,
    "smart_money": 36 * 3600,  # daily refresh, stale after 36h
}
```

Extend the `health()` function. After the existing `dune_last_sync` line, add:

```python
    smart_money_last_sync = last_sync_at("smart_money")
```

And append to the `sources` list:

```python
        _status("smart_money", smart_money_last_sync),
```

- [ ] **Step 2: Add a test**

Append to `backend/tests/test_health.py` (or create if nonexistent — check first with `ls backend/tests/test_health.py`):

```python
def test_health_reports_smart_money_source():
    from fastapi.testclient import TestClient
    from app.main import app

    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()["sources"]}
    assert "smart_money" in names
```

- [ ] **Step 3: Run the test — expect PASS**

```bash
cd backend && .venv/bin/pytest tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/health.py backend/tests/test_health.py
git commit -m "feat(v2-smart-money): add smart_money freshness entry to /api/health"
```

---

## Task 11: Frontend — API client

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetcher**

Append to `frontend/src/api.ts`:

```typescript
export type SmartMoneyEntry = {
  rank: number;
  wallet: string;
  label: string | null;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number | null;
  win_rate: number | null;
  trade_count: number;
  volume_usd: number;
  weth_bought: number;
  weth_sold: number;
};

export type SmartMoneyLeaderboard = {
  snapshot_at: string | null;
  window_days: number;
  entries: SmartMoneyEntry[];
};

export async function fetchSmartMoneyLeaderboard(
  limit = 50,
): Promise<SmartMoneyLeaderboard> {
  const r = await fetch(url(`/api/leaderboard/smart-money?limit=${limit}`), {
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`smart-money leaderboard ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(v2-smart-money): add frontend API client for leaderboard"
```

---

## Task 12: Frontend — `SmartMoneyLeaderboard` panel

**Files:**
- Create: `frontend/src/components/SmartMoneyLeaderboard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Implement the panel**

Create `frontend/src/components/SmartMoneyLeaderboard.tsx`:

```typescript
import { useQuery } from "@tanstack/react-query";

import { fetchSmartMoneyLeaderboard, type SmartMoneyEntry } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";

const STALE_HOURS = 36;

function truncWallet(w: string): string {
  if (w.length <= 12) return w;
  return `${w.slice(0, 6)}…${w.slice(-4)}`;
}

function etherscanUrl(w: string): string {
  return `https://etherscan.io/address/${w}`;
}

function fmtPnl(v: number): string {
  const sign = v >= 0 ? "+" : "-";
  return `${sign}${formatUsdCompact(Math.abs(v))}`;
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function isStale(snapshotIso: string | null): boolean {
  if (snapshotIso === null) return false;
  const ageMs = Date.now() - new Date(snapshotIso).getTime();
  return ageMs > STALE_HOURS * 3600 * 1000;
}

export default function SmartMoneyLeaderboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["smart-money-leaderboard"],
    queryFn: () => fetchSmartMoneyLeaderboard(),
    refetchInterval: 5 * 60_000,
  });

  const stale = isStale(data?.snapshot_at ?? null);

  return (
    <Card
      title="Smart money leaderboard"
      subtitle="Top 50 ETH DEX traders by 30d realized PnL · WETH only · mainnet"
      bodyClassName="p-0"
    >
      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!isLoading && !error && (!data || data.entries.length === 0) && (
        <p className="p-5 text-sm text-slate-500">
          no snapshot yet — refresh runs daily at 03:00 UTC. Needs{" "}
          <code className="text-slate-300">DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD</code> set.
        </p>
      )}
      {stale && (
        <p className="px-5 py-2 text-xs text-amber-300/80 border-b border-surface-divider">
          Snapshot is older than {STALE_HOURS}h — daily refresh may have stalled.
        </p>
      )}

      {data && data.entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500 border-b border-surface-divider">
              <tr>
                <th className="text-left px-4 py-3 font-medium">#</th>
                <th className="text-left px-4 py-3 font-medium">Wallet</th>
                <th className="text-right px-4 py-3 font-medium">Realized PnL</th>
                <th className="text-right px-4 py-3 font-medium">Unrealized</th>
                <th className="text-right px-4 py-3 font-medium">Win rate</th>
                <th className="text-right px-4 py-3 font-medium">Trades</th>
                <th className="text-right px-4 py-3 font-medium">Volume</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e: SmartMoneyEntry) => (
                <tr
                  key={e.wallet}
                  className="border-b border-surface-divider/50 hover:bg-surface-hover/40"
                >
                  <td className="px-4 py-3 font-mono text-slate-400 tabular-nums">
                    {e.rank}
                  </td>
                  <td className="px-4 py-3">
                    <a
                      href={etherscanUrl(e.wallet)}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-slate-200 hover:text-white"
                    >
                      {truncWallet(e.wallet)}
                    </a>
                    {e.label && (
                      <span className="ml-2 inline-block rounded-sm bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                        {e.label}
                      </span>
                    )}
                  </td>
                  <td
                    className={
                      "px-4 py-3 text-right font-mono tabular-nums " +
                      (e.realized_pnl_usd >= 0 ? "text-up" : "text-down")
                    }
                  >
                    {fmtPnl(e.realized_pnl_usd)}
                  </td>
                  <td
                    className={
                      "px-4 py-3 text-right font-mono tabular-nums " +
                      (e.unrealized_pnl_usd === null
                        ? "text-slate-600"
                        : e.unrealized_pnl_usd >= 0
                          ? "text-up/80"
                          : "text-down/80")
                    }
                  >
                    {e.unrealized_pnl_usd === null
                      ? "—"
                      : fmtPnl(e.unrealized_pnl_usd)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {fmtPct(e.win_rate)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400 tabular-nums">
                    {e.trade_count}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300 tabular-nums">
                    {formatUsdCompact(e.volume_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Mount the panel in App.tsx**

Modify `frontend/src/App.tsx`. Add the import with the other panel imports:

```typescript
import SmartMoneyLeaderboard from "./components/SmartMoneyLeaderboard";
```

Add a `<Guarded>` entry in the main panel list. Place it after `DerivativesPanel` and before `OrderFlowPanel` (so v2 features cluster together):

```tsx
        <Guarded label="Smart money" id="smart-money">
          <SmartMoneyLeaderboard />
        </Guarded>
```

- [ ] **Step 3: Verify TypeScript + build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: no type errors; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SmartMoneyLeaderboard.tsx frontend/src/App.tsx
git commit -m "feat(v2-smart-money): add SmartMoneyLeaderboard dashboard panel"
```

---

## Task 13: Env documentation + milestone note

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.env.example` (only if it exists)

- [ ] **Step 1: Check for .env.example**

```bash
ls .env.example 2>/dev/null || echo "not present"
```

If present, append:

```bash
# Dune query ID for the smart-money leaderboard (v2). When unset, the
# sync job is a no-op and the panel shows "no data yet".
DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD=0
```

- [ ] **Step 2: Update CLAUDE.md milestone status**

In `CLAUDE.md`, find the `## v2 status` section. Update the entries:

```markdown
## v2 status

- v2-derivatives ✅ OI + funding rates for ETH perp across Binance/Bybit/OKX/Deribit.
- v2-order-flow ✅ Dune `dex.trades` aggregates WETH buy vs sell pressure across major DEXes, persists hourly to `order_flow`; `/api/flows/order-flow` endpoint; dashboard panel with buy/sell/net tiles + signed-stacked bar + net line. Runs on 8h cadence to stay within Dune free-tier credit budget. Requires `DUNE_QUERY_ID_ORDER_FLOW` in `.env` (SQL at `backend/dune/order_flow.sql`).
- v2-smart-money-leaderboard ✅ Daily Dune refresh of top 50 ETH DEX traders by 30d realized PnL on WETH; FIFO engine runs in Python over `dex.trades` candidate rows; persists snapshot per run to `smart_money_leaderboard`; `/api/leaderboard/smart-money` endpoint; dashboard panel. Requires `DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD` in `.env` (SQL at `backend/dune/smart_money_leaderboard.sql`).
- v2 pending — wallet clustering, mempool (needs node), large-vs-small tx volume structure
```

(The `v2-order-flow` entry keeps its current wording; only update it if it still says `🚧`.)

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .env.example 2>/dev/null
git commit -m "docs(v2-smart-money): document env var and mark milestone"
```

Note: `.env.example` is only staged if it exists — the second `git add` silently no-ops if the file is missing.

---

## Task 14: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && .venv/bin/pytest -v
```

Expected: all tests PASS. If anything regresses (auth, flows, whales, alerts), fix the regression before moving on.

- [ ] **Step 2: Start the stack**

```bash
make up
```

Wait for healthchecks. Expected: postgres, redis, api, worker, realtime, frontend all up.

- [ ] **Step 3: Verify the API endpoint with no data**

```bash
curl -s http://localhost:8000/api/leaderboard/smart-money | jq .
```

Expected:
```json
{
  "snapshot_at": null,
  "window_days": 30,
  "entries": []
}
```

- [ ] **Step 4: Verify /api/health lists the new source**

```bash
curl -s http://localhost:8000/api/health | jq '.sources[] | select(.name == "smart_money")'
```

Expected: `{"name": "smart_money", "last_update": null, "lag_seconds": null, "stale": true}` (stale because no sync has run yet — correct).

- [ ] **Step 5: Verify the frontend panel renders the empty state**

Open `http://localhost:5173` in a browser. Scroll to the "Smart money leaderboard" panel. Expected: panel visible, shows "no snapshot yet — refresh runs daily at 03:00 UTC…" message, no JS errors in the dev tools console.

- [ ] **Step 6: (Manual — requires Dune account) Register the query**

1. In the Dune web UI, create a new query named "Etherscope — Smart Money Leaderboard (v2)".
2. Paste the contents of `backend/dune/smart_money_leaderboard.sql` and run it. Verify it returns rows in a reasonable time (< 3 min). Check the top wallet manually — it should not be a known router.
3. Copy the query ID from the Dune URL.
4. Set `DUNE_QUERY_ID_SMART_MONEY_LEADERBOARD=<id>` in `.env`.
5. Restart the worker: `make down && make up`.
6. Trigger a manual run (mirrors the pattern in `flow_jobs.py`):

```bash
docker compose exec worker python -c "\
import asyncio; \
from app.workers.leaderboard_jobs import sync_smart_money_leaderboard; \
print(asyncio.run(sync_smart_money_leaderboard({})))"
```

Expected: prints `{"run_id": "<uuid>", "rows": <N>}`.

7. Re-curl the API and the dashboard — expect 50 entries sorted by realized PnL.

- [ ] **Step 7: Spot-check the output**

Pick the top wallet's address. Open Etherscan. Verify:
- It is an EOA (not a contract).
- It has meaningful 30d DEX activity.
- It is not one of the router addresses from the exclusion list.

If the #1 slot is clearly a router or MEV bot not in the exclusion list, add that address to the exclusion list, re-save the query on Dune, and re-run.

- [ ] **Step 8: Final commit (if any tweaks from step 7)**

```bash
git add -u
git commit -m "chore(v2-smart-money): extend router exclusion list after manual review"
```

Skip this step if no tweaks were needed.

---

## Self-Review Completed

Spec coverage:
- Goals & non-goals → Tasks 1–14 collectively.
- Scope decisions table (window 30d, top 50, top-500 candidates, FIFO, skip pre-window, WETH↔any, router exclusions, daily cadence, snapshots) → Tasks 4, 5, 7, 8.
- Architecture diagram → Tasks 1 (schema), 4 (query), 5–6 (engine), 7 (sync), 8 (cron), 9 (API), 11–12 (frontend).
- Database schema → Tasks 1, 2.
- Dune query (including `router_exclusions` CTE, `tx_from`, partition pruning) → Task 4.
- FIFO engine (algorithm, precision, metric definitions, unrealized mark) → Tasks 5, 6.
- API endpoint spec (response shape, empty-state, caching-deferred-as-future) → Task 9. (Redis caching is explicitly deferred; spec says "Redis-cached for 5 minutes"; the initial implementation skips the Redis cache since the endpoint reads only 50 rows and is fast — document this as a deferred optimization if added later.)
- Frontend spec (columns, Etherscan link, label badge, stale banner, empty state, ErrorBoundary via `<Guarded>`) → Task 12.
- Error handling (Dune timeout, empty rows, unknown side, sell-only, missing ETH price, no-snapshot endpoint, transactional boundary) → Tasks 6, 7, 8, 9.
- Testing (pnl_engine unit + sync integration + API) → Tasks 5, 6, 7, 9.
- Observability (per-refresh log, /api/health entry) → Tasks 7, 10.
- Configuration (new env var, no new secrets) → Tasks 3, 13.
- Rollout (unset-ID no-op, manual verification, CLAUDE.md milestone) → Tasks 8, 13, 14.

Note on Redis caching: the spec mentions a 5-minute Redis cache on the read endpoint. The initial implementation in Task 9 reads directly from Postgres (50 rows, indexed). Adding a Redis layer is straightforward to retrofit but adds test surface. Deferred to future work; the endpoint latency is expected to be < 10 ms without it.

Placeholder scan: clean. All code steps contain complete code. All commands have expected output.

Type consistency: `WalletPnL` fields match across `pnl_engine.py` (Task 5), `leaderboard_sync.py` (Task 7), and the ORM model (Task 2). Wallet addresses are `str` (lowercase hex 0x…) throughout Python and `VARCHAR(42)` in SQL. API response uses `float` for numeric fields matching existing panel conventions (documented in Task 9 rationale).
