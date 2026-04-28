# Mempool Whale Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface whale-sized Ethereum transactions while still in the mempool (before mining), via Geth's `newPendingTransactions` subscription, displayed in the Whale Transfers panel as a top "Pending" section.

**Architecture:** Spec at `docs/superpowers/specs/2026-04-28-mempool-tracking-design.md`. Mempool listener runs as a concurrent asyncio task inside the existing `realtime` container. Whale-sized pending txs persist to a new `pending_transfers` table; an arq cron job cleans up rows that are >30 min old or now confirmed.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x / Pydantic v2 / arq / asyncio websockets / Postgres 16 / React 18 + TanStack Query / Tailwind.

---

## File Structure

**New files:**
- `backend/alembic/versions/0005_pending_transfers.py` — schema migration
- `backend/app/realtime/erc20_decode.py` — decode `transfer(address,uint256)` calldata
- `backend/app/realtime/mempool.py` — pending-tx subscriber + filter + persist
- `backend/app/workers/pending_cleanup.py` — arq cron task to drop stale/confirmed pending rows
- `backend/tests/test_erc20_decode.py`
- `backend/tests/test_mempool_parser.py`
- `backend/tests/test_pending_cleanup.py`
- `backend/tests/test_pending_api.py`

**Modified files:**
- `backend/app/core/models.py` — add `PendingTransfer` ORM model
- `backend/app/realtime/listener.py` — `main()` spawns mempool task alongside the existing `newHeads` task
- `backend/app/realtime/parser.py` — add `decode_pending_tx()` returning a `PendingWhale` dataclass
- `backend/app/api/whales.py` — add `GET /api/whales/pending` endpoint
- `backend/app/api/schemas.py` — add `PendingTransferOut` and `PendingTransfersResponse`
- `backend/app/workers/arq_settings.py` — register `cleanup_pending_transfers` cron (every minute)
- `frontend/src/api.ts` — `getPendingWhales()` client function
- `frontend/src/components/WhaleTransfersPanel.tsx` — add Pending section at the top

---

## Task 1: Migration — `pending_transfers` table

**Files:**
- Create: `backend/alembic/versions/0005_pending_transfers.py`

- [ ] **Step 1: Write the migration**

```python
"""pending mempool transfers

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_transfers",
        sa.Column("tx_hash", sa.String(66), primary_key=True),
        sa.Column("from_addr", sa.String(42), nullable=False),
        sa.Column("to_addr", sa.String(42), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=True),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("nonce", sa.BigInteger, nullable=True),
        sa.Column("gas_price_gwei", sa.Numeric(20, 9), nullable=True),
    )
    op.create_index("ix_pending_seen_at_desc", "pending_transfers", [sa.text("seen_at DESC")])
    op.create_index("ix_pending_sender_nonce", "pending_transfers", ["from_addr", "nonce"])


def downgrade() -> None:
    op.drop_index("ix_pending_sender_nonce", table_name="pending_transfers")
    op.drop_index("ix_pending_seen_at_desc", table_name="pending_transfers")
    op.drop_table("pending_transfers")
```

> Note: this assumes the most recent migration on `main` is `0004_smart_money_leaderboard`. If a newer migration has landed, bump both `revision` and `down_revision` accordingly.

- [ ] **Step 2: Verify migration applies cleanly**

Run from `backend/`:

```bash
alembic upgrade head
```

Expected: no errors. Re-run produces "Already up to date" with no error.

- [ ] **Step 3: Verify downgrade also works**

```bash
alembic downgrade -1
alembic upgrade head
```

