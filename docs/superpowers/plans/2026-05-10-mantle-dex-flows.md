# Mantle DEX Flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Mantle-network sibling listener that decodes Agni V3 swap events for MNT pools, persists hourly buy/sell pressure to a new `mantle_order_flow` table, and surfaces it in a new `MantleOrderFlowPanel` on the Markets page.

**Architecture:** Dedicated docker-compose service `mantle_realtime` (profile-gated, opt-in) running `python -m app.realtime.mantle_listener`. Same scaffolding as the existing `arbitrum_realtime` service. Public Mantle WS via `MANTLE_WS_URL` env var; idle when unset. Aggregator stores raw MNT volume (no USD conversion at write time); the read endpoint multiplies by a Redis-cached MNT/USD price from CoinGecko, so a CoinGecko outage cannot drop swap data.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, asyncio + websockets, httpx, Redis, Pydantic v2 (backend); React 18, TanStack Query, Recharts, Tailwind, shadcn/ui (frontend).

**Spec:** `docs/superpowers/specs/2026-05-10-mantle-dex-flows-design.md`

---

## File map

**Create:**
- `backend/alembic/versions/0026_mantle_order_flow.py`
- `backend/app/realtime/mantle_dex_registry.py`
- `backend/app/realtime/mantle_swap_decoder.py`
- `backend/app/realtime/mantle_order_flow_agg.py`
- `backend/app/realtime/mantle_listener.py`
- `backend/app/services/mnt_price.py`
- `backend/app/api/mantle_flows.py`
- `backend/tests/test_mantle_swap_decoder.py`
- `backend/tests/test_mantle_order_flow_agg.py`
- `backend/tests/test_mantle_flows_api.py`
- `frontend/src/components/MantleOrderFlowPanel.tsx`
- `docs/mantle-setup.md`

**Modify:**
- `backend/app/core/models.py` (add `MantleOrderFlow`)
- `backend/app/core/config.py` (add `mantle_ws_url`)
- `backend/app/main.py` (register router)
- `backend/app/api/schemas.py` (add response schemas)
- `frontend/src/api.ts` (add fetcher + types)
- `frontend/src/lib/panelRegistry.ts` (register panel)
- `docker-compose.yml` (add `mantle_realtime` service)
- `.env.example` (add `MANTLE_WS_URL=`)
- `CLAUDE.md` (move backlog item to shipped, post-merge)

---

## Test runner

The repo's canonical command is `make backend-test` (runs `cd backend && .venv/bin/pytest -v`). For a single file: `cd backend && .venv/bin/pytest tests/test_X.py -v`. Pure-compute tests (decoder, registry) don't touch the DB; aggregator and API tests use testcontainers Postgres.

---

## Task 1: Schema — `MantleOrderFlow` model + alembic 0026 migration

**Files:**
- Modify: `backend/app/core/models.py` (add new class after `OrderFlow`)
- Create: `backend/alembic/versions/0026_mantle_order_flow.py`

- [ ] **Step 1: Add the SQLAlchemy model**

Open `backend/app/core/models.py`, find the existing `class OrderFlow(Base):` block (around line 142), and add the following class immediately after it:

```python
class MantleOrderFlow(Base):
    """Hourly DEX buy/sell pressure for MNT on Mantle DEXes (post-v4 backlog).

    Sibling table to OrderFlow but stores raw MNT volume rather than USD,
    because the writer (mantle_realtime) is intentionally price-independent —
    USD valuation happens at read time using a Redis-cached CoinGecko
    snapshot. v1 only ships rows with dex='agni'; the column accommodates
    additional Mantle DEXes (fusionx, cleopatra, butter, …) without schema
    change."""
    __tablename__ = "mantle_order_flow"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    dex: Mapped[str] = mapped_column(String(16), primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)  # "buy" | "sell"
    count: Mapped[int] = mapped_column(BigInteger)
    mnt_amount: Mapped[float] = mapped_column(Numeric(38, 18))
```

- [ ] **Step 2: Write the alembic migration**

Create `backend/alembic/versions/0026_mantle_order_flow.py` with the following contents:

```python
"""mantle order flow (Agni V3 — Mantle Network)

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-10

Hourly buy/sell pressure for MNT on Mantle DEXes. v1 only writes
dex='agni' but the column is sized for more. Storing raw MNT volume
keeps the writer price-independent — the API multiplies by a Redis-
cached CoinGecko MNT/USD snapshot at read time.
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mantle_order_flow",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dex", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("count", sa.BigInteger, nullable=False),
        sa.Column("mnt_amount", sa.Numeric(38, 18), nullable=False),
        sa.PrimaryKeyConstraint("ts_bucket", "dex", "side"),
    )
    op.create_index(
        "ix_mantle_order_flow_ts",
        "mantle_order_flow",
        ["ts_bucket"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"ts_bucket": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_mantle_order_flow_ts", table_name="mantle_order_flow")
    op.drop_table("mantle_order_flow")
```

- [ ] **Step 3: Apply the migration**

Run:
```bash
make migrate
```
Expected output: `INFO  [alembic.runtime.migration] Running upgrade 0025 -> 0026, mantle order flow ...`

- [ ] **Step 4: Verify the table exists**

Run:
```bash
docker compose exec postgres psql -U postgres -d ethdb -c "\d mantle_order_flow"
```
Expected: a column listing showing `ts_bucket`, `dex`, `side`, `count`, `mnt_amount` and a composite PK on `(ts_bucket, dex, side)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/models.py backend/alembic/versions/0026_mantle_order_flow.py
git commit -m "feat(mantle): mantle_order_flow schema + alembic 0026"
```

---

## Task 2: Config — `MANTLE_WS_URL` setting + `.env.example`

**Files:**
- Modify: `backend/app/core/config.py` (add field)
- Modify: `.env.example` (document the var)

- [ ] **Step 1: Add the setting**

In `backend/app/core/config.py`, find the existing `arbitrum_http_url: str = ""` line and add the following immediately after it:

```python
    # Mantle WS endpoint — used by the mantle_realtime sibling listener.
    # No Alchemy fallback in v1; defaults to "" so the listener idles
    # cleanly. Public RPC (e.g. wss://mantle-rpc.publicnode.com) is fine.
    mantle_ws_url: str = ""
```

- [ ] **Step 2: Document in `.env.example`**

Append to `/Users/zianvalles/Projects/Eth/.env.example`:

```
# Mantle public WS endpoint (e.g. wss://mantle-rpc.publicnode.com).
# When unset, the mantle_realtime sibling listener idles and the
# /api/flows/mantle-order-flow endpoint returns empty rows.
MANTLE_WS_URL=
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py .env.example
git commit -m "feat(mantle): MANTLE_WS_URL config setting"
```

---

## Task 3: MNT price provider — Redis-cached CoinGecko lookup

**Files:**
- Create: `backend/app/services/mnt_price.py`
- Create: test inline in `backend/tests/test_mnt_price.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mnt_price.py`:

```python
"""Unit tests for app.services.mnt_price.

The function under test is a thin Redis-cached HTTP wrapper, so the
tests stub both Redis and the HTTP client and only assert the wiring."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.mnt_price import get_mnt_usd, MNT_PRICE_CACHE_KEY


@pytest.fixture
def fake_redis():
    r = MagicMock()
    r.get.return_value = None
    return r


def test_returns_cached_value_when_redis_hits(fake_redis):
    fake_redis.get.return_value = b"0.81"
    with patch("app.services.mnt_price.get_redis", return_value=fake_redis):
        assert get_mnt_usd() == pytest.approx(0.81)
    fake_redis.get.assert_called_once_with(MNT_PRICE_CACHE_KEY)


def test_fetches_and_caches_on_miss(fake_redis):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"mantle": {"usd": 0.79}}
    with (
        patch("app.services.mnt_price.get_redis", return_value=fake_redis),
        patch("app.services.mnt_price.httpx.get", return_value=mock_resp) as get,
    ):
        assert get_mnt_usd() == pytest.approx(0.79)
    get.assert_called_once()
    # Redis SET with a 60s TTL
    fake_redis.set.assert_called_once()
    args, kwargs = fake_redis.set.call_args
    assert args[0] == MNT_PRICE_CACHE_KEY
    assert kwargs.get("ex") == 60


def test_returns_none_on_http_error(fake_redis):
    mock_resp = MagicMock(status_code=429)
    mock_resp.json.return_value = {}
    with (
        patch("app.services.mnt_price.get_redis", return_value=fake_redis),
        patch("app.services.mnt_price.httpx.get", return_value=mock_resp),
    ):
        assert get_mnt_usd() is None
    # Negative result is NOT cached.
    fake_redis.set.assert_not_called()


def test_returns_none_on_network_exception(fake_redis):
    import httpx
    with (
        patch("app.services.mnt_price.get_redis", return_value=fake_redis),
        patch("app.services.mnt_price.httpx.get", side_effect=httpx.RequestError("boom")),
    ):
        assert get_mnt_usd() is None
    fake_redis.set.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mnt_price.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.mnt_price'`.

- [ ] **Step 3: Implement the price provider**

Create `backend/app/services/mnt_price.py`:

```python
"""Redis-cached MNT/USD lookup via CoinGecko's free /simple/price endpoint.

Used at /api/flows/mantle-order-flow read time to convert raw mnt_amount
into usd_value. Returns None on HTTP error / rate limit; the endpoint
falls back to MNT-denominated bars in that case. Negative results are
NOT cached so the next request re-attempts immediately."""
from __future__ import annotations

import logging
from typing import Final

import httpx

from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

MNT_PRICE_CACHE_KEY: Final[str] = "mnt_usd:current"
_CACHE_TTL_S: Final[int] = 60
_COINGECKO_URL: Final[str] = (
    "https://api.coingecko.com/api/v3/simple/price?ids=mantle&vs_currencies=usd"
)
_REQUEST_TIMEOUT_S: Final[float] = 5.0


def get_mnt_usd() -> float | None:
    """Return current MNT/USD or None if upstream is unreachable."""
    redis = get_redis()
    cached = redis.get(MNT_PRICE_CACHE_KEY)
    if cached is not None:
        try:
            return float(cached)
        except (TypeError, ValueError):
            log.warning("corrupt mnt_usd cache value: %r", cached)
            # fall through to refresh

    try:
        resp = httpx.get(_COINGECKO_URL, timeout=_REQUEST_TIMEOUT_S)
    except httpx.RequestError as exc:
        log.warning("mnt_usd fetch failed: %s", exc)
        return None

    if resp.status_code != 200:
        log.warning("mnt_usd non-200: %s", resp.status_code)
        return None

    data = resp.json()
    price = data.get("mantle", {}).get("usd")
    if not isinstance(price, (int, float)):
        return None

    redis.set(MNT_PRICE_CACHE_KEY, str(price), ex=_CACHE_TTL_S)
    return float(price)
```

Note: `get_redis()` is the existing helper at `backend/app/core/redis_client.py` — confirm import path matches before saving (same import the existing `app.services.eth_price` module uses).

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mnt_price.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/mnt_price.py backend/tests/test_mnt_price.py
git commit -m "feat(mantle): redis-cached MNT/USD price provider"
```

---

## Task 4: Mantle DEX registry — Agni MNT pools

**Files:**
- Create: `backend/app/realtime/mantle_dex_registry.py`
- Create: test inline in `backend/tests/test_mantle_dex_registry.py`

**Pool selection note:** Resolve the top-5 Agni MNT pools (where MNT is one side) by 30-day volume before writing this task. Use either:
- DefiLlama: `https://yields.llama.fi/pools` filtered to `chain=Mantle`, `project=agni-finance`
- Agni's official UI: pool browser sorted by volume

