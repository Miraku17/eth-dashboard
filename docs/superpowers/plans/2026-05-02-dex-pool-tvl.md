# DEX Pool TVL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `DexPoolTvlPanel` showing top-100 Ethereum-mainnet DEX pools by TVL across Uniswap V2/V3 + Curve + Balancer, sourced hourly from DefiLlama's free `/yields/pools` endpoint.

**Architecture:** Extends the existing `DefiLlamaClient` with a `fetch_yield_pools()` method. New hourly arq cron `sync_dex_pool_tvl` (minute 27) writes top-100 rows to `dex_pool_tvl`. New endpoint extends the existing `/api/defi/*` router. Frontend reuses shadcn `SimpleSelect` for the DEX picker.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy, alembic, arq, httpx), Postgres 16, Redis 7, React + Vite + TypeScript + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-05-02-dex-pool-tvl-design.md`.

**File map:**
- Create: `backend/alembic/versions/0013_dex_pool_tvl.py`
- Create: `backend/app/services/dex_pool_sync.py` — `upsert_dex_pool_tvl`
- Create: `backend/app/workers/dex_pool_jobs.py` — `sync_dex_pool_tvl` arq task
- Create: `backend/tests/test_dex_pool_sync.py`, `test_dex_pool_jobs.py`
- Create: `frontend/src/components/DexPoolTvlPanel.tsx`
- Modify: `backend/app/core/models.py` — add `DexPoolTvl`
- Modify: `backend/app/clients/defillama.py` — add `fetch_yield_pools()` method
- Modify: `backend/tests/test_defillama_client.py` — add 2 new tests
- Modify: `backend/app/api/schemas.py` — add `DexPoolTvlPoint`, `DexPoolTvlLatestResponse`
- Modify: `backend/app/api/defi.py` — add `/defi/dex-pools/latest` endpoint
- Modify: `backend/app/workers/arq_settings.py` — register cron at minute 27
- Modify: `frontend/src/api.ts` — types + `fetchDexPoolTvlLatest`
- Modify: `frontend/src/lib/panelRegistry.ts` — register the panel
- Modify: `CLAUDE.md` — v3-dex-pool-tvl milestone line

---

## Task 1 — Database table + ORM

**Files:**
- Create: `backend/alembic/versions/0013_dex_pool_tvl.py`
- Modify: `backend/app/core/models.py`

- [ ] **Step 1: Migration**

Create `backend/alembic/versions/0013_dex_pool_tvl.py`:

```python
"""dex pool tvl

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dex_pool_tvl",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("pool_id", sa.String(80), primary_key=True),
        sa.Column("dex", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("tvl_usd", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dex_pool_tvl")
```

- [ ] **Step 2: ORM class**

In `backend/app/core/models.py`, after the `ProtocolTvl` class, add:

```python
class DexPoolTvl(Base):
    """Hourly top-N DEX-pool TVL snapshot. Source: DefiLlama /yields/pools.
    Filtered to Ethereum mainnet + Uniswap V2/V3 + Curve + Balancer. (v3-dex-pool-tvl)"""
    __tablename__ = "dex_pool_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pool_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dex: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(80))
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))
```

- [ ] **Step 3: Apply migration**

```bash
docker cp /Users/zianvalles/Projects/Eth-dex/backend/alembic/versions/0013_dex_pool_tvl.py eth-api-1:/app/alembic/versions/0013_dex_pool_tvl.py
docker compose -f /Users/zianvalles/Projects/Eth/docker-compose.yml exec -T api alembic upgrade head
```

Expected: `Running upgrade 0012 -> 0013, dex pool tvl`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0013_dex_pool_tvl.py backend/app/core/models.py
git commit -m "feat(dex): add dex_pool_tvl table + DexPoolTvl model"
```

---

## Task 2 — Extend DefiLlama client + tests

**Files:**
- Modify: `backend/app/clients/defillama.py`
- Modify: `backend/tests/test_defillama_client.py`

- [ ] **Step 1: Add 2 failing tests**

Append to `backend/tests/test_defillama_client.py`:

```python
@pytest.mark.asyncio
async def test_fetch_yield_pools_success():
    """Returns the 'data' array from /yields/pools."""
    fake = {
        "status": "success",
        "data": [
            {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "USDC-WETH",
             "pool": "0xpool1", "tvlUsd": 312_000_000.0},
            {"chain": "Ethereum", "project": "curve-dex", "symbol": "3pool",
             "pool": "0xpool2", "tvlUsd": 64_000_000.0},
        ],
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_yield_pools()
    assert len(out) == 2
    assert out[0]["symbol"] == "USDC-WETH"


@pytest.mark.asyncio
async def test_fetch_yield_pools_returns_empty_on_error():
    def boom(req):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_yield_pools()
    assert out == []
```

- [ ] **Step 2: Run tests (expect AttributeError on `fetch_yield_pools`)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_defillama_client.py -v 2>&1 | tail -8
```

- [ ] **Step 3: Implement the new method**

In `backend/app/clients/defillama.py`, add a new method to the `DefiLlamaClient` class (after `fetch_protocol_tvl`):

```python
    async def fetch_yield_pools(self) -> list[dict]:
        """Return DefiLlama's /yields/pools 'data' array (~10k pools across all
        chains/protocols). Caller filters/sorts. Returns [] on any error.

        NOTE: this hits a DIFFERENT base host than /protocol/{slug}.
        DefiLlama serves yields at https://yields.llama.fi/, distinct from the
        api.llama.fi protocol endpoint. The httpx client passed in must already
        be configured with that base URL.
        """
        try:
            resp = await self._http.get("/pools", timeout=30.0)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("defillama yield pools fetch failed: %s", e)
            return []
        return body.get("data") or []
```

(The base URL is set when the client is constructed. The cron in Task 4 will pass `https://yields.llama.fi` as the base.)

Also export a constant for the yields host. Near the existing `DEFILLAMA_BASE_URL = "https://api.llama.fi"`, add:

```python
DEFILLAMA_YIELDS_BASE_URL = "https://yields.llama.fi"
```

- [ ] **Step 4: Run tests (expect 5 passed: 3 prior + 2 new)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_defillama_client.py -v 2>&1 | tail -8
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/defillama.py backend/tests/test_defillama_client.py
git commit -m "feat(dex): extend DefiLlamaClient with fetch_yield_pools()"
```

---

## Task 3 — `upsert_dex_pool_tvl` service + tests

**Files:**
- Create: `backend/app/services/dex_pool_sync.py`
- Create: `backend/tests/test_dex_pool_sync.py`

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_dex_pool_sync.py`:

```python
"""Tests for the dex_pool_tvl upsert path."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import DexPoolTvl
from app.services.dex_pool_sync import upsert_dex_pool_tvl


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(DexPoolTvl).delete()
        s.commit()
        yield s