Expected: clean down + up cycle.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0006_pending_transfers.py
git commit -m "feat(mempool): add pending_transfers table migration"
```

---

## Task 2: ORM model — `PendingTransfer`

**Files:**
- Modify: `backend/app/core/models.py` (after the existing `Transfer` class, around line 84)

- [ ] **Step 1: Add the model**

Append after the `Transfer` class:

```python
class PendingTransfer(Base):
    __tablename__ = "pending_transfers"
    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    from_addr: Mapped[str] = mapped_column(String(42), index=True)
    to_addr: Mapped[str] = mapped_column(String(42))
    asset: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Numeric(38, 18))
    usd_value: Mapped[float | None] = mapped_column(Numeric(32, 2), nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nonce: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gas_price_gwei: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && python -c "from app.core.models import PendingTransfer; print(PendingTransfer.__tablename__)"
```

Expected output: `pending_transfers`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/models.py
git commit -m "feat(mempool): add PendingTransfer ORM model"
```

---

## Task 3: ERC-20 calldata decoder

**Files:**
- Create: `backend/app/realtime/erc20_decode.py`
- Test: `backend/tests/test_erc20_decode.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_erc20_decode.py`:

```python
from app.realtime.erc20_decode import decode_erc20_transfer


def test_decode_valid_transfer_calldata():
    # transfer(0xaaaa...aaaa, 1_000_000)
    addr_part = "000000000000000000000000" + "aa" * 20
    amount_part = format(1_000_000, "064x")
    data = "0xa9059cbb" + addr_part + amount_part
    result = decode_erc20_transfer(data)
    assert result is not None
    to_addr, amount = result
    assert to_addr == "0x" + "aa" * 20
    assert amount == 1_000_000


def test_decode_uppercase_hex_prefix():
    addr_part = "000000000000000000000000" + "bb" * 20
    amount_part = format(42, "064x")
    data = "0xA9059CBB" + addr_part + amount_part
    result = decode_erc20_transfer(data)
    assert result is not None
    assert result[0] == "0x" + "bb" * 20
    assert result[1] == 42


def test_decode_unknown_selector_returns_none():
    # approve(...) — different selector
    data = "0x095ea7b3" + "00" * 64
    assert decode_erc20_transfer(data) is None


def test_decode_too_short_returns_none():
    assert decode_erc20_transfer("0xa9059cbb") is None
    assert decode_erc20_transfer("0x") is None
    assert decode_erc20_transfer("") is None


def test_decode_none_returns_none():
    assert decode_erc20_transfer(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_erc20_decode.py -v`

Expected: ImportError, module `app.realtime.erc20_decode` does not exist.

- [ ] **Step 3: Implement the decoder**

Create `backend/app/realtime/erc20_decode.py`:

```python
"""Decode ERC-20 transfer(address,uint256) calldata.

Used by the mempool listener: pending txs have no event logs yet, so we
decode the input data of `transfer(...)` calls directly to identify
ERC-20 token movements before they're mined.
"""

# keccak256("transfer(address,uint256)")[:8] = "a9059cbb"
TRANSFER_SELECTOR = "a9059cbb"


def decode_erc20_transfer(data: str | None) -> tuple[str, int] | None:
    """Return (to_addr, amount) for a `transfer(...)` call, else None.

    Accepts hex with or without `0x` prefix, any case. Returns None if the
    selector doesn't match transfer(), or if the data is too short.
    """
    if not data:
        return None
    s = data.lower()
    if s.startswith("0x"):
        s = s[2:]
    # selector (8 hex) + to (64) + amount (64) = 136 hex chars
    if len(s) < 136:
        return None
    if s[:8] != TRANSFER_SELECTOR:
        return None
    # The `to` address is right-padded into the 32-byte slot — last 40 hex chars are the address
    to_addr = "0x" + s[8 + 24 : 8 + 64]
    amount = int(s[8 + 64 : 8 + 128], 16)
    return to_addr, amount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_erc20_decode.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/erc20_decode.py backend/tests/test_erc20_decode.py
git commit -m "feat(mempool): erc20 transfer calldata decoder + tests"
```

---

## Task 4: Pending-tx whale filter (pure function)

**Files:**
- Modify: `backend/app/realtime/parser.py`
- Test: `backend/tests/test_mempool_parser.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_mempool_parser.py`:

```python
from app.realtime.parser import PendingWhale, decode_pending_tx


def _native_tx(value_eth: float, to: str = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") -> dict:
    return {
        "hash": "0xtx",
        "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "to": to,
        "value": hex(int(value_eth * 10**18)),
        "input": "0x",
        "nonce": "0x5",
        "gasPrice": hex(20 * 10**9),
    }


def _erc20_transfer_tx(token_addr: str, amount_raw: int) -> dict:
    addr_part = "000000000000000000000000" + "bb" * 20
    amount_part = format(amount_raw, "064x")
    return {
        "hash": "0xtx",
        "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "to": token_addr,
        "value": "0x0",
        "input": "0xa9059cbb" + addr_part + amount_part,
        "nonce": "0x6",
        "gasPrice": hex(25 * 10**9),
    }


def test_native_eth_above_threshold_returns_pending_whale():
    tx = _native_tx(150)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "ETH"
    assert result.amount == 150.0
    assert result.usd_value == 450_000.0
    assert result.from_addr == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result.nonce == 5
    assert result.gas_price_gwei == 20.0


def test_native_eth_below_threshold_returns_none():
    tx = _native_tx(50)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_native_eth_contract_creation_returns_none():
    tx = _native_tx(150)
    tx["to"] = None
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_usdt_above_threshold_returns_pending_whale():
    # USDT contract address (lowercase), 6 decimals, 500_000 USDT
    tx = _erc20_transfer_tx("0xdac17f958d2ee523a2206206994597c13d831ec7", 500_000 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "USDT"
    assert result.amount == 500_000.0
    assert result.usd_value == 500_000.0


def test_erc20_usdc_below_threshold_returns_none():
    tx = _erc20_transfer_tx("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 100_000 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_volatile_wbtc_above_native_threshold_returns_pending_whale():
    # WBTC, 8 decimals, threshold 3.5 WBTC; send 5 WBTC.
    tx = _erc20_transfer_tx("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 5 * 10**8)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert isinstance(result, PendingWhale)
    assert result.asset == "WBTC"
    assert result.amount == 5.0
    assert result.usd_value == 350_000.0  # 5 × 70000 (price_usd_approx)


def test_erc20_volatile_wbtc_below_native_threshold_returns_none():
    # 2 WBTC < 3.5 WBTC native threshold
    tx = _erc20_transfer_tx("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 2 * 10**8)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None


def test_erc20_to_unknown_token_returns_none():
    # Transfer call to a contract we don't track
    tx = _erc20_transfer_tx("0x0000000000000000000000000000000000000001", 999 * 10**6)
    result = decode_pending_tx(tx, eth_usd=3000.0, threshold_eth=100.0, threshold_usd=250_000.0)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mempool_parser.py -v`

Expected: ImportError on `PendingWhale` / `decode_pending_tx`.

- [ ] **Step 3: Implement `PendingWhale` and `decode_pending_tx`**

Append to `backend/app/realtime/parser.py`:

```python
from app.realtime.erc20_decode import decode_erc20_transfer


@dataclass(frozen=True)
class PendingWhale:
    tx_hash: str
    from_addr: str
    to_addr: str
    asset: str
    amount: float
    usd_value: float | None
    nonce: int | None
    gas_price_gwei: float | None


def decode_pending_tx(
    tx: dict,
    *,
    eth_usd: float | None,
    threshold_eth: float,
    threshold_usd: float,
) -> PendingWhale | None:
    """Identify whale-sized native-ETH or ERC-20-transfer pending txs.

    Pending txs lack event logs, so for ERC-20 we decode the input-data
    `transfer(address,uint256)` selector directly. The thresholds match
    the confirmed-tx parser.
    """
    to_addr = tx.get("to")
    from_addr = tx.get("from")
    if not from_addr:
        return None

    nonce = _parse_hex(tx.get("nonce"))
    gas_price_wei = _parse_hex(tx.get("gasPrice"))
    gas_price_gwei = gas_price_wei / GWEI if gas_price_wei else None

    # Native ETH transfer
    if to_addr:
        value_wei = _parse_hex(tx.get("value"))
        if value_wei > 0:
            amount = value_wei / WEI
            if amount >= threshold_eth:
                usd = amount * eth_usd if eth_usd else None
                return PendingWhale(
                    tx_hash=tx["hash"],
                    from_addr=from_addr.lower(),
                    to_addr=to_addr.lower(),
                    asset="ETH",
                    amount=amount,
                    usd_value=usd,
                    nonce=nonce,
                    gas_price_gwei=gas_price_gwei,
                )

    # ERC-20 transfer call to a tracked token
    if to_addr:
        token_addr = to_addr.lower()
        decoded = decode_erc20_transfer(tx.get("input"))
        if decoded is None:
            return None
        decoded_to, raw_amount = decoded

        stable = STABLES_BY_ADDRESS.get(token_addr)
        if stable is not None:
            amount = raw_amount / (10**stable.decimals)
            if amount < threshold_usd:
                return None
            return PendingWhale(
                tx_hash=tx["hash"],
                from_addr=from_addr.lower(),
                to_addr=decoded_to.lower(),
                asset=stable.symbol,
                amount=amount,
                usd_value=amount,
                nonce=nonce,
                gas_price_gwei=gas_price_gwei,
            )

        volatile = VOLATILE_BY_ADDRESS.get(token_addr)
        if volatile is not None:
            amount = raw_amount / (10**volatile.decimals)
            if amount < volatile.threshold_native:
                return None
            return PendingWhale(
                tx_hash=tx["hash"],
                from_addr=from_addr.lower(),
                to_addr=decoded_to.lower(),
                asset=volatile.symbol,
                amount=amount,
                usd_value=amount * volatile.price_usd_approx,
                nonce=nonce,
                gas_price_gwei=gas_price_gwei,
            )

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mempool_parser.py -v`

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/parser.py backend/tests/test_mempool_parser.py
git commit -m "feat(mempool): pending-tx whale filter (native + ERC-20 decode)"
```

---

## Task 5: Mempool listener integration

**Files:**
- Create: `backend/app/realtime/mempool.py`
- Modify: `backend/app/realtime/listener.py`

This task wires the new subscription into the existing listener process. The mempool listener runs as a concurrent asyncio task next to the existing `newHeads` task, sharing the same WebSocket and reconnect lifecycle.

- [ ] **Step 1: Create the mempool module**

Create `backend/app/realtime/mempool.py`:

```python
"""Mempool listener — detect whale-sized pending transactions.

Subscribes to `newPendingTransactions` on the local Geth WebSocket and,
for each pending hash, fetches the tx via `eth_getTransactionByHash`,
runs the pending whale filter, and persists matches to `pending_transfers`.
"""
import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.models import PendingTransfer
from app.realtime.parser import PendingWhale, decode_pending_tx

log = logging.getLogger("realtime.mempool")

# Cap concurrent eth_getTransactionByHash lookups so a flood of mempool hashes
# can't overwhelm the WebSocket pipeline. 32 is roughly the steady-state mempool
# arrival rate during a typical mainnet block window.
LOOKUP_CONCURRENCY = 32


def _persist_pending(session: Session, w: PendingWhale) -> None:
    """Insert a pending whale, replacing any prior tx with same (from, nonce)."""
    if w.nonce is not None:
        session.query(PendingTransfer).filter(
            PendingTransfer.from_addr == w.from_addr,
            PendingTransfer.nonce == w.nonce,
            PendingTransfer.tx_hash != w.tx_hash,
        ).delete(synchronize_session=False)

    stmt = insert(PendingTransfer).values(
        tx_hash=w.tx_hash,
        from_addr=w.from_addr,
        to_addr=w.to_addr,
        asset=w.asset,
        amount=w.amount,
        usd_value=w.usd_value,
        nonce=w.nonce,
        gas_price_gwei=w.gas_price_gwei,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["tx_hash"])
    session.execute(stmt)
    session.commit()


async def _process_hash(
    client,
    sessionmaker,
    tx_hash: str,
    eth_usd_provider,
    thresholds: tuple[float, float],
    sem: asyncio.Semaphore,
) -> None:
    threshold_eth, threshold_usd = thresholds
    async with sem:
        try:
            res = await client.call("eth_getTransactionByHash", [tx_hash])
        except Exception:
            log.debug("getTransactionByHash failed for %s", tx_hash, exc_info=True)
            return
    tx = res.get("result") if isinstance(res, dict) else None
    if not tx:
        return  # tx already mined or dropped between subscription and lookup

    eth_usd = eth_usd_provider()
    whale = decode_pending_tx(
        tx,
        eth_usd=eth_usd,
        threshold_eth=threshold_eth,
        threshold_usd=threshold_usd,
    )
    if whale is None:
        return

    try:
        with sessionmaker() as session:
            _persist_pending(session, whale)
        log.info(
            "pending whale asset=%s amount=%s usd=%s tx=%s",
            whale.asset, whale.amount, whale.usd_value, whale.tx_hash,
        )
    except Exception:
        log.exception("failed to persist pending whale %s", whale.tx_hash)


async def run_mempool_loop(
    client,
    sessionmaker,
    eth_usd_provider,
    thresholds: tuple[float, float],
) -> None:
    """Subscribe + dispatch loop. Returns when the WS connection drops."""
    queue = await client.subscribe(["newPendingTransactions"])
    log.info("subscribed to newPendingTransactions")
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    while True:
        tx_hash = await queue.get()
        # Each hash is processed independently; we don't await it so the loop
        # keeps draining the queue.
        asyncio.create_task(
            _process_hash(client, sessionmaker, tx_hash, eth_usd_provider, thresholds, sem)
        )
```

- [ ] **Step 2: Wire it into the existing listener `run_once`**

In `backend/app/realtime/listener.py`, find the `run_once` function. Modify it to spawn the mempool loop alongside the existing block-processing loop.

Read the current `run_once` function:

```bash
sed -n '/^async def run_once/,/^async def main/p' backend/app/realtime/listener.py
```

Replace the body of `run_once` so it runs both subscriptions concurrently. The new shape:

```python
async def run_once(ws_url: str, sessionmaker, thresholds: tuple[float, float]) -> None:
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
        client = AlchemyClient(ws)
        pump_task = asyncio.create_task(client.pump())

        def eth_usd_provider() -> float | None:
            with sessionmaker() as session:
                return _latest_eth_usd(session)

        try:
            heads = await client.subscribe(["newHeads"])
            log.info("subscribed to newHeads")
            mempool_task = asyncio.create_task(
                run_mempool_loop(client, sessionmaker, eth_usd_provider, thresholds)
            )
            try:
                while True:
                    head = await next_head(heads, HEAD_STALL_TIMEOUT_S)
                    if head is None:
                        log.warning(
                            "no new head in %.0fs — reconnecting", HEAD_STALL_TIMEOUT_S
                        )
                        return  # outer main() loop recreates the WS
                    bn = int(head["number"], 16)
                    try:
                        await _process_block(client, bn, sessionmaker, thresholds)
                    except Exception:
                        log.exception("block %d processing failed", bn)
            finally:
                mempool_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await mempool_task
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
```

Add the import at the top of `listener.py`:

```python
from app.realtime.mempool import run_mempool_loop
```

- [ ] **Step 3: Smoke test the import + module loads cleanly**

```bash
cd backend && python -c "from app.realtime.listener import run_once; from app.realtime.mempool import run_mempool_loop; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Run the existing realtime tests to confirm no regression**

```bash
cd backend && pytest tests/test_realtime_parser.py tests/test_listener_persist.py -v
```

Expected: all existing tests pass (no behavior change to existing code paths).

> Note: if `tests/test_listener_persist.py` does not exist in your branch, omit it. The point is to confirm the existing realtime tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/mempool.py backend/app/realtime/listener.py
git commit -m "feat(mempool): subscribe to newPendingTransactions concurrently with newHeads"
```

---

## Task 6: Cleanup arq job

**Files:**
- Create: `backend/app/workers/pending_cleanup.py`
- Modify: `backend/app/workers/arq_settings.py`
- Test: `backend/tests/test_pending_cleanup.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_pending_cleanup.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import PendingTransfer, Transfer
from app.workers.pending_cleanup import _cleanup_pending


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PendingTransfer).delete()
        s.query(Transfer).delete()
        s.commit()
        yield s