For each pool, capture: pool address (checksummed), the token0/token1 addresses, and the fee tier. Determine `token0_is_mnt` by comparing addresses (Mantle MNT contract: `0x3c3a81e81dc49A522A592e7622A7E711c06bf354`; if MNT is the *native* asset, the wrapped MNT contract `0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8` is what appears in pool config — verify against the pool's `token0()`/`token1()` calls before pinning).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mantle_dex_registry.py`:

```python
"""Smoke tests for the Mantle Agni pool registry. We don't assert
specific addresses (those will rotate as Agni's pool composition
evolves) — only that the registry's shape is well-formed."""
from app.realtime.mantle_dex_registry import (
    AGNI_POOLS,
    POOL_BY_ADDRESS,
    UNISWAP_V3_SWAP_TOPIC,
)


def test_at_least_one_pool_registered():
    assert len(AGNI_POOLS) >= 1


def test_pools_are_lowercase_addresses():
    for pool in AGNI_POOLS:
        assert pool.address == pool.address.lower(), pool


def test_pool_by_address_is_consistent():
    for pool in AGNI_POOLS:
        assert POOL_BY_ADDRESS[pool.address] is pool


def test_each_pool_has_required_fields():
    for pool in AGNI_POOLS:
        assert pool.dex == "agni"
        assert isinstance(pool.token0_is_mnt, bool)
        assert pool.quote_symbol  # non-empty string


def test_swap_topic_is_v3_keccak():
    # keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
    assert UNISWAP_V3_SWAP_TOPIC == (
        "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_dex_registry.py -v
```
Expected: FAIL with import error.

- [ ] **Step 3: Implement the registry**

Create `backend/app/realtime/mantle_dex_registry.py`:

```python
"""Curated registry of Agni Finance MNT pools on Mantle.

Agni is a Uniswap V3 fork — the Swap event ABI matches V3 exactly,
so the only chain-specific detail is the per-pool config below.
Adding pools is a code change, not config: changes here ship via
the regular release path, not via env vars.

To extend: append a MantlePool entry, set token0_is_mnt by comparing
the pool's token0() address against the Mantle MNT (or wrapped-MNT)
contract address."""
from __future__ import annotations

from typing import Final, NamedTuple

# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
UNISWAP_V3_SWAP_TOPIC: Final[str] = (
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
)

# Mantle native MNT (wrapped) contract. Used at registry-build time
# when verifying token0_is_mnt against on-chain pool config.
MANTLE_WMNT: Final[str] = "0x78c1b0c915c4faa5fffa6cabf0219da63d7f4cb8"


class MantlePool(NamedTuple):
    address: str          # lowercase pool contract address
    dex: str              # 'agni'
    token0_is_mnt: bool   # True iff pool.token0() == WMNT
    quote_symbol: str     # 'USDC' | 'USDT' | 'WETH' | 'mETH' | …
    fee_tier: int         # bps (500 = 0.05%, 3000 = 0.3%, etc.)


# v1: top-5 Agni MNT pools by 30d volume. Pinned at implementation time.
# Re-pin when one of these falls out of the top-5 (registry change ships
# via PR; not auto-rotating in v1).
AGNI_POOLS: Final[tuple[MantlePool, ...]] = (
    # MantlePool(address="0x...", dex="agni", token0_is_mnt=True,  quote_symbol="USDC", fee_tier=500),
    # MantlePool(address="0x...", dex="agni", token0_is_mnt=False, quote_symbol="WETH", fee_tier=3000),
    # … fill in 5 pools before merging.
)


POOL_BY_ADDRESS: Final[dict[str, MantlePool]] = {p.address: p for p in AGNI_POOLS}


def pool_addresses() -> list[str]:
    """List of pool contract addresses for the listener's eth_getLogs filter."""
    return [p.address for p in AGNI_POOLS]
```

**Important:** before this task can pass code review, the engineer MUST replace the commented-out template entries with real Agni pool addresses (top 5 by 30d volume) verified to have MNT as one side. Until that's done, `len(AGNI_POOLS) >= 1` will fail.

- [ ] **Step 4: Pin real pool addresses**

Look up the top-5 Agni MNT pools by 30d volume (see "Pool selection note" above), verify each pool's token0/token1 by calling `eth_call(pool, token0())` against any Mantle RPC, and replace the commented entries in `AGNI_POOLS` with concrete `MantlePool(...)` literals.

Sanity check: `cast call <pool> "token0()(address)" --rpc-url https://rpc.mantle.xyz` should return either WMNT (`0x78c1...`) or the quote token's address. Set `token0_is_mnt=True` accordingly.

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_dex_registry.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/realtime/mantle_dex_registry.py backend/tests/test_mantle_dex_registry.py
git commit -m "feat(mantle): Agni V3 pool registry (top-5 MNT pools)"
```

---

## Task 5: Mantle swap decoder — V3 Swap log → MantleSwap

**Files:**
- Create: `backend/app/realtime/mantle_swap_decoder.py`
- Create: `backend/tests/test_mantle_swap_decoder.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_mantle_swap_decoder.py`:

```python
"""Pure-compute tests for the Mantle V3 swap decoder.

V3 Swap event payload (non-indexed, in `data`):
  amount0:        int256, signed
  amount1:        int256, signed
  sqrtPriceX96:   uint160 (we ignore)
  liquidity:      uint128 (we ignore)
  tick:           int24   (we ignore)

Sign convention (FROM POOL'S PERSPECTIVE):
  positive = pool received (user gave)
  negative = pool sent (user got)

So if MNT is token0:
  amount0 < 0  →  user got MNT     →  side = 'buy'
  amount0 > 0  →  user gave MNT    →  side = 'sell'
"""
from datetime import datetime, timezone
from typing import Final

import pytest

from app.realtime.mantle_dex_registry import MantlePool
from app.realtime.mantle_swap_decoder import decode_mantle_swap


# 18-decimal MNT amount, encoded as a signed 256-bit two's-complement word.
ONE_MNT: Final[int] = 10**18

POOL_MNT_TOKEN0 = MantlePool(
    address="0x" + "a" * 40,
    dex="agni",
    token0_is_mnt=True,
    quote_symbol="USDC",
    fee_tier=500,
)

POOL_MNT_TOKEN1 = MantlePool(
    address="0x" + "b" * 40,
    dex="agni",
    token0_is_mnt=False,
    quote_symbol="WETH",
    fee_tier=3000,
)

UNKNOWN_POOL_ADDR = "0x" + "c" * 40

V3_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


def _to_word(n: int) -> str:
    """Encode a signed int256 as a 64-char hex word (no 0x prefix)."""
    if n < 0:
        n += 1 << 256
    return f"{n:064x}"


def _make_log(*, pool: str, amount0: int, amount1: int) -> dict:
    """Build a minimal V3 Swap log fixture."""
    data = "0x" + _to_word(amount0) + _to_word(amount1) + _to_word(0) + _to_word(0) + _to_word(0)
    return {
        "address": pool,
        "topics": [V3_TOPIC, "0x" + "0" * 64, "0x" + "0" * 64],
        "data": data,
    }


def test_buy_when_mnt_is_token0():
    # User receives 5 MNT (amount0 = -5 MNT)
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=-5 * ONE_MNT, amount1=100 * 10**6)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "buy"
    assert result.mnt_amount == pytest.approx(5.0)
    assert result.dex == "agni"


def test_sell_when_mnt_is_token0():
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=3 * ONE_MNT, amount1=-50 * 10**6)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "sell"
    assert result.mnt_amount == pytest.approx(3.0)


def test_buy_when_mnt_is_token1():
    # User receives 7 MNT (amount1 = -7 MNT)
    log = _make_log(pool=POOL_MNT_TOKEN1.address, amount0=2 * 10**18, amount1=-7 * ONE_MNT)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN1, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "buy"
    assert result.mnt_amount == pytest.approx(7.0)


def test_sell_when_mnt_is_token1():
    log = _make_log(pool=POOL_MNT_TOKEN1.address, amount0=-1 * 10**18, amount1=4 * ONE_MNT)
    result = decode_mantle_swap(log, POOL_MNT_TOKEN1, ts=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert result is not None
    assert result.side == "sell"
    assert result.mnt_amount == pytest.approx(4.0)


def test_truncated_data_returns_none():
    log = {"address": POOL_MNT_TOKEN0.address, "topics": [V3_TOPIC], "data": "0xdead"}
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None


def test_wrong_topic_returns_none():
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=-ONE_MNT, amount1=ONE_MNT)
    log["topics"] = ["0x" + "f" * 64]
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None


def test_zero_mnt_amount_returns_none():
    # Some V3 pools emit Swap with one side zero (degenerate edge case).
    log = _make_log(pool=POOL_MNT_TOKEN0.address, amount0=0, amount1=ONE_MNT)
    assert decode_mantle_swap(log, POOL_MNT_TOKEN0, ts=datetime(2026, 5, 10, tzinfo=timezone.utc)) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_swap_decoder.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the decoder**

Create `backend/app/realtime/mantle_swap_decoder.py`:

```python
"""Decode Agni (Uniswap V3 fork) Swap events into MantleSwap tuples.

Pure functions — no DB, no network. The Mantle listener calls
`decode_mantle_swap()` per Swap log it pulls back from eth_getLogs;
the MantleOrderFlowAggregator accumulates the results into hourly
buckets.

V3 Swap event:
  Swap(address sender, address recipient, int256 amount0, int256 amount1,
       uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
  Non-indexed signed amounts in `data`, FROM THE POOL'S PERSPECTIVE:
    positive = pool received (user gave)
    negative = pool sent     (user got)
  MNT = token0, amount0 < 0 → user bought MNT (side='buy').
  MNT = token0, amount0 > 0 → user sold MNT   (side='sell').
  Mirror for token1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.realtime.mantle_dex_registry import MantlePool, UNISWAP_V3_SWAP_TOPIC

MNT_DECIMALS = 18
_WEI_PER_MNT = 10**MNT_DECIMALS


@dataclass(frozen=True)
class MantleSwap:
    dex: str            # 'agni'
    side: str           # 'buy' | 'sell'  (user perspective on MNT)
    mnt_amount: float   # positive MNT volume, in MNT units (not wei)
    ts: datetime


def _hex_to_int_signed(word: str) -> int:
    """Convert a 64-char hex word (no 0x prefix) to a signed int256."""
    n = int(word, 16)
    if n >= 1 << 255:
        n -= 1 << 256
    return n


def _slice_words(data_hex: str) -> list[str]:
    """Split `0x…` payload into 64-char hex words."""
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return [body[i : i + 64] for i in range(0, len(body), 64)]


def decode_mantle_swap(log: dict, pool: MantlePool, *, ts: datetime) -> MantleSwap | None:
    """Decode one V3 Swap log under the given pool's MNT side configuration.

    Returns None on:
      * topic mismatch
      * truncated payload (< 5 words)
      * zero MNT amount on the relevant side
    """
    topics = log.get("topics") or []
    if not topics or topics[0].lower() != UNISWAP_V3_SWAP_TOPIC:
        return None

    words = _slice_words(log.get("data", ""))
    if len(words) < 5:
        return None

    amount0 = _hex_to_int_signed(words[0])
    amount1 = _hex_to_int_signed(words[1])

    raw = amount0 if pool.token0_is_mnt else amount1
    if raw == 0:
        return None

    side = "buy" if raw < 0 else "sell"
    mnt_amount = abs(raw) / _WEI_PER_MNT

    return MantleSwap(dex=pool.dex, side=side, mnt_amount=mnt_amount, ts=ts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_swap_decoder.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/mantle_swap_decoder.py backend/tests/test_mantle_swap_decoder.py
git commit -m "feat(mantle): V3 swap decoder for Agni MNT pools"
```

---

## Task 6: Mantle order-flow aggregator

**Files:**
- Create: `backend/app/realtime/mantle_order_flow_agg.py`
- Create: `backend/tests/test_mantle_order_flow_agg.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_mantle_order_flow_agg.py`:

```python
"""Aggregator semantics tests. Use a real testcontainers Postgres
because the additive ON CONFLICT path is the most important property
to verify and mocking session execution would obscure it."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.models import MantleOrderFlow
from app.realtime.mantle_order_flow_agg import MantleOrderFlowAggregator
from app.realtime.mantle_swap_decoder import MantleSwap


@pytest.fixture
def agg(test_session_factory):
    """test_session_factory fixture comes from conftest.py and yields
    a sessionmaker bound to a freshly migrated testcontainers Postgres."""
    return MantleOrderFlowAggregator(test_session_factory)


def _swap(side: str, amount: float, ts: datetime, dex: str = "agni") -> MantleSwap:
    return MantleSwap(dex=dex, side=side, mnt_amount=amount, ts=ts)


def _read_all(test_session_factory) -> list[MantleOrderFlow]:
    with test_session_factory() as s:
        return list(s.scalars(select(MantleOrderFlow).order_by(
            MantleOrderFlow.ts_bucket, MantleOrderFlow.dex, MantleOrderFlow.side
        )))


def test_two_buys_same_hour_collapse_to_single_row(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)
    agg.add(_swap("buy", 5.0, h.replace(minute=12)))
    agg.add(_swap("buy", 3.0, h.replace(minute=58)))
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 1
    assert rows[0].side == "buy"
    assert float(rows[0].mnt_amount) == pytest.approx(8.0)
    assert rows[0].count == 2


def test_hour_rollover_writes_previous_bucket(agg, test_session_factory):
    h1 = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    h2 = datetime(2026, 5, 10, 15, 5, tzinfo=timezone.utc)
    agg.add(_swap("buy", 4.0, h1))
    agg.add(_swap("sell", 2.0, h2))   # different hour → flush prev
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 2
    by_hour = {r.ts_bucket: r for r in rows}
    h1_bucket = h1.replace(minute=0, second=0, microsecond=0)
    h2_bucket = h2.replace(minute=0, second=0, microsecond=0)
    assert float(by_hour[h1_bucket].mnt_amount) == pytest.approx(4.0)
    assert by_hour[h1_bucket].side == "buy"
    assert float(by_hour[h2_bucket].mnt_amount) == pytest.approx(2.0)
    assert by_hour[h2_bucket].side == "sell"


def test_partial_flush_idempotent_via_additive_on_conflict(agg, test_session_factory):
    """Simulate a graceful restart mid-hour: flush twice with the same
    in-memory buffer state. The on-conflict path should yield doubled
    totals because two flushes of identical state IS double-counting —
    BUT the realistic restart scenario is that the second flush carries
    DIFFERENT (subsequent) swaps, so what we're really testing is that
    the SQL is additive rather than overwriting."""
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)

    # First "process": 1 buy, then crash.
    agg.add(_swap("buy", 5.0, h))
    agg.flush()

    # Second "process" (restart): another buy in the same hour.
    agg2 = MantleOrderFlowAggregator(test_session_factory)
    agg2.add(_swap("buy", 3.0, h.replace(minute=45)))
    agg2.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 1
    assert float(rows[0].mnt_amount) == pytest.approx(8.0)
    assert rows[0].count == 2


def test_zero_amount_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", 0.0, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_negative_amount_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", -1.5, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_unknown_side_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("hodl", 5.0, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_buy_and_sell_in_same_hour_produce_two_rows(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", 5.0, h))
    agg.add(_swap("sell", 2.0, h.replace(minute=45)))
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 2
    by_side = {r.side: r for r in rows}
    assert float(by_side["buy"].mnt_amount) == pytest.approx(5.0)
    assert float(by_side["sell"].mnt_amount) == pytest.approx(2.0)
```