def test_upsert_dex_pool_tvl_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool1", "dex": "uniswap-v3",
         "symbol": "USDC-WETH", "tvl_usd": 312_000_000.0},
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool2", "dex": "curve-dex",
         "symbol": "3pool", "tvl_usd": 64_000_000.0},
    ]
    n = upsert_dex_pool_tvl(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(DexPoolTvl).order_by(DexPoolTvl.tvl_usd.desc())).scalars().all()
    assert stored[0].pool_id == "0xpool1"
    assert stored[0].dex == "uniswap-v3"


def test_upsert_dex_pool_tvl_idempotent(session):
    rows = [{"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool1", "dex": "uniswap-v3",
             "symbol": "USDC-WETH", "tvl_usd": 300_000_000.0}]
    upsert_dex_pool_tvl(session, rows)
    session.commit()
    rows[0]["tvl_usd"] = 350_000_000.0
    upsert_dex_pool_tvl(session, rows)
    session.commit()
    stored = session.execute(select(DexPoolTvl)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].tvl_usd)) == Decimal("350000000.000000")


def test_upsert_dex_pool_tvl_multi_pool_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": f"0xpool{i}", "dex": "uniswap-v3",
         "symbol": f"PAIR{i}", "tvl_usd": 1e6 * (10 - i)} for i in range(1, 6)
    ]
    assert upsert_dex_pool_tvl(session, rows) == 5
```

- [ ] **Step 2: Run tests (expect ImportError)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_dex_pool_sync.py -v 2>&1 | tail -8
```

- [ ] **Step 3: Implement the upsert**

Create `backend/app/services/dex_pool_sync.py`:

```python
"""Upsert path for hourly DEX pool TVL snapshots. One row per
(ts_bucket, pool_id). Postgres on_conflict_do_update for idempotency."""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import DexPoolTvl


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    cleaned = value.replace("Z", "+00:00").replace(" UTC", "+00:00")
    return datetime.fromisoformat(cleaned)


def upsert_dex_pool_tvl(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, pool_id)."""
    if not rows:
        return 0
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "pool_id": r["pool_id"],
            "dex": r["dex"],
            "symbol": r["symbol"],
            "tvl_usd": r["tvl_usd"],
        }
        for r in rows
    ]
    stmt = pg_insert(DexPoolTvl).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "pool_id"],
        set_={
            "dex": stmt.excluded.dex,
            "symbol": stmt.excluded.symbol,
            "tvl_usd": stmt.excluded.tvl_usd,
        },
    )
    session.execute(stmt)
    return len(values)
```

- [ ] **Step 4: Run tests (expect 3 passed)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_dex_pool_sync.py -v 2>&1 | tail -8
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dex_pool_sync.py backend/tests/test_dex_pool_sync.py
git commit -m "feat(dex): upsert_dex_pool_tvl service + tests"
```

---

## Task 4 — `sync_dex_pool_tvl` arq task + tests

**Files:**
- Create: `backend/app/workers/dex_pool_jobs.py`
- Create: `backend/tests/test_dex_pool_jobs.py`

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_dex_pool_jobs.py`:

```python
"""Tests for the DEX-pool TVL cron — exercises filter / sort / top-N logic
without hitting DefiLlama."""
from app.workers.dex_pool_jobs import _filter_and_top_n, ALLOWED_DEXES, TOP_N


def test_filter_and_top_n_keeps_only_ethereum_and_allowed_dexes():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "USDC-WETH",
         "pool": "0xa", "tvlUsd": 100e6},
        {"chain": "Polygon",  "project": "uniswap-v3", "symbol": "USDC-WMATIC",
         "pool": "0xb", "tvlUsd": 90e6},   # wrong chain
        {"chain": "Ethereum", "project": "sushi", "symbol": "USDC-WETH",
         "pool": "0xc", "tvlUsd": 80e6},   # wrong project
        {"chain": "Ethereum", "project": "curve-dex", "symbol": "3pool",
         "pool": "0xd", "tvlUsd": 70e6},
    ]
    out = _filter_and_top_n(pools)
    pool_ids = [p["pool"] for p in out]
    assert pool_ids == ["0xa", "0xd"]


def test_filter_and_top_n_sorts_desc_by_tvl():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A-B",
         "pool": f"0x{i:02x}", "tvlUsd": 1e6 * i} for i in range(1, 6)
    ]
    out = _filter_and_top_n(pools)
    tvls = [p["tvlUsd"] for p in out]
    assert tvls == sorted(tvls, reverse=True)


def test_filter_and_top_n_caps_at_top_n():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A-B",
         "pool": f"0x{i:04x}", "tvlUsd": 1e6 * (200 - i)} for i in range(200)
    ]
    out = _filter_and_top_n(pools)
    assert len(out) == TOP_N


def test_filter_and_top_n_skips_missing_or_zero_tvl():
    pools = [
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "A", "pool": "0xa", "tvlUsd": 100e6},
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "B", "pool": "0xb", "tvlUsd": None},
        {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "C", "pool": "0xc", "tvlUsd": 0.0},
    ]
    out = _filter_and_top_n(pools)
    pool_ids = [p["pool"] for p in out]
    assert pool_ids == ["0xa"]


def test_allowed_dexes_intact():
    assert ALLOWED_DEXES == {"uniswap-v3", "uniswap-v2", "curve-dex", "balancer-v2"}
```

- [ ] **Step 2: Run tests (expect ImportError)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_dex_pool_jobs.py -v 2>&1 | tail -8
```

- [ ] **Step 3: Implement the cron**

Create `backend/app/workers/dex_pool_jobs.py`:

```python
"""Hourly cron: snapshot top-N Ethereum-mainnet DEX pools by TVL.

DefiLlama /yields/pools returns ~10k pools across all chains/protocols.
We filter to Ethereum + Uniswap V2/V3 + Curve + Balancer, sort by tvlUsd
desc, take top 100, upsert.
"""
import logging
from datetime import UTC, datetime