def _make_pending(session, tx_hash: str, age_minutes: int) -> PendingTransfer:
    row = PendingTransfer(
        tx_hash=tx_hash,
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
        seen_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
        nonce=1,
        gas_price_gwei=Decimal("20"),
    )
    session.add(row)
    session.commit()
    return row


def test_cleanup_removes_stale_pending(session):
    _make_pending(session, "0xstale", age_minutes=31)
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 0


def test_cleanup_keeps_recent_pending(session):
    _make_pending(session, "0xfresh", age_minutes=5)
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 1


def test_cleanup_removes_now_confirmed_pending(session):
    _make_pending(session, "0xconfirmed", age_minutes=2)
    confirmed = Transfer(
        tx_hash="0xconfirmed",
        log_index=0,
        block_number=24_000_000,
        ts=datetime.now(UTC),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
    )
    session.add(confirmed)
    session.commit()
    _cleanup_pending(session)
    assert session.query(PendingTransfer).count() == 0


def test_cleanup_keeps_distinct_pending_when_others_confirmed(session):
    _make_pending(session, "0xstillpending", age_minutes=5)
    _make_pending(session, "0xconfirmed", age_minutes=5)
    confirmed = Transfer(
        tx_hash="0xconfirmed",
        log_index=0,
        block_number=24_000_000,
        ts=datetime.now(UTC),
        from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        asset="ETH",
        amount=Decimal("100"),
        usd_value=Decimal("300000"),
    )
    session.add(confirmed)
    session.commit()
    _cleanup_pending(session)
    remaining = [r.tx_hash for r in session.query(PendingTransfer).all()]
    assert remaining == ["0xstillpending"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_pending_cleanup.py -v`

Expected: ImportError on `app.workers.pending_cleanup`.

- [ ] **Step 3: Implement the cleanup**

Create `backend/app/workers/pending_cleanup.py`:

```python
"""Periodic job: drop expired or now-confirmed pending whale rows."""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker

log = logging.getLogger("workers.pending_cleanup")

EXPIRY_MINUTES = 30


def _cleanup_pending(session: Session) -> int:
    res = session.execute(
        text(
            """
            DELETE FROM pending_transfers
            WHERE seen_at < NOW() - make_interval(mins => :minutes)
               OR tx_hash IN (
                   SELECT tx_hash FROM transfers WHERE ts > NOW() - INTERVAL '1 hour'
               )
            """
        ),
        {"minutes": EXPIRY_MINUTES},
    )
    session.commit()
    return res.rowcount or 0


async def cleanup_pending_transfers(ctx: dict) -> dict:
    sessionmaker = ctx.get("sessionmaker") or get_sessionmaker()
    with sessionmaker() as session:
        deleted = _cleanup_pending(session)
    log.info("pending_cleanup deleted=%d", deleted)
    return {"deleted": deleted}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_pending_cleanup.py -v`

Expected: 4 passed.

- [ ] **Step 5: Register the cron in arq_settings**

Edit `backend/app/workers/arq_settings.py`. Add the import:

```python
from app.workers.pending_cleanup import cleanup_pending_transfers
```

In `WorkerSettings.functions`, add `cleanup_pending_transfers` to the list.

In `WorkerSettings.cron_jobs`, add a new entry:

```python
cron(cleanup_pending_transfers, minute=set(range(0, 60)), run_at_startup=False),
```

- [ ] **Step 6: Smoke-test that arq settings still load**

```bash
cd backend && python -c "from app.workers.arq_settings import WorkerSettings; print(len(WorkerSettings.functions), 'functions')"
```

Expected: prints `8 functions` (was 7, now +1).

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/pending_cleanup.py backend/app/workers/arq_settings.py backend/tests/test_pending_cleanup.py
git commit -m "feat(mempool): pending_transfers cleanup cron (every 60s)"
```

---

## Task 7: API endpoint — `GET /api/whales/pending`

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/whales.py`
- Test: `backend/tests/test_pending_api.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_pending_api.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.core.db import get_session
from app.core.models import PendingTransfer


def test_pending_endpoint_returns_rows_sorted_desc(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)

    def override_get_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    with Session() as s:
        s.query(PendingTransfer).delete()
        now = datetime.now(UTC)
        s.add_all([
            PendingTransfer(
                tx_hash="0xolder",
                from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                to_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                asset="ETH",
                amount=Decimal("150"),
                usd_value=Decimal("450000"),
                seen_at=now - timedelta(seconds=30),
                nonce=1,
                gas_price_gwei=Decimal("20"),
            ),
            PendingTransfer(
                tx_hash="0xnewer",
                from_addr="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                to_addr="0xcccccccccccccccccccccccccccccccccccccccc",
                asset="USDT",
                amount=Decimal("500000"),
                usd_value=Decimal("500000"),
                seen_at=now - timedelta(seconds=5),
                nonce=2,
                gas_price_gwei=Decimal("25"),
            ),
        ])
        s.commit()

    try:
        client = TestClient(app)
        resp = client.get("/api/whales/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        hashes = [r["tx_hash"] for r in data["pending"]]
        assert hashes == ["0xnewer", "0xolder"]
        # USD value present and correct
        assert float(data["pending"][0]["usd_value"]) == 500000.0
    finally:
        app.dependency_overrides.clear()


def test_pending_endpoint_empty_returns_empty_list(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)

    def override_get_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    with Session() as s:
        s.query(PendingTransfer).delete()
        s.commit()

    try:
        client = TestClient(app)
        resp = client.get("/api/whales/pending")
        assert resp.status_code == 200
        assert resp.json() == {"pending": []}
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_pending_api.py -v`

Expected: 404 on the route, or schema-import errors.

- [ ] **Step 3: Add Pydantic schemas**

Append to `backend/app/api/schemas.py`:

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

> If `Decimal` and `datetime` aren't already imported at the top of `schemas.py`, add `from datetime import datetime` and `from decimal import Decimal`.

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/whales.py`, add the import and a new route handler at the bottom:

```python
from app.api.schemas import (
    PendingTransferOut,
    PendingTransfersResponse,
    WhaleTransfer,
    WhaleTransfersResponse,
)
from app.core.models import PendingTransfer, Transfer
```

Add the route:

```python
@router.get("/pending", response_model=PendingTransfersResponse)
def pending_whales(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(20, ge=1, le=100),
) -> PendingTransfersResponse:
    rows = (
        session.execute(
            select(PendingTransfer).order_by(PendingTransfer.seen_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    return PendingTransfersResponse(
        pending=[
            PendingTransferOut(
                tx_hash=r.tx_hash,
                from_addr=r.from_addr,
                to_addr=r.to_addr,
                from_label=label_for(r.from_addr),
                to_label=label_for(r.to_addr),
                asset=r.asset,
                amount=r.amount,
                usd_value=r.usd_value,
                seen_at=r.seen_at,
            )
            for r in rows
        ]
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_pending_api.py -v`

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/whales.py backend/app/api/schemas.py backend/tests/test_pending_api.py
git commit -m "feat(mempool): GET /api/whales/pending endpoint"
```

---

## Task 8: Frontend — Pending section in WhaleTransfersPanel

**Files:**
- Modify: `frontend/src/api.ts` (or wherever the existing whale-API client lives — verify path)
- Modify: `frontend/src/components/WhaleTransfersPanel.tsx`

- [ ] **Step 1: Add API client function**

Inspect `frontend/src/api.ts` (or the project's API client file) and add a function next to the existing `getWhaleTransfers`:

```typescript
export type PendingWhale = {
  tx_hash: string;
  from_addr: string;
  to_addr: string;
  from_label: string | null;
  to_label: string | null;
  asset: string;
  amount: number;
  usd_value: number | null;
  seen_at: string;
};

export type PendingWhalesResponse = {
  pending: PendingWhale[];
};

export async function getPendingWhales(): Promise<PendingWhalesResponse> {
  const res = await fetch(`${API_BASE}/api/whales/pending`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`getPendingWhales failed: ${res.status}`);
  return res.json();
}
```

> Use the existing `API_BASE` and `authHeaders()` patterns the file already exports. If the client uses TanStack Query directly, add a `usePendingWhales()` hook in the corresponding hooks file.

- [ ] **Step 2: Add Pending section to `WhaleTransfersPanel.tsx`**

Open `frontend/src/components/WhaleTransfersPanel.tsx`. At the top of the rendered panel content (above the existing confirmed list), add:

```tsx
const { data: pendingData } = useQuery({
  queryKey: ["pendingWhales"],
  queryFn: getPendingWhales,
  refetchInterval: 5000,
});

const pending = pendingData?.pending ?? [];
```

Render conditionally:

```tsx
{pending.length > 0 && (
  <div className="mb-3">
    <div className="flex items-center gap-2 mb-2">
      <span className="h-2 w-2 rounded-full bg-yellow-500" />
      <span className="text-xs font-semibold uppercase tracking-wide text-yellow-500">
        Pending ({pending.length})
      </span>
    </div>
    <ul className="space-y-1">
      {pending.slice(0, 5).map((p) => (
        <li
          key={p.tx_hash}
          className="border-l-2 border-yellow-500/40 pl-2 text-sm flex justify-between"
        >
          <span>
            {formatAmount(p.amount)} {p.asset}{" "}
            {p.from_label ?? short(p.from_addr)} → {p.to_label ?? short(p.to_addr)}
          </span>
          <span className="text-xs text-muted-foreground">
            {relativeTime(p.seen_at)}
          </span>
        </li>
      ))}
    </ul>
    <hr className="my-3 border-border/50" />
  </div>
)}
```

> Use the existing `formatAmount`, `short`, and `relativeTime` helpers from the file. If they don't exist, define a one-liner `relativeTime(iso: string)` returning e.g. "8s ago" — or import a small utility like `dayjs` if already in the project.

- [ ] **Step 3: Type-check + build the frontend**

Run from `frontend/`:

```bash
npm run typecheck && npm run build
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 4: Manual visual check (optional, only if convenient)**

Run the local dev stack and seed a fake pending row:

```bash
make up
docker compose exec api python -c "
from datetime import UTC, datetime
from decimal import Decimal
from app.core.db import get_sessionmaker
from app.core.models import PendingTransfer
sm = get_sessionmaker()
with sm() as s:
    s.add(PendingTransfer(tx_hash='0xtest', from_addr='0x'+'a'*40, to_addr='0x'+'b'*40, asset='ETH', amount=Decimal('200'), usd_value=Decimal('600000'), seen_at=datetime.now(UTC), nonce=1, gas_price_gwei=Decimal('20')))
    s.commit()
print('seeded')
"
```

Open `http://localhost:5173`. You should see the Pending section with one row.

Clean up:

```bash
docker compose exec api python -c "
from app.core.db import get_sessionmaker
from app.core.models import PendingTransfer
sm = get_sessionmaker()
with sm() as s:
    s.query(PendingTransfer).delete()
    s.commit()
"
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/WhaleTransfersPanel.tsx
git commit -m "feat(mempool): pending section in WhaleTransfersPanel"
```

---

## Task 9: Production smoke test

This is a manual checklist — no code, just verifying the end-to-end on the production server.

- [ ] **Step 1: Push the branch and open a PR**

```bash
git push -u origin feature/mempool-tracking
gh pr create --title "feat(mempool): pending whale tracking" --body "$(cat <<'EOF'
## Summary
- New `pending_transfers` table + ORM model
- Mempool listener: subscribes to `newPendingTransactions` on local Geth, decodes ERC-20 transfer calldata, persists whale-sized pending txs
- Cleanup cron (every 60s) drops rows >30 min old or now confirmed
- New endpoint: GET /api/whales/pending
- WhaleTransfersPanel adds a "Pending" section at top with 5s polling

## Test plan
- [ ] Unit + integration tests pass: `make backend-test`
- [ ] Frontend type-checks + builds: `cd frontend && npm run typecheck && npm run build`
- [ ] Production smoke: ssh to server, deploy, watch logs for `subscribed to newPendingTransactions` and at least one pending whale within 30 min

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Merge to main**

After review, merge the PR.

- [ ] **Step 3: Deploy on production server**

SSH to the server:

```bash
ssh etherscope@84.32.176.155
cd ~/etherscope
git pull origin main
docker compose build api worker realtime frontend
docker compose run --rm api alembic upgrade head
docker compose up -d
```

- [ ] **Step 4: Verify mempool listener is connected**

```bash
docker compose logs realtime --tail 30 | grep -i "mempool\|newPending\|subscribed"
```

Expected: see `subscribed to newPendingTransactions`.

- [ ] **Step 5: Wait 5–10 min, then check pending_transfers table**

```bash
docker compose exec postgres psql -U eth -d eth -c "SELECT tx_hash, asset, amount, seen_at FROM pending_transfers ORDER BY seen_at DESC LIMIT 10;"
```

Expected: at least one row (mainnet typically has 1-3 whale txs per minute).

- [ ] **Step 6: Hit the API**

```bash
curl -s http://localhost:8000/api/whales/pending | python3 -m json.tool
```

Expected: JSON with a `pending` array.

- [ ] **Step 7: Verify in dashboard**

Open `http://84.32.176.155:5173` in a browser. Confirm the Pending section appears at the top of the Whale Transfers panel with at least one row.

- [ ] **Step 8: Wait 35 min, verify cleanup ran**

```bash
docker compose exec postgres psql -U eth -d eth -c "SELECT COUNT(*) FROM pending_transfers WHERE seen_at < NOW() - INTERVAL '30 minutes';"
```

Expected: `0`. (Rows older than 30 min were cleaned up.)

If all 8 steps pass, the feature is live and stable.

---

## Self-Review Notes

- **Spec coverage:** every section of the design spec maps to a task — schema (Task 1), ORM (Task 2), erc20 decoder (Task 3), parser (Task 4), listener integration (Task 5), cleanup job (Task 6), API (Task 7), frontend (Task 8), smoke test (Task 9).
- **Idempotency:** ON CONFLICT DO NOTHING in `_persist_pending` covers re-seen hashes; replacement-by-nonce handles speed-ups.
- **Replacement edge case:** Task 5's `_persist_pending` deletes any row with same `(from_addr, nonce)` and different `tx_hash` before inserting — correct for replaced txs.
- **Cleanup correctness:** Task 6 tests cover stale-by-time AND now-confirmed paths.
- **Reorgs:** addressed by the cleanup pass — if a "confirmed" tx is reorg'd back to pending, our row is gone but the mempool listener will re-insert it on next seen.
- **Listener concurrency:** spawning `asyncio.create_task` per pending hash is bounded by the `LOOKUP_CONCURRENCY` semaphore (32) — prevents pile-up under burst load.