Note: `test_session_factory` is the existing conftest fixture used by `test_order_flow.py`, `test_volume_agg.py`, etc. Confirm its name in `backend/tests/conftest.py` — if it's spelled differently (`session_factory`, `db_session_factory`), update the fixture references.

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_order_flow_agg.py -v
```
Expected: FAIL with `ModuleNotFoundError: app.realtime.mantle_order_flow_agg`.

- [ ] **Step 3: Implement the aggregator**

Create `backend/app/realtime/mantle_order_flow_agg.py`:

```python
"""Hourly aggregator for Mantle DEX order flow.

Mirrors OrderFlowAggregator pattern: in-memory accumulation per
(dex, side), flush on hour rollover with additive ON CONFLICT so
graceful-shutdown partial flushes compose cleanly.

Crucially, this aggregator does NOT consult any price provider. It
stores raw MNT volume; USD valuation happens at /api/flows/mantle-
order-flow read time (see app.api.mantle_flows). This isolation
means a CoinGecko outage cannot drop swap data."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import MantleOrderFlow
from app.realtime.mantle_swap_decoder import MantleSwap

SessionFactory = Callable[[], Session] | sessionmaker


class MantleOrderFlowAggregator:
    """Buffers (dex, side) → (count, mnt_total) for one hour, flushes to
    `mantle_order_flow` when the active hour changes (or on `flush()`)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._current_hour: datetime | None = None
        self._buf: dict[tuple[str, str], tuple[int, float]] = {}

    def add(self, swap: MantleSwap) -> None:
        if swap.side not in ("buy", "sell"):
            return
        if swap.mnt_amount <= 0:
            return
        hour = swap.ts.replace(minute=0, second=0, microsecond=0)
        if self._current_hour is None:
            self._current_hour = hour
        elif hour != self._current_hour:
            self._flush_current()
            self._current_hour = hour
            self._buf = {}
        count, total = self._buf.get((swap.dex, swap.side), (0, 0.0))
        self._buf[(swap.dex, swap.side)] = (count + 1, total + swap.mnt_amount)

    def flush(self) -> None:
        if self._current_hour is not None:
            self._flush_current()
            self._buf = {}
            self._current_hour = None

    def _flush_current(self) -> None:
        if not self._buf or self._current_hour is None:
            return
        rows = []
        for (dex, side), (count, mnt_total) in self._buf.items():
            rows.append({
                "ts_bucket": self._current_hour,
                "dex": dex,
                "side": side,
                "count": count,
                "mnt_amount": mnt_total,
            })
        stmt = pg_insert(MantleOrderFlow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_bucket", "dex", "side"],
            set_={
                # ADDITIVE — graceful-shutdown partial flushes compose.
                "count": MantleOrderFlow.count + stmt.excluded.count,
                "mnt_amount": MantleOrderFlow.mnt_amount + stmt.excluded.mnt_amount,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_order_flow_agg.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/realtime/mantle_order_flow_agg.py backend/tests/test_mantle_order_flow_agg.py
git commit -m "feat(mantle): hourly order-flow aggregator with additive on_conflict"
```

---

## Task 7: Mantle listener entry point

**Files:**
- Create: `backend/app/realtime/mantle_listener.py`

This task has no unit test by design — matches the precedent set by `arbitrum_listener.py` (no test) and `listener.py` (no test). Lifecycle is verified manually in §"Manual verification" of the spec.

- [ ] **Step 1: Implement the listener**

Create `backend/app/realtime/mantle_listener.py`. Use `backend/app/realtime/arbitrum_listener.py` as the template, adapting:
- Class name `ArbitrumClient` → `MantleClient` (same JSON-RPC-over-WS shape)
- WS URL source: `settings.mantle_ws_url` (no Alchemy fallback)
- Idle log message: `"MANTLE_WS_URL unset; mantle_realtime idle"`
- Per-block log filter: `address=mantle_dex_registry.pool_addresses()`, `topics=[UNISWAP_V3_SWAP_TOPIC]`
- Decoder: `decode_mantle_swap(log, POOL_BY_ADDRESS[log.address.lower()], ts=block_ts)`
- Aggregator: `MantleOrderFlowAggregator(get_sessionmaker())` — call `agg.add(swap)` per decoded log
- Watchdog: 60s head-stall timeout (mirror Arbitrum)
- Reconnect backoff: same as Arbitrum (5s base, capped)

Skeleton:

```python
"""Mantle WebSocket listener — Agni V3 swap events for MNT pools.

Sibling to mainnet `app.realtime.listener` and `arbitrum_listener`;
dedicated process so a Mantle public-RPC stall or Agni decoder bug
can't disrupt mainnet processing. Same WS-client / reconnect pattern.

Run as `python -m app.realtime.mantle_listener` from the
`mantle_realtime` docker-compose service (profile-gated, opt-in)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import websockets

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.realtime.mantle_dex_registry import (
    POOL_BY_ADDRESS,
    UNISWAP_V3_SWAP_TOPIC,
    pool_addresses,
)
from app.realtime.mantle_order_flow_agg import MantleOrderFlowAggregator
from app.realtime.mantle_swap_decoder import decode_mantle_swap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mantle_realtime")

RECONNECT_DELAY_S = 5.0
HEAD_STALL_TIMEOUT_S = 60.0
RPC_CALL_TIMEOUT_S = 30.0


class MantleClient:
    """JSON-RPC-over-WS client. Same shape as ArbitrumClient — duplicated
    rather than abstracted because future divergence is plausible and
    listeners are the highest-impact code in the project."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subs: dict[str, asyncio.Queue] = {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list, timeout: float = RPC_CALL_TIMEOUT_S) -> dict:
        rid = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        try:
            await self._ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
            }))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def subscribe(self, params: list) -> asyncio.Queue:
        result = await self.call("eth_subscribe", params)
        sub_id = result["result"]
        q: asyncio.Queue = asyncio.Queue()
        self._subs[sub_id] = q
        return q

    async def reader(self) -> None:
        async for raw in self._ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending[msg["id"]].set_result(msg)
            elif msg.get("method") == "eth_subscription":
                sub_id = msg["params"]["subscription"]
                q = self._subs.get(sub_id)
                if q is not None:
                    await q.put(msg["params"]["result"])


async def _process_block(client: MantleClient, agg: MantleOrderFlowAggregator, head: dict) -> None:
    block_number_hex = head["number"]
    block_ts = datetime.fromtimestamp(int(head["timestamp"], 16), tz=UTC)
    addresses = pool_addresses()
    if not addresses:
        return  # registry empty → nothing to fetch
    logs_resp = await client.call("eth_getLogs", [{
        "fromBlock": block_number_hex,
        "toBlock":   block_number_hex,
        "address":   addresses,
        "topics":    [UNISWAP_V3_SWAP_TOPIC],
    }])
    for raw_log in logs_resp.get("result", []) or []:
        pool = POOL_BY_ADDRESS.get(raw_log["address"].lower())
        if pool is None:
            continue
        swap = decode_mantle_swap(raw_log, pool, ts=block_ts)
        if swap is not None:
            agg.add(swap)