import httpx

from app.clients.defillama import DEFILLAMA_YIELDS_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.dex_pool_sync import upsert_dex_pool_tvl

log = logging.getLogger(__name__)

ALLOWED_DEXES: frozenset[str] = frozenset(
    {"uniswap-v3", "uniswap-v2", "curve-dex", "balancer-v2"}
)
TOP_N = 100


def _filter_and_top_n(pools: list[dict]) -> list[dict]:
    """Keep Ethereum + allowed-DEX pools with positive TVL, sort desc, cap top 100."""
    filtered: list[dict] = []
    for p in pools:
        if p.get("chain") != "Ethereum":
            continue
        if p.get("project") not in ALLOWED_DEXES:
            continue
        tvl = p.get("tvlUsd")
        if not isinstance(tvl, (int, float)) or tvl <= 0:
            continue
        filtered.append(p)
    filtered.sort(key=lambda p: p["tvlUsd"], reverse=True)
    return filtered[:TOP_N]


async def sync_dex_pool_tvl(ctx: dict) -> dict:
    """Snapshot top-100 Ethereum DEX pools by TVL at top-of-hour."""
    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()

    async with httpx.AsyncClient(
        base_url=DEFILLAMA_YIELDS_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=30.0,
    ) as http:
        client = DefiLlamaClient(http)
        all_pools = await client.fetch_yield_pools()

    if not all_pools:
        log.warning("dex pool tvl: no pools fetched — skipping write")
        return {"dex_pool_tvl": 0}

    top = _filter_and_top_n(all_pools)
    rows = [
        {
            "ts_bucket": ts_bucket,
            "pool_id": p["pool"],
            "dex": p["project"],
            "symbol": p.get("symbol") or "",
            "tvl_usd": float(p["tvlUsd"]),
        }
        for p in top
    ]

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_dex_pool_tvl(session, rows)
        session.commit()

    record_sync_ok("dex_pool_tvl")
    log.info("synced dex_pool_tvl: %d pools (top of %d Ethereum pools)", n, len(all_pools))
    return {"dex_pool_tvl": n}
```

- [ ] **Step 4: Run tests (expect 5 passed)**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest tests/test_dex_pool_jobs.py -v 2>&1 | tail -8
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/dex_pool_jobs.py backend/tests/test_dex_pool_jobs.py
git commit -m "feat(dex): sync_dex_pool_tvl arq task + tests"
```

---

## Task 5 — Wire cron into arq settings

**Files:**
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Register cron**

In `backend/app/workers/arq_settings.py`:

1. Add import next to the existing `defi_jobs` import:

```python
from app.workers.dex_pool_jobs import sync_dex_pool_tvl
```

2. Add to `WorkerSettings.functions` tuple:

```python
        sync_dex_pool_tvl,
```

3. Add cron entry, minute=27 (defi_tvl is at 17, lst_supply at 7 — 27 keeps it in its own slot):

```python
        # DEX-pool TVL: hourly DefiLlama /yields/pools snapshot, offset to
        # minute 27 so we don't collide with defi_tvl (17) or lst_supply (7).
        cron(sync_dex_pool_tvl, minute={27}, run_at_startup=False),
```

- [ ] **Step 2: Sanity check syntax**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/python -c "
import ast
with open('app/workers/arq_settings.py') as f:
    ast.parse(f.read())