async def _run_once(ws_url: str) -> None:
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
        client = MantleClient(ws)
        reader_task = asyncio.create_task(client.reader())
        try:
            heads_q = await client.subscribe(["newHeads"])
            agg = MantleOrderFlowAggregator(get_sessionmaker())
            log.info("mantle_realtime connected; pools=%d", len(pool_addresses()))
            while True:
                try:
                    head = await asyncio.wait_for(heads_q.get(), timeout=HEAD_STALL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    log.warning("newHeads stalled > %ss; reconnecting", HEAD_STALL_TIMEOUT_S)
                    return
                try:
                    await _process_block(client, agg, head)
                except Exception:
                    log.exception("error processing block; continuing")
        finally:
            agg.flush()  # best-effort drain on disconnect
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task


async def main() -> None:
    settings = get_settings()
    ws_url = settings.mantle_ws_url
    if not ws_url:
        log.info("MANTLE_WS_URL unset; mantle_realtime idle")
        # Sleep instead of exit so docker doesn't restart-loop.
        while True:
            await asyncio.sleep(3600)

    while True:
        try:
            await _run_once(ws_url)
        except Exception:
            log.exception("mantle_realtime crashed; reconnecting in %ss", RECONNECT_DELAY_S)
        await asyncio.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())
```

Cross-check against `arbitrum_listener.py` to confirm import paths match (`get_sessionmaker` location, etc.).

- [ ] **Step 2: Verify the file imports cleanly**

Run:
```bash
cd backend && .venv/bin/python -c "import app.realtime.mantle_listener"
```
Expected: no output (clean import). If it fails, fix imports.

- [ ] **Step 3: Commit**

```bash
git add backend/app/realtime/mantle_listener.py
git commit -m "feat(mantle): WS listener entry point (mirrors arbitrum_realtime)"
```

---

## Task 8: API endpoint + Pydantic schemas

**Files:**
- Modify: `backend/app/api/schemas.py` (add response schemas)
- Create: `backend/app/api/mantle_flows.py` (router)
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_mantle_flows_api.py`

- [ ] **Step 1: Add the response schemas**

In `backend/app/api/schemas.py`, find `class OrderFlowPoint(BaseModel):` (around line 296) and add the following classes near it (group with other flows schemas):

```python
class MantleOrderFlowRow(BaseModel):
    ts_bucket: datetime
    dex: str
    side: str            # "buy" | "sell"
    count: int
    mnt_amount: float
    usd_value: float | None  # null when MNT/USD price is unavailable


class MantleOrderFlowSummary(BaseModel):
    buy_usd: float | None
    sell_usd: float | None
    net_usd: float | None
    active_dexes: list[str]
    mnt_usd: float | None
    price_unavailable: bool


class MantleOrderFlowResponse(BaseModel):
    rows: list[MantleOrderFlowRow]
    summary: MantleOrderFlowSummary
```

- [ ] **Step 2: Write the failing API test**

Create `backend/tests/test_mantle_flows_api.py`:

```python
"""End-to-end test: seed mantle_order_flow rows, hit the endpoint,
assert response shape + USD aggregation + price-fallback path."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


def _seed(session, ts: datetime, dex: str, side: str, count: int, mnt_amount: float) -> None:
    session.execute(text("""
        INSERT INTO mantle_order_flow (ts_bucket, dex, side, count, mnt_amount)
        VALUES (:t, :d, :s, :c, :m)
    """), {"t": ts, "d": dex, "s": side, "c": count, "m": mnt_amount})
    session.commit()


def test_returns_rows_in_window_with_usd_value(test_session_factory):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with test_session_factory() as s:
        _seed(s, now,                         "agni", "buy",  10, 100.0)
        _seed(s, now,                         "agni", "sell",  6,  50.0)
        _seed(s, now - timedelta(hours=48),   "agni", "buy",   1,   1.0)  # outside 24h window

    client = TestClient(app)
    with patch("app.api.mantle_flows.get_mnt_usd", return_value=0.80):
        r = client.get("/api/flows/mantle-order-flow?hours=24")
    assert r.status_code == 200
    body = r.json()

    assert len(body["rows"]) == 2
    by_side = {row["side"]: row for row in body["rows"]}
    assert by_side["buy"]["mnt_amount"] == 100.0
    assert by_side["buy"]["usd_value"]  == 80.0
    assert by_side["sell"]["mnt_amount"] == 50.0
    assert by_side["sell"]["usd_value"]  == 40.0

    summary = body["summary"]
    assert summary["buy_usd"]  == 80.0
    assert summary["sell_usd"] == 40.0
    assert summary["net_usd"]  == 40.0
    assert summary["active_dexes"] == ["agni"]
    assert summary["mnt_usd"]  == 0.80
    assert summary["price_unavailable"] is False


def test_price_unavailable_returns_null_usd(test_session_factory):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with test_session_factory() as s:
        _seed(s, now, "agni", "buy", 1, 5.0)

    client = TestClient(app)
    with patch("app.api.mantle_flows.get_mnt_usd", return_value=None):
        r = client.get("/api/flows/mantle-order-flow?hours=24")
    body = r.json()
    assert body["rows"][0]["usd_value"] is None
    assert body["summary"]["buy_usd"] is None
    assert body["summary"]["price_unavailable"] is True


def test_empty_table_returns_empty_rows(test_session_factory):
    client = TestClient(app)
    with patch("app.api.mantle_flows.get_mnt_usd", return_value=0.80):
        r = client.get("/api/flows/mantle-order-flow?hours=24")
    body = r.json()
    assert body["rows"] == []
    assert body["summary"]["active_dexes"] == []
    assert body["summary"]["buy_usd"] == 0.0
    assert body["summary"]["sell_usd"] == 0.0
```

Note: confirm the testcontainers fixture name in `conftest.py` and whether the test client uses that fixture for DB access. If the existing pattern wires the FastAPI app's DB session to testcontainers automatically, no changes needed. Otherwise, mirror the wiring used by `test_order_flow.py` (or whichever existing endpoint test reads from a seeded table).

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_flows_api.py -v
```
Expected: FAIL with 404 on `/api/flows/mantle-order-flow` (router not registered yet).

- [ ] **Step 4: Implement the endpoint**

Create `backend/app/api/mantle_flows.py`:

```python
"""GET /api/flows/mantle-order-flow — Mantle DEX MNT buy/sell pressure.

Reads `mantle_order_flow` rows over the requested window, multiplies the
raw mnt_amount by a Redis-cached MNT/USD snapshot to produce usd_value,
and aggregates a summary tile. The writer (mantle_realtime) stores raw
MNT only, so a CoinGecko outage degrades gracefully here (null usd_value,
price_unavailable=True) without dropping any swap data."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    MantleOrderFlowResponse,
    MantleOrderFlowRow,
    MantleOrderFlowSummary,
)
from app.core.db import get_session
from app.core.models import MantleOrderFlow
from app.services.mnt_price import get_mnt_usd

router = APIRouter()


@router.get("/api/flows/mantle-order-flow", response_model=MantleOrderFlowResponse)
def mantle_order_flow(
    session: Annotated[Session, Depends(get_session)],
    hours: int = Query(default=24, ge=1, le=168),
) -> MantleOrderFlowResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(session.scalars(
        select(MantleOrderFlow)
        .where(MantleOrderFlow.ts_bucket >= cutoff)
        .order_by(MantleOrderFlow.ts_bucket, MantleOrderFlow.dex, MantleOrderFlow.side)
    ))

    mnt_usd = get_mnt_usd()
    price_unavailable = mnt_usd is None

    out_rows: list[MantleOrderFlowRow] = []
    buy_usd_total = 0.0
    sell_usd_total = 0.0
    active_dexes: set[str] = set()

    for r in rows:
        active_dexes.add(r.dex)
        usd_value = float(r.mnt_amount) * mnt_usd if mnt_usd is not None else None
        if usd_value is not None:
            if r.side == "buy":
                buy_usd_total += usd_value
            elif r.side == "sell":
                sell_usd_total += usd_value
        out_rows.append(MantleOrderFlowRow(
            ts_bucket=r.ts_bucket,
            dex=r.dex,
            side=r.side,
            count=r.count,
            mnt_amount=float(r.mnt_amount),
            usd_value=usd_value,
        ))

    summary = MantleOrderFlowSummary(
        buy_usd=None  if price_unavailable else buy_usd_total,
        sell_usd=None if price_unavailable else sell_usd_total,
        net_usd=None  if price_unavailable else (buy_usd_total - sell_usd_total),
        active_dexes=sorted(active_dexes),
        mnt_usd=mnt_usd,
        price_unavailable=price_unavailable,
    )
    return MantleOrderFlowResponse(rows=out_rows, summary=summary)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import alongside the other API imports (alphabetical order — between `leaderboard_router` and `network_router` works):

```python
from app.api.mantle_flows import router as mantle_flows_router
```

And add the `include_router` call alongside the other registrations (also alphabetical):

```python
app.include_router(mantle_flows_router, prefix="")
```

(Use `prefix=""` because the route already includes `/api/flows/...` in its path. Match the convention used by the existing `flows_router` registration — confirm by reading the surrounding `include_router(...)` lines.)

- [ ] **Step 6: Run the tests to verify they pass**

Run:
```bash
cd backend && .venv/bin/pytest tests/test_mantle_flows_api.py -v
```
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/mantle_flows.py backend/app/main.py backend/tests/test_mantle_flows_api.py
git commit -m "feat(mantle): /api/flows/mantle-order-flow endpoint"
```

---

## Task 9: Frontend API client — types + fetcher

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetcher**

Append to `frontend/src/api.ts` (group with other flow types — search for `OrderFlowResponse` and place near it):

```typescript
export type MantleOrderFlowRow = {
  ts_bucket: string;       // ISO timestamp
  dex: string;             // 'agni'
  side: "buy" | "sell";
  count: number;
  mnt_amount: number;
  usd_value: number | null;
};

export type MantleOrderFlowSummary = {
  buy_usd: number | null;
  sell_usd: number | null;
  net_usd: number | null;
  active_dexes: string[];
  mnt_usd: number | null;
  price_unavailable: boolean;
};

export type MantleOrderFlowResponse = {
  rows: MantleOrderFlowRow[];
  summary: MantleOrderFlowSummary;
};

export async function fetchMantleOrderFlow(
  hours = 24,
): Promise<MantleOrderFlowResponse> {
  const r = await apiFetch(`/api/flows/mantle-order-flow?hours=${hours}`);
  if (!r.ok) throw new Error(`mantle order flow ${r.status}`);
  return await r.json();
}
```

- [ ] **Step 2: Verify type-check passes**

Run:
```bash
cd frontend && npm run build
```
Expected: build succeeds (no TS errors). If errors mention `apiFetch` or import paths, match the existing patterns in `api.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(mantle): frontend api types + fetcher"
```

---

## Task 10: Frontend panel — `MantleOrderFlowPanel`

**Files:**
- Create: `frontend/src/components/MantleOrderFlowPanel.tsx`
- Modify: `frontend/src/lib/panelRegistry.ts` (register panel)

- [ ] **Step 1: Implement the panel**

Use `frontend/src/components/OrderFlowPanel.tsx` as the structural reference (read it first). Create `frontend/src/components/MantleOrderFlowPanel.tsx`:

```typescript
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchMantleOrderFlow, type MantleOrderFlowResponse } from "../api";
import PanelShell from "./PanelShell";

type ChartPoint = {
  ts: string;       // hour-truncated label
  buy_usd: number;
  sell_usd: number; // stored negative for signed-stack effect
};

function buildChartData(resp: MantleOrderFlowResponse | undefined): ChartPoint[] {
  if (!resp) return [];
  const byHour = new Map<string, ChartPoint>();
  for (const r of resp.rows) {
    const point = byHour.get(r.ts_bucket) ?? {
      ts: r.ts_bucket,
      buy_usd: 0,
      sell_usd: 0,
    };
    if (r.side === "buy" && r.usd_value != null) {
      point.buy_usd += r.usd_value;
    } else if (r.side === "sell" && r.usd_value != null) {
      point.sell_usd -= r.usd_value;
    }
    byHour.set(r.ts_bucket, point);
  }
  return [...byHour.values()].sort((a, b) => a.ts.localeCompare(b.ts));
}

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000)     return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toFixed(0)}`;
}

export default function MantleOrderFlowPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["mantle-order-flow"],
    queryFn: () => fetchMantleOrderFlow(24),
    refetchInterval: 60_000,
  });

  const chartData = buildChartData(data);
  const summary = data?.summary;
  const empty = !isLoading && !error && data && data.rows.length === 0;

  return (
    <PanelShell title="Mantle order flow (24h)" subtitle="MNT buy / sell pressure on Agni">
      {isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {error && <p className="p-5 text-sm text-down">unavailable</p>}
      {empty && (
        <p className="p-5 text-sm text-slate-500">
          no data yet — set <code>MANTLE_WS_URL</code> and bring up the
          <code> mantle</code> docker compose profile.
        </p>
      )}

      {summary && data && data.rows.length > 0 && (
        <>
          <div className="grid grid-cols-3 gap-3 px-5 pt-3">
            <Tile label="Buy"  value={fmtUsd(summary.buy_usd)}  tone="up" />
            <Tile label="Sell" value={fmtUsd(summary.sell_usd)} tone="down" />
            <Tile
              label="Net"
              value={fmtUsd(summary.net_usd)}
              tone={(summary.net_usd ?? 0) >= 0 ? "up" : "down"}
            />
          </div>

          <div className="h-56 px-5 pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} stackOffset="sign">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
                <XAxis dataKey="ts" hide />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} tickFormatter={fmtUsd} />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" />
                <Tooltip
                  formatter={(v: number) => fmtUsd(v)}
                  contentStyle={{ background: "#0f172a", border: "1px solid #334155" }}
                />
                <Bar dataKey="buy_usd"  stackId="x" fill="#22c55e" />
                <Bar dataKey="sell_usd" stackId="x" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {summary.price_unavailable && (
            <p className="px-5 pb-3 pt-2 text-xs text-slate-500">
              USD pricing unavailable (CoinGecko); chart shows MNT-denominated bars when reachable.
            </p>
          )}
        </>
      )}
    </PanelShell>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone: "up" | "down" }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-base font-semibold ${tone === "up" ? "text-up" : "text-down"}`}>
        {value}
      </div>
    </div>
  );
}
```

Verify against `OrderFlowPanel.tsx` — color tokens (`text-up`, `text-down`), `<PanelShell>` props, and tile pattern should match the existing convention. If `PanelShell` lives at a different path (`./PanelShell` vs `../components/PanelShell`), fix the import.

- [ ] **Step 2: Register the panel**

In `frontend/src/lib/panelRegistry.ts`:

(a) Add the import (alphabetical, after `LstMarketSharePanel`):
```typescript
import MantleOrderFlowPanel from "../components/MantleOrderFlowPanel";
```

(b) Add the entry in the `PANELS` array, alongside other markets-page panels (after `order-flow` so they sit next to each other):
```typescript
  { id: "mantle-order-flow", label: "Mantle order flow", component: MantleOrderFlowPanel, defaultPage: "markets", defaultWidth: 2 },
```

- [ ] **Step 3: Verify the build**

Run:
```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MantleOrderFlowPanel.tsx frontend/src/lib/panelRegistry.ts
git commit -m "feat(mantle): MantleOrderFlowPanel on Markets page"
```

---

## Task 11: Docker Compose — `mantle_realtime` service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add the service block**

In `docker-compose.yml`, find the existing `arbitrum_realtime` block and add the following block immediately after it (mirror the same indentation):

```yaml
  # Sibling listener for Mantle DEX activity (Agni V3 swaps on MNT pools).
  # Runs in its own process so a Mantle public-RPC stall or Agni decoder
  # bug can't disrupt mainnet realtime processing. When MANTLE_WS_URL is
  # unset, the entrypoint logs a notice and idles — no crash loop.
  mantle_realtime:
    # Opt-in via profile so the listener doesn't crash-loop or burn CUs
    # against an unconfigured Mantle endpoint by default. Start explicitly
    # with `docker compose --profile mantle up -d mantle_realtime`.
    profiles: ["mantle"]
    build: ./backend
    dns: [1.1.1.1, 8.8.8.8]
    env_file: .env
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    command: python -m app.realtime.mantle_listener
    volumes:
      - ./backend:/app
```

- [ ] **Step 2: Verify the compose file parses**

Run:
```bash
docker compose --profile mantle config | grep -A2 mantle_realtime
```
Expected: the resolved service definition prints. No syntax errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(mantle): mantle_realtime sibling docker service (profile-gated)"
```

---

## Task 12: Operator setup doc

**Files:**
- Create: `docs/mantle-setup.md`

- [ ] **Step 1: Write the doc**

Create `docs/mantle-setup.md`:

```markdown
# Mantle realtime listener — operator setup

Starting the `mantle_realtime` sibling listener for MNT DEX flow tracking.

## Prerequisites

- Postgres + Redis containers up (`make up`)
- Migrations applied through revision `0026` (`make migrate`)

## 1. Pick a Mantle WS endpoint

Public Mantle RPCs that expose `eth_subscribe` over WSS:

| Provider           | URL                                          | Notes                         |
|--------------------|----------------------------------------------|-------------------------------|
| PublicNode         | `wss://mantle-rpc.publicnode.com`            | Free, no signup               |
| Ankr (public tier) | `wss://rpc.ankr.com/mantle/ws`               | Free, occasionally rate-limits |
| Mantle official    | `wss://mantle-mainnet.public.blastapi.io`    | Free                          |

Any one works. The listener has a 60s head-stall watchdog that force-reconnects on silent subscription drops, so flaky public endpoints are tolerable.

## 2. Configure `.env`

```
MANTLE_WS_URL=wss://mantle-rpc.publicnode.com
```

When unset, the panel renders an empty-state message and the container idles.

## 3. Bring up the container

```
docker compose --profile mantle up -d mantle_realtime
docker compose logs -f mantle_realtime
```

Expected first log lines:
```
mantle_realtime  INFO  mantle_realtime  mantle_realtime connected; pools=5
mantle_realtime  INFO  mantle_realtime  ...
```

If you see `mantle_realtime  INFO  MANTLE_WS_URL unset; mantle_realtime idle`, your env var didn't propagate — recheck `.env`.

## 4. Verify data is flowing

After ~5 minutes of swap activity, run:

```
docker compose exec postgres psql -U postgres -d ethdb -c "SELECT * FROM mantle_order_flow ORDER BY ts_bucket DESC LIMIT 5;"
```

Once the first hour rolls over, rows appear. The dashboard panel `Mantle order flow` (Markets page) will populate within 60 seconds.

## Stopping

```
docker compose --profile mantle stop mantle_realtime
```

Mainnet and Arbitrum listeners are unaffected.

## Troubleshooting

- **Empty panel after deploy:** check the container logs for connection errors. Public RPCs sometimes block from datacenter IPs.
- **Bars look wrong:** confirm pool addresses in `app/realtime/mantle_dex_registry.py` are still in Agni's top-5 by volume; pools rotate.
- **USD values show null:** CoinGecko is unreachable or rate-limited from the API container. Panel falls back to MNT-denominated bars; no data is lost.
```

- [ ] **Step 2: Commit**

```bash
git add docs/mantle-setup.md
git commit -m "docs(mantle): operator setup guide"
```

---

## Task 13: CLAUDE.md — move backlog item to shipped

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the backlog**

In `CLAUDE.md`, find the `Backlog (post-vacation)` section and replace the `🟡 **Mantle Network DEX flows**` line with a `✅` shipped entry. Add this line after the last v5 status entry in the `## v5 status` section (or, if you prefer, leave it under "Backlog" with the ✅ marker matching the existing pattern for `EURS` and `On-chain perps`):

```markdown
- ✅ **Mantle Network DEX flows** — shipped 2026-05-XX (replace with merge date). Sibling listener `mantle_realtime` (profile-gated, opt-in) consumes Agni V3 Swap events for the top-5 MNT pools, persists hourly buy/sell pressure to `mantle_order_flow`. New `/api/flows/mantle-order-flow` + `MantleOrderFlowPanel` on Markets page. Public Mantle WS via `MANTLE_WS_URL` (idle when unset). USD valuation at read time via Redis-cached CoinGecko MNT/USD — writer is price-independent so a CoinGecko outage cannot drop swap data. v1 is Agni-only; broader DEX coverage (FusionX, Cleopatra, Butter) is registry-only follow-up. Spec: `docs/superpowers/specs/2026-05-10-mantle-dex-flows-design.md`. Setup: `docs/mantle-setup.md`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark Mantle DEX flows shipped"
```

---

## Final verification (manual)

Before declaring v1 done, run through the spec's "Manual verification" checklist:

1. Start `mantle_realtime` against the public WS, watch logs for the first decoded swap within ~5 minutes.
2. Wait for a clean hour rollover, verify a row appears in `mantle_order_flow`:
   ```bash
   docker compose exec postgres psql -U postgres -d ethdb -c "SELECT * FROM mantle_order_flow ORDER BY ts_bucket DESC LIMIT 10;"
   ```
3. Open the panel at `/markets`, confirm bars render and USD valuation is live (CoinGecko reachable).
4. Disconnect the test machine briefly to confirm the empty-state copy appears (no swap data flowing).

After verification, push the branch:
```bash
git push origin main
```