print('syntax OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/arq_settings.py
git commit -m "feat(dex): register sync_dex_pool_tvl cron (minute 27)"
```

---

## Task 6 — API schemas + endpoint

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/defi.py`

- [ ] **Step 1: Add schemas**

In `backend/app/api/schemas.py`, after the existing `DefiTvlLatestResponse` class, add:

```python
class DexPoolTvlPoint(BaseModel):
    pool_id: str
    dex: str
    symbol: str
    tvl_usd: float


class DexPoolTvlLatestResponse(BaseModel):
    ts_bucket: datetime | None
    pools: list[DexPoolTvlPoint]
```

- [ ] **Step 2: Add endpoint**

In `backend/app/api/defi.py`:

1. Update the schemas import block:

```python
from app.api.schemas import (
    DefiTvlAsset,
    DefiTvlLatestResponse,
    DefiTvlPoint,
    DefiTvlPointsResponse,
    DefiTvlProtocolSnapshot,
    DexPoolTvlLatestResponse,
    DexPoolTvlPoint,
)
```

2. Update model import:

```python
from app.core.models import DexPoolTvl, ProtocolTvl
```

3. At the bottom of the file (after `defi_tvl_latest`), add:

```python
@router.get("/dex-pools/latest", response_model=DexPoolTvlLatestResponse)
def dex_pools_latest(
    session: Annotated[Session, Depends(get_session)],
) -> DexPoolTvlLatestResponse:
    """Latest hourly snapshot of top-N DEX pools, sorted desc by tvl_usd."""
    latest_ts = session.execute(
        select(DexPoolTvl.ts_bucket).order_by(DexPoolTvl.ts_bucket.desc()).limit(1)
    ).scalar()
    if latest_ts is None:
        return DexPoolTvlLatestResponse(ts_bucket=None, pools=[])
    rows = session.execute(
        select(DexPoolTvl)
        .where(DexPoolTvl.ts_bucket == latest_ts)
        .order_by(DexPoolTvl.tvl_usd.desc())
    ).scalars().all()
    return DexPoolTvlLatestResponse(
        ts_bucket=latest_ts,
        pools=[
            DexPoolTvlPoint(
                pool_id=r.pool_id,
                dex=r.dex,
                symbol=r.symbol,
                tvl_usd=float(r.tvl_usd),
            )
            for r in rows
        ],
    )
```

- [ ] **Step 3: Smoke-check imports + routes**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/python -c "
from app.api.defi import router
print('routes:', [r.path for r in router.routes])
"
```

Expected: `['/defi/tvl', '/defi/tvl/latest', '/defi/dex-pools/latest']`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/defi.py
git commit -m "feat(dex): /api/defi/dex-pools/latest endpoint + schemas"
```

---

## Task 7 — Frontend types + fetcher

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetcher**

In `frontend/src/api.ts`, after the existing `fetchDefiTvlLatest` function, add:

```typescript
export type DexPoolTvlPoint = {
  pool_id: string;
  dex: string;
  symbol: string;
  tvl_usd: number;
};

export type DexPoolTvlLatestResponse = {
  ts_bucket: string | null;
  pools: DexPoolTvlPoint[];
};

export async function fetchDexPoolTvlLatest(): Promise<DexPoolTvlLatestResponse> {
  const r = await apiFetch(`/api/defi/dex-pools/latest`);
  if (!r.ok) throw new Error(`dex pool tvl latest ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Build**

```bash
cd /Users/zianvalles/Projects/Eth-dex/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(dex): frontend fetchDexPoolTvlLatest + types"
```

---

## Task 8 — `DexPoolTvlPanel` component + registry

**Files:**
- Create: `frontend/src/components/DexPoolTvlPanel.tsx`
- Modify: `frontend/src/lib/panelRegistry.ts`

- [ ] **Step 1: Write panel**

Create `frontend/src/components/DexPoolTvlPanel.tsx`:

```typescript
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDexPoolTvlLatest, type DexPoolTvlPoint } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import { SimpleSelect } from "./ui/Select";

const TOP_N_DISPLAY = 20;

type DexFilter = "ALL" | "uniswap-v3" | "uniswap-v2" | "curve-dex" | "balancer-v2";

const DEX_LABELS: Record<DexFilter, string> = {
  ALL: "All DEXes",
  "uniswap-v3": "Uniswap v3",
  "uniswap-v2": "Uniswap v2",
  "curve-dex": "Curve",
  "balancer-v2": "Balancer v2",
};

const DEX_OPTIONS: { value: DexFilter; label: string }[] = [
  { value: "ALL", label: "All DEXes" },
  { value: "uniswap-v3", label: "Uniswap v3" },
  { value: "uniswap-v2", label: "Uniswap v2" },
  { value: "curve-dex", label: "Curve" },
  { value: "balancer-v2", label: "Balancer v2" },
];

export default function DexPoolTvlPanel() {
  const [filter, setFilter] = useState<DexFilter>("ALL");

  const { data, isLoading, error } = useQuery({
    queryKey: ["dex-pool-tvl-latest"],
    queryFn: fetchDexPoolTvlLatest,
    refetchInterval: 5 * 60_000,
  });

  const filtered = useMemo<DexPoolTvlPoint[]>(() => {
    const pools = data?.pools ?? [];
    const view = filter === "ALL" ? pools : pools.filter((p) => p.dex === filter);
    return view.slice(0, TOP_N_DISPLAY);
  }, [data, filter]);

  const max = Math.max(1, ...filtered.map((p) => p.tvl_usd));
  const totalView = filtered.reduce((s, p) => s + p.tvl_usd, 0);

  return (
    <Card
      title="DEX pool TVL"
      subtitle={`Ethereum mainnet · top ${TOP_N_DISPLAY} pools by TVL · DefiLlama`}
      actions={
        <SimpleSelect
          value={filter}
          onChange={setFilter}
          options={DEX_OPTIONS}
          ariaLabel="Filter by DEX"
        />
      }
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && filtered.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — first hourly sync pending
        </p>
      )}
      {filtered.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{filtered.length} pools shown</span>
            <span className="font-mono tabular-nums text-slate-300">
              {formatUsdCompact(totalView)} combined
            </span>
          </div>
          <ul className="space-y-2">
            {filtered.map((p) => {
              const barPct = (p.tvl_usd / max) * 100;
              return (
                <li key={p.pool_id} className="text-sm">
                  <div className="flex justify-between mb-1 gap-2 min-w-0">
                    <span className="truncate min-w-0">
                      <span className="text-slate-500 text-[11px] mr-1.5">
                        {DEX_LABELS[p.dex as DexFilter] ?? p.dex}
                      </span>
                      <span className="text-slate-200 font-medium">{p.symbol}</span>
                    </span>
                    <span className="font-mono tabular-nums text-slate-200 shrink-0">
                      {formatUsdCompact(p.tvl_usd)}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                    <div
                      className="h-full bg-brand/70 rounded-full"
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Register panel**

In `frontend/src/lib/panelRegistry.ts`:

1. Add import alphabetically:

```typescript
import DexPoolTvlPanel from "../components/DexPoolTvlPanel";
```

2. Add a new entry after the `defi-tvl` entry:

```typescript
  { id: "dex-pool-tvl", label: "DEX pool TVL", component: DexPoolTvlPanel, defaultPage: "onchain", defaultWidth: 2 },
```

- [ ] **Step 3: Build**

```bash
cd /Users/zianvalles/Projects/Eth-dex/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DexPoolTvlPanel.tsx frontend/src/lib/panelRegistry.ts
git commit -m "feat(dex): DexPoolTvlPanel + registry entry"
```

---

## Task 9 — CLAUDE.md milestone

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add line**

In `CLAUDE.md`, after the existing `v3-defi-tvl` line, add:

```markdown
- v3-dex-pool-tvl ⚠️ DEX pool TVL — hourly arq cron (`sync_dex_pool_tvl`, minute 27) hits DefiLlama's `/yields/pools` endpoint, filters Ethereum mainnet + Uniswap V2/V3 + Curve + Balancer, persists top-100 pools by TVL to `dex_pool_tvl`; `/api/defi/dex-pools/latest` endpoint returns the latest snapshot sorted desc; `DexPoolTvlPanel` renders a DEX picker (shadcn Select) + top-20 pool list with horizontal bars. No new env var. Spec: `docs/superpowers/specs/2026-05-02-dex-pool-tvl-design.md`.
```

(Use ⚠️ until first sync; flip to ✅ in Task 12.)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(dex): add v3-dex-pool-tvl milestone line"
```

---

## Task 10 — Test sweep

- [ ] **Step 1: Full backend pytest**

```bash
cd /Users/zianvalles/Projects/Eth-dex/backend && .venv/bin/pytest -q 2>&1 | tail -5
```

Expected: 13 new tests pass (2 client + 3 sync + 5 jobs + 3 already in defi_jobs from PR #29). No NEW failures vs main; pre-existing `test_flows_api` failures persist.

- [ ] **Step 2: Frontend build**

```bash
cd /Users/zianvalles/Projects/Eth-dex/frontend && npm run build 2>&1 | tail -5
```

---

## Task 11 — Push, PR, merge

- [ ] **Step 1: Push**

```bash
cd /Users/zianvalles/Projects/Eth-dex && git push -u origin feat/dex-pool-tvl
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "feat(dex): top DEX pools by TVL panel — Uniswap V2/V3 + Curve + Balancer" --body "$(cat <<'EOF'
## Summary
Top-100 Ethereum-mainnet DEX pools by TVL across **Uniswap V3**, **Uniswap V2**, **Curve**, and **Balancer V2**. Sourced hourly from DefiLlama's free \`/yields/pools\` endpoint. Answers "where is USDC/USDT/WETH/DAI/WBTC actually locked across DEXes" — companion to the lending-style DeFi TVL panel (PR #29).

Spec: \`docs/superpowers/specs/2026-05-02-dex-pool-tvl-design.md\`.

## Files
**Backend**
- new: alembic 0013 — \`dex_pool_tvl\` table
- new: \`backend/app/services/dex_pool_sync.py\`
- new: \`backend/app/workers/dex_pool_jobs.py\` — minute 27 cron
- mod: \`clients/defillama.py\` (added \`fetch_yield_pools\`), \`models.py\`, \`arq_settings.py\`, \`api/schemas.py\`, \`api/defi.py\`

**Frontend**
- new: \`DexPoolTvlPanel.tsx\` — DEX picker + top-20 pool list
- mod: \`api.ts\`, \`panelRegistry.ts\`

## Test plan
- [x] backend pytest — 10 new tests pass
- [x] \`npm run build\` — succeeds
- [ ] **Post-merge:** trigger first sync, verify ~100 rows land.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Merge + cleanup**

```bash
gh pr merge --squash --delete-branch
cd /Users/zianvalles/Projects/Eth
git worktree remove /Users/zianvalles/Projects/Eth-dex --force
git branch -D feat/dex-pool-tvl || true
git fetch origin && git reset --hard origin/main
```

---

## Task 12 — Trigger first sync, verify

- [ ] **Step 1: Recreate worker + apply migration**

```bash
docker compose up -d worker api
docker compose exec -T api alembic upgrade head
```

- [ ] **Step 2: Trigger sync inline**

```bash
echo 'import asyncio' > /tmp/dex.py
echo 'from app.workers.dex_pool_jobs import sync_dex_pool_tvl' >> /tmp/dex.py
echo 'print(asyncio.run(sync_dex_pool_tvl({})))' >> /tmp/dex.py
docker compose exec -T worker python < /tmp/dex.py
```

Expected: `{'dex_pool_tvl': 100}`.

- [ ] **Step 3: Verify**

```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -t -c \"select dex, count(*), round(sum(tvl_usd)::numeric / 1e9, 2) as total_busd from dex_pool_tvl where ts_bucket = (select max(ts_bucket) from dex_pool_tvl) group by dex order by total_busd desc;\""
```

Expected: 4 rows (uniswap-v3, uniswap-v2, curve-dex, balancer-v2) with non-zero counts.

- [ ] **Step 4: Flip CLAUDE.md ⚠️→✅**

```bash
sed -i '' 's/v3-dex-pool-tvl ⚠️/v3-dex-pool-tvl ✅/' CLAUDE.md
git add CLAUDE.md
git commit -m "docs(dex): flip v3-dex-pool-tvl ⚠️→✅"
git push origin main
```

---

## Self-review

**Spec coverage:**
- Top-100 cap → Task 4 (`TOP_N`).
- Uniswap V2/V3 + Curve + Balancer filter → Task 4 (`ALLOWED_DEXES`).
- DEX picker → Task 8.
- Hourly cron at minute 27 → Task 5.
- Auth-gated endpoint → Task 6 (added to existing `/defi` router which is already gated).
- 10 new tests → Tasks 2, 3, 4.

**Type consistency:**
- `pool_id`, `dex`, `symbol` — all `str`/`String` end-to-end.
- `tvl_usd` is `Numeric(38,6)` → `float` → `number`.
- Cron name `sync_dex_pool_tvl` consistent across worker, registered fn, sync_status key, log line.

**Placeholder scan:** none.

---

## Execution Handoff

Subagent-driven (recommended). Same flow used for v3-staking, v3-lst, v3-defi-tvl.
