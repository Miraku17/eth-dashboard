# ETH Staking Flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Beacon Flows panel surfacing net ETH staked (deposits − full validator exits) plus partial-withdrawal rewards over the last 30 days, with a live active-validator-count tile sourced from the self-hosted Lighthouse beacon API.

**Architecture:** New Dune query against the curated `staking_ethereum.flows` spell, persisted hourly via the existing `sync_dune_flows` arq job. Live validator count via a new thin Lighthouse beacon-API client (Redis-cached 5 min). Two new endpoints under `/api/staking/*`, one new React panel reusing the divergent-bar + sparkline pattern from PR #24.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy, alembic, arq, httpx), Postgres 16, Redis 7, React + Vite + TypeScript.

**Spec:** `docs/superpowers/specs/2026-05-02-eth-staking-flows-design.md`.

**File map:**
- Create: `backend/dune/staking_flows.sql` — Dune query SQL
- Create: `backend/alembic/versions/0009_staking_flows.py` — `staking_flows` table migration
- Create: `backend/app/clients/beacon.py` — Lighthouse beacon-API client
- Create: `backend/app/api/staking.py` — `/api/staking/{flows,summary}` routes
- Create: `backend/tests/test_staking_sync.py` — upsert + row-mapping unit tests
- Create: `backend/tests/test_beacon_client.py` — beacon client unit tests
- Create: `frontend/src/components/StakingFlowsPanel.tsx` — React panel
- Modify: `backend/app/core/models.py` — add `StakingFlow` ORM class
- Modify: `backend/app/core/config.py` — add `dune_query_id_staking_flows`, `beacon_http_url` settings
- Modify: `backend/app/services/flow_sync.py` — add `upsert_staking_flows`
- Modify: `backend/app/workers/flow_jobs.py` — add staking_flows to `sync_dune_flows` job list
- Modify: `backend/app/api/__init__.py` — register staking router
- Modify: `backend/app/api/schemas.py` — add `StakingFlowPoint`, `StakingFlowsResponse`, `StakingSummary`
- Modify: `frontend/src/api.ts` — `fetchStakingFlows`, `fetchStakingSummary`, types
- Modify: `frontend/src/lib/panelRegistry.ts` — register `StakingFlowsPanel`
- Modify: `.env.example` — add `BEACON_HTTP_URL`, `DUNE_QUERY_ID_STAKING_FLOWS` keys
- Modify: `CLAUDE.md` — add v3-staking line + operator setup note

Plus, after merge: paste `staking_flows.sql` into a new Dune query via MCP, copy the ID into `.env`, run the worker sync once.

---

## Task 1 — Database table & ORM model

**Files:**
- Create: `backend/alembic/versions/0009_staking_flows.py`
- Modify: `backend/app/core/models.py`

- [ ] **Step 1: Write the alembic migration**

Create `backend/alembic/versions/0009_staking_flows.py`:

```python
"""staking flows

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staking_flows",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("kind", sa.String(20), primary_key=True),
        sa.Column("amount_eth", sa.Numeric(38, 18), nullable=False),
        sa.Column("amount_usd", sa.Numeric(38, 6), nullable=True),
        sa.CheckConstraint(
            "kind IN ('deposit','withdrawal_partial','withdrawal_full')",
            name="staking_flows_kind_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("staking_flows")
```

- [ ] **Step 2: Add the ORM model**

In `backend/app/core/models.py`, after the `VolumeBucket` class, add:

```python
class StakingFlow(Base):
    """Hourly beacon-chain flow leg: deposits, partial withdrawals (rewards
    skim), full withdrawals (validator exits). Sourced from Dune's curated
    staking_ethereum.flows spell. (v3)"""
    __tablename__ = "staking_flows"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    amount_eth: Mapped[float] = mapped_column(Numeric(38, 18))
    amount_usd: Mapped[float | None] = mapped_column(Numeric(38, 6), nullable=True)
```

- [ ] **Step 3: Run the migration locally**

```bash
cd /Users/zianvalles/Projects/Eth && docker compose exec -T api alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 0008 -> 0009, staking flows`.

Verify the table exists:

```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '\\d staking_flows'"
```

Expected: shows the four columns with `(ts_bucket, kind)` as the composite primary key.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0009_staking_flows.py backend/app/core/models.py
git commit -m "feat(staking): add staking_flows table + StakingFlow model"
```

---

## Task 2 — Dune SQL + config keys

**Files:**
- Create: `backend/dune/staking_flows.sql`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the Dune query**

Create `backend/dune/staking_flows.sql`:

```sql
-- Beacon-chain flow legs per hour, last 30d. Sourced from the curated
-- staking_ethereum.flows spell (one row per validator event, with
-- amount_staked / amount_partial_withdrawn / amount_full_withdrawn populated).
--
-- Result columns: ts_bucket, kind, amount_eth, amount_usd
-- kind ∈ {deposit, withdrawal_partial, withdrawal_full}
with hourly as (
  select
    date_trunc('hour', f.block_time) as ts_bucket,
    sum(f.amount_staked) as deposit_eth,
    sum(f.amount_partial_withdrawn) as partial_eth,
    sum(f.amount_full_withdrawn) as full_eth
  from staking_ethereum.flows f
  where f.block_time > now() - interval '30' day
  group by 1
),
eth_price as (
  select date_trunc('hour', minute) as ts_bucket, avg(price) as price_usd
  from prices.usd
  where blockchain = 'ethereum'
    and symbol = 'ETH'
    and minute > now() - interval '30' day
  group by 1
),
priced as (
  select
    h.ts_bucket,
    h.deposit_eth,
    h.partial_eth,
    h.full_eth,
    coalesce(p.price_usd, 0) as price_usd
  from hourly h
  left join eth_price p using (ts_bucket)
)
select ts_bucket, 'deposit' as kind,
       deposit_eth as amount_eth,
       deposit_eth * price_usd as amount_usd
from priced where deposit_eth > 0
union all
select ts_bucket, 'withdrawal_partial' as kind,
       partial_eth as amount_eth,
       partial_eth * price_usd as amount_usd
from priced where partial_eth > 0
union all
select ts_bucket, 'withdrawal_full' as kind,
       full_eth as amount_eth,
       full_eth * price_usd as amount_usd
from priced where full_eth > 0
order by ts_bucket desc
```

- [ ] **Step 2: Add settings**

In `backend/app/core/config.py`, find the existing Dune query ID lines and add:

```python
    dune_query_id_staking_flows: int = 0
```

In the same `Settings` class, add (alongside other URLs like `alchemy_http_url`):

```python
    beacon_http_url: str | None = None
```

- [ ] **Step 3: Update `.env.example`**

In `.env.example`, after the existing `DUNE_QUERY_ID_VOLUME_BUCKETS=` line, add:

```
DUNE_QUERY_ID_STAKING_FLOWS=
```

After the existing `ALCHEMY_HTTP_URL=` block (or wherever the self-hosted node URLs are documented), add:

```
# Self-hosted Lighthouse beacon API (optional). When set, the staking
# panel surfaces a live active-validator-count tile. Default Lighthouse
# HTTP port is 5052; use the docker-bridge host for cross-container reach.
BEACON_HTTP_URL=
# Example: BEACON_HTTP_URL=http://172.17.0.1:5052
```

- [ ] **Step 4: Commit**

```bash
git add backend/dune/staking_flows.sql backend/app/core/config.py .env.example
git commit -m "feat(staking): add staking_flows Dune SQL + settings keys"
```

---

## Task 3 — `upsert_staking_flows` service

**Files:**
- Modify: `backend/app/services/flow_sync.py`
- Test: `backend/tests/test_staking_sync.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_staking_sync.py`:

```python
"""Tests for the staking_flows upsert path. Mirrors test_flow_sync conventions."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.models import Base, StakingFlow
from app.services.flow_sync import upsert_staking_flows


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_upsert_staking_flows_round_trip(session):
    rows = [
        {
            "ts_bucket": "2026-05-01 12:00:00.000 UTC",
            "kind": "deposit",
            "amount_eth": 320.0,
            "amount_usd": 1_120_000.0,
        },
        {
            "ts_bucket": "2026-05-01 12:00:00.000 UTC",
            "kind": "withdrawal_full",
            "amount_eth": 64.0,
            "amount_usd": 224_000.0,
        },
    ]
    n = upsert_staking_flows(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(StakingFlow).order_by(StakingFlow.kind)).scalars().all()
    assert {row.kind for row in stored} == {"deposit", "withdrawal_full"}
    assert Decimal(str(stored[0].amount_eth)) == Decimal("320.000000000000000000")


def test_upsert_staking_flows_filters_unknown_kind(session):
    rows = [
        {
            "ts_bucket": "2026-05-01 12:00:00.000 UTC",
            "kind": "deposit",
            "amount_eth": 32.0,
            "amount_usd": 112_000.0,
        },
        {
            "ts_bucket": "2026-05-01 12:00:00.000 UTC",
            "kind": "garbage",  # defensive: should be skipped
            "amount_eth": 1.0,
            "amount_usd": 4000.0,
        },
    ]
    n = upsert_staking_flows(session, rows)
    session.commit()
    assert n == 1


def test_upsert_staking_flows_idempotent(session):
    rows = [
        {
            "ts_bucket": "2026-05-01 12:00:00.000 UTC",
            "kind": "deposit",
            "amount_eth": 32.0,
            "amount_usd": 112_000.0,
        },
    ]
    upsert_staking_flows(session, rows)
    session.commit()
    # Same key, updated value
    rows[0]["amount_eth"] = 64.0
    rows[0]["amount_usd"] = 224_000.0
    upsert_staking_flows(session, rows)
    session.commit()
    stored = session.execute(select(StakingFlow)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].amount_eth)) == Decimal("64.000000000000000000")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && .venv/bin/pytest tests/test_staking_sync.py -v
```

Expected: ImportError: cannot import name 'upsert_staking_flows' from 'app.services.flow_sync'.

- [ ] **Step 3: Implement `upsert_staking_flows`**

In `backend/app/services/flow_sync.py`, near the bottom (after `upsert_volume_buckets`), add:

```python
_STAKING_KINDS = ("deposit", "withdrawal_partial", "withdrawal_full")


def upsert_staking_flows(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, kind). Filters out rows whose kind isn't
    in _STAKING_KINDS as a defensive guard against schema drift on the Dune side.
    """
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "kind": r["kind"],
            "amount_eth": r["amount_eth"],
            "amount_usd": r.get("amount_usd"),
        }
        for r in rows
        if r.get("kind") in _STAKING_KINDS
    ]
    return _upsert_chunked(
        session,
        StakingFlow,
        values,
        index_elements=["ts_bucket", "kind"],
        update_cols=["amount_eth", "amount_usd"],
    )
```

In the same file, add `StakingFlow` to the imports near the top:

```python
from app.core.models import (
    ExchangeFlow,
    OnchainVolume,
    OrderFlow,
    StablecoinFlow,
    StakingFlow,
    VolumeBucket,
)
```

(Sort alphabetically — that's the existing convention.)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_staking_sync.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/flow_sync.py backend/tests/test_staking_sync.py
git commit -m "feat(staking): upsert_staking_flows service + tests"
```

---

## Task 4 — Wire into `sync_dune_flows` cron

**Files:**
- Modify: `backend/app/workers/flow_jobs.py`

- [ ] **Step 1: Add staking_flows to the job list**

In `backend/app/workers/flow_jobs.py`:

1. Update the import to include the new service function:

```python
from app.services.flow_sync import (
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_order_flow,
    upsert_stablecoin_flows,
    upsert_staking_flows,
    upsert_volume_buckets,
)
```

2. Inside `sync_dune_flows`, append one entry to the `jobs` list (after `onchain_volume`):

```python
        jobs = [
            ("exchange_flows", settings.dune_query_id_exchange_flows, upsert_exchange_flows),
            ("stablecoin_flows", settings.dune_query_id_stablecoin_supply, upsert_stablecoin_flows),
            ("onchain_volume", settings.dune_query_id_onchain_volume, upsert_onchain_volume),
            ("staking_flows", settings.dune_query_id_staking_flows, upsert_staking_flows),
        ]
```

The existing skip-on-zero logic already covers the new entry — when `DUNE_QUERY_ID_STAKING_FLOWS=0` (unset), it logs "skipping" and continues without error.

- [ ] **Step 2: Run the existing flow-jobs test suite**

```bash
cd backend && .venv/bin/pytest tests/ -k "flow" -v 2>&1 | tail -10
```

Expected: existing tests still pass; no NEW failures vs. main.

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/flow_jobs.py
git commit -m "feat(staking): wire staking_flows into sync_dune_flows job"
```

---

## Task 5 — Lighthouse beacon-API client

**Files:**
- Create: `backend/app/clients/beacon.py`
- Test: `backend/tests/test_beacon_client.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_beacon_client.py`:

```python
"""Unit tests for the thin Lighthouse beacon-API client."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.beacon import BeaconClient


@pytest.mark.asyncio
async def test_active_validator_count_parses_data_length():
    """Returns len(response['data']) when the call succeeds."""
    fake_data = {"data": [{"index": str(i)} for i in range(5)]}
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json = MagicMock(return_value=fake_data)
    response.raise_for_status = MagicMock()

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake_data))
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        n = await client.active_validator_count()
    assert n == 5


@pytest.mark.asyncio
async def test_active_validator_count_returns_none_on_http_error():
    """Network failure → None (caller hides the tile)."""
    def boom(req):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http)
        n = await client.active_validator_count()
    assert n is None


@pytest.mark.asyncio
async def test_active_validator_count_uses_cache(monkeypatch):
    """Second call within TTL returns cached value without re-hitting the network."""
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"data": [{}, {}, {}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://beacon.test") as http:
        client = BeaconClient(http, cache_ttl_s=300)
        assert await client.active_validator_count() == 3
        assert await client.active_validator_count() == 3
    assert calls["n"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/test_beacon_client.py -v
```

Expected: ModuleNotFoundError: No module named 'app.clients.beacon'.

- [ ] **Step 3: Implement the client**

Create `backend/app/clients/beacon.py`:

```python
"""Thin client over the Lighthouse beacon-node HTTP API.

Only exposes what the dashboard actually consumes. v1 = single endpoint:
active validator count.

Beacon HTTP spec: https://ethereum.github.io/beacon-APIs/
"""
import logging
import time

import httpx

log = logging.getLogger(__name__)


class BeaconClient:
    """Minimal Lighthouse beacon-API client. Caches the validator count
    in-process to avoid the ~1.5MB payload cost on repeat calls."""

    def __init__(self, http: httpx.AsyncClient, *, cache_ttl_s: int = 300) -> None:
        self._http = http
        self._cache_ttl_s = cache_ttl_s
        self._cached_count: int | None = None
        self._cached_at: float = 0.0

    async def active_validator_count(self) -> int | None:
        """Count of validators in 'active_ongoing' state at head.

        Returns None on any error so callers can degrade gracefully.
        """
        now = time.monotonic()
        if self._cached_count is not None and (now - self._cached_at) < self._cache_ttl_s:
            return self._cached_count
        try:
            resp = await self._http.get(
                "/eth/v1/beacon/states/head/validators",
                params={"status": "active_ongoing"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            count = len(data)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("beacon validator count failed: %s", e)
            return None
        self._cached_count = count
        self._cached_at = now
        return count
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/test_beacon_client.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/beacon.py backend/tests/test_beacon_client.py
git commit -m "feat(staking): Lighthouse beacon-API client (active validator count)"
```

---

## Task 6 — API schemas & route

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/api/staking.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Add response schemas**

In `backend/app/api/schemas.py`, after the existing `VolumeBucketsResponse` (or other flow-shaped response models — find by greppingfor `OnchainVolumeResponse`), add:

```python
class StakingFlowPoint(BaseModel):
    ts_bucket: datetime
    kind: Literal["deposit", "withdrawal_partial", "withdrawal_full"]
    amount_eth: float
    amount_usd: float | None


class StakingFlowsResponse(BaseModel):
    points: list[StakingFlowPoint]


class StakingSummary(BaseModel):
    active_validator_count: int | None
    total_eth_staked_30d: float
    net_eth_staked_30d: float
```

If `Literal` and `datetime` aren't already imported at the top of the file, add them.

- [ ] **Step 2: Create the staking router**

Create `backend/app/api/staking.py`:

```python
"""Staking layer endpoints — beacon-chain deposit/withdrawal flows
and a live active-validator-count summary tile."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    StakingFlowPoint,
    StakingFlowsResponse,
    StakingSummary,
)
from app.clients.beacon import BeaconClient
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import StakingFlow

router = APIRouter(prefix="/staking", tags=["staking"])

HoursParam = Annotated[int, Query(ge=1, le=24 * 60, description="look-back window in hours")]


@router.get("/flows", response_model=StakingFlowsResponse)
def staking_flows(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 48,
    limit: int = Query(5000, ge=1, le=20000),
) -> StakingFlowsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(StakingFlow)
        .where(StakingFlow.ts_bucket >= cutoff)
        .order_by(StakingFlow.ts_bucket.desc())
        .limit(limit)
    ).scalars().all()
    return StakingFlowsResponse(
        points=[
            StakingFlowPoint(
                ts_bucket=r.ts_bucket,
                kind=r.kind,
                amount_eth=float(r.amount_eth),
                amount_usd=float(r.amount_usd) if r.amount_usd is not None else None,
            )
            for r in rows
        ]
    )


@router.get("/summary", response_model=StakingSummary)
async def staking_summary(
    session: Annotated[Session, Depends(get_session)],
) -> StakingSummary:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    rows = session.execute(
        select(StakingFlow).where(StakingFlow.ts_bucket >= cutoff)
    ).scalars().all()

    deposits = sum(float(r.amount_eth) for r in rows if r.kind == "deposit")
    full_w = sum(float(r.amount_eth) for r in rows if r.kind == "withdrawal_full")

    settings = get_settings()
    active_count: int | None = None
    if settings.beacon_http_url:
        async with httpx.AsyncClient(base_url=settings.beacon_http_url) as http:
            client = BeaconClient(http)
            active_count = await client.active_validator_count()

    return StakingSummary(
        active_validator_count=active_count,
        total_eth_staked_30d=deposits,
        net_eth_staked_30d=deposits - full_w,
    )
```

- [ ] **Step 3: Register the router**

In `backend/app/api/__init__.py`, find where the existing routers are imported/registered (mirror whatever pattern is there — usually `from app.api import flows` then `app.include_router(flows.router)`). Add:

```python
from app.api import staking
...
app.include_router(staking.router)
```

If the existing file uses a different pattern (e.g. an `api_router = APIRouter()` aggregator), follow that pattern instead — the goal is "staking router is mounted under `/api/staking`".

- [ ] **Step 4: Smoke-test the endpoints**

Restart the API container, then:

```bash
docker compose restart api
sleep 3
curl -s http://localhost:8000/api/staking/flows?hours=24 | head -c 200
curl -s http://localhost:8000/api/staking/summary
```

Expected: `/flows` returns `{"points":[]}` (no data yet, since the Dune query ID isn't set). `/summary` returns `{"active_validator_count": null, "total_eth_staked_30d": 0.0, "net_eth_staked_30d": 0.0}` (or non-null active_count if `BEACON_HTTP_URL` is set).

If either returns 404, the router didn't register — re-check `app/api/__init__.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/staking.py backend/app/api/__init__.py
git commit -m "feat(staking): /api/staking/flows + /api/staking/summary endpoints"
```

---

## Task 7 — Frontend API client + types

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetch functions**

In `frontend/src/api.ts`, after `fetchStablecoinFlows` (or any other flow-shaped fetcher), add:

```typescript
export type StakingFlowKind = "deposit" | "withdrawal_partial" | "withdrawal_full";

export type StakingFlowPoint = {
  ts_bucket: string;
  kind: StakingFlowKind;
  amount_eth: number;
  amount_usd: number | null;
};

export async function fetchStakingFlows(
  hours: number,
  limit = 5000,
): Promise<StakingFlowPoint[]> {
  const r = await apiFetch(`/api/staking/flows?hours=${hours}&limit=${limit}`);
  if (!r.ok) throw new Error(`staking flows ${r.status}`);
  return (await r.json()).points;
}

export type StakingSummary = {
  active_validator_count: number | null;
  total_eth_staked_30d: number;
  net_eth_staked_30d: number;
};

export async function fetchStakingSummary(): Promise<StakingSummary> {
  const r = await apiFetch(`/api/staking/summary`);
  if (!r.ok) throw new Error(`staking summary ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

```bash
cd frontend && npm run build
```

Expected: succeeds (the panel doesn't exist yet, so the new types are unused but not erroring).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(staking): frontend fetchStakingFlows + fetchStakingSummary"
```

---

## Task 8 — `StakingFlowsPanel` React component

**Files:**
- Create: `frontend/src/components/StakingFlowsPanel.tsx`
- Modify: `frontend/src/lib/panelRegistry.ts`

- [ ] **Step 1: Write the panel component**

Create `frontend/src/components/StakingFlowsPanel.tsx`:

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStakingFlows,
  fetchStakingSummary,
  rangeToHours,
  type FlowRange,
  type StakingFlowKind,
  type StakingFlowPoint,
} from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";
import Sparkline from "./Sparkline";

type LegAgg = {
  totalEth: number;
  totalUsd: number;
  hourlyEth: number[];
};

export default function StakingFlowsPanel() {
  const [range, setRange] = useState<FlowRange>("48h");
  const hours = rangeToHours(range);

  const flows = useQuery({
    queryKey: ["staking-flows", hours],
    queryFn: () => fetchStakingFlows(hours),
    refetchInterval: 60_000,
  });
  const summary = useQuery({
    queryKey: ["staking-summary"],
    queryFn: fetchStakingSummary,
    refetchInterval: 5 * 60_000,
  });

  const legs = aggregate(flows.data ?? []);
  const netEth = legs.deposit.totalEth - legs.withdrawal_full.totalEth;
  const maxLeg = Math.max(
    1,
    legs.deposit.totalEth,
    legs.withdrawal_full.totalEth,
  );

  return (
    <Card
      title="Beacon flows"
      subtitle={`last ${range} · staking deposits vs validator exits`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {flows.isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {flows.error && <p className="text-sm text-down">unavailable</p>}
      {!flows.isLoading && !flows.error && (flows.data ?? []).length === 0 && (
        <p className="text-sm text-slate-500">no data yet — waiting for Dune sync</p>
      )}
      {(flows.data ?? []).length > 0 && (
        <div className="space-y-3">
          <div className="flex justify-between items-baseline @xs:flex-col @xs:gap-1">
            <span className="text-xs text-slate-500">
              {summary.data?.active_validator_count != null
                ? `${summary.data.active_validator_count.toLocaleString()} active validators`
                : "active validators —"}
            </span>
            <span
              className={
                "text-sm font-mono tabular-nums " +
                (netEth >= 0 ? "text-up" : "text-down")
              }
            >
              net {netEth >= 0 ? "+" : ""}
              {netEth.toLocaleString(undefined, { maximumFractionDigits: 0 })} ETH
            </span>
          </div>

          <LegRow
            label="Deposits"
            tone="up"
            leg={legs.deposit}
            maxLeg={maxLeg}
          />
          <LegRow
            label="Full exits"
            tone="down"
            leg={legs.withdrawal_full}
            maxLeg={maxLeg}
          />

          <div className="text-[11px] text-slate-500 font-mono tabular-nums @xs:hidden border-t border-surface-raised pt-2">
            rewards skim (partial withdrawals):{" "}
            {legs.withdrawal_partial.totalEth.toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })}{" "}
            ETH (
            {formatUsdCompact(legs.withdrawal_partial.totalUsd)})
          </div>
        </div>
      )}
    </Card>
  );
}

function LegRow({
  label,
  tone,
  leg,
  maxLeg,
}: {
  label: string;
  tone: "up" | "down";
  leg: LegAgg;
  maxLeg: number;
}) {
  const pct = (leg.totalEth / maxLeg) * 100;
  return (
    <div className="text-sm">
      <div className="flex justify-between mb-1">
        <span className="text-slate-200">{label}</span>
        <span
          className={
            "font-mono tabular-nums " + (tone === "up" ? "text-up" : "text-down")
          }
        >
          {tone === "up" ? "+" : "−"}
          {leg.totalEth.toLocaleString(undefined, { maximumFractionDigits: 0 })}{" "}
          ETH
          {leg.totalUsd > 0 && (
            <span className="text-slate-500">
              {" "}
              ({formatUsdCompact(leg.totalUsd)})
            </span>
          )}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-surface-raised overflow-hidden">
          <div
            className={
              "h-full rounded-full " +
              (tone === "up" ? "bg-up/80" : "bg-down/80")
            }
            style={{ width: `${pct}%` }}
          />
        </div>
        <Sparkline values={leg.hourlyEth} color={tone} width={80} height={20} />
      </div>
    </div>
  );
}

function aggregate(points: StakingFlowPoint[]): Record<StakingFlowKind, LegAgg> {
  const blank: LegAgg = { totalEth: 0, totalUsd: 0, hourlyEth: [] };
  const result: Record<StakingFlowKind, LegAgg> = {
    deposit: { ...blank, hourlyEth: [] },
    withdrawal_partial: { ...blank, hourlyEth: [] },
    withdrawal_full: { ...blank, hourlyEth: [] },
  };
  const hourlyMap: Record<StakingFlowKind, Map<string, number>> = {
    deposit: new Map(),
    withdrawal_partial: new Map(),
    withdrawal_full: new Map(),
  };
  for (const p of points) {
    result[p.kind].totalEth += p.amount_eth;
    result[p.kind].totalUsd += p.amount_usd ?? 0;
    const m = hourlyMap[p.kind];
    m.set(p.ts_bucket, (m.get(p.ts_bucket) ?? 0) + p.amount_eth);
  }
  for (const k of Object.keys(hourlyMap) as StakingFlowKind[]) {
    const sorted = [...hourlyMap[k].entries()].sort((a, b) =>
      a[0].localeCompare(b[0]),
    );
    result[k].hourlyEth = sorted.map(([, v]) => v);
  }
  return result;
}
```

- [ ] **Step 2: Register the panel**

In `frontend/src/lib/panelRegistry.ts`:

1. Add the import (alphabetically grouped with the other panel imports):

```typescript
import StakingFlowsPanel from "../components/StakingFlowsPanel";
```

2. Add the panel definition to the `PANELS` array, on the "onchain" page:

```typescript
  { id: "staking-flows", label: "Beacon flows", component: StakingFlowsPanel, defaultPage: "onchain", defaultWidth: 1 },
```

(Place it next to `stablecoin-supply` so the on-chain page reads naturally.)

- [ ] **Step 3: Build the frontend**

```bash
cd frontend && npm run build
```

Expected: succeeds. No new chunks-size warnings beyond the existing 500kB threshold notice.

- [ ] **Step 4: Visual smoke check**

```bash
cd /Users/zianvalles/Projects/Eth && docker compose restart frontend
```

Open `http://localhost:5173`, navigate to the Onchain page, confirm:
- Beacon flows panel renders (will say "no data yet" until the Dune query is configured)
- No console errors
- Resizing the panel to S/M/L works (drag handle from PR #16)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StakingFlowsPanel.tsx frontend/src/lib/panelRegistry.ts
git commit -m "feat(staking): StakingFlowsPanel React component + registry entry"
```

---

## Task 9 — CLAUDE.md milestone update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the v3-staking milestone line**

In `CLAUDE.md`, find the `## v2 status` block and the `**v2 complete.**` line that closes it. Immediately after that line, add:

```markdown
## v3 status

- v3-staking ⚠️ ETH staking flows — Dune `staking_ethereum.flows` spell aggregates beacon-chain deposits + partial-withdrawal rewards + full validator exits hourly into `staking_flows`; `/api/staking/flows` and `/api/staking/summary` endpoints; `StakingFlowsPanel` renders divergent leg bars + sparklines + active-validator-count tile (when `BEACON_HTTP_URL` set). Requires `DUNE_QUERY_ID_STAKING_FLOWS` in `.env` (SQL at `backend/dune/staking_flows.sql`); `BEACON_HTTP_URL=http://172.17.0.1:5052` enables the live tile (Lighthouse default port). Spec: `docs/superpowers/specs/2026-05-02-eth-staking-flows-design.md`. (LST market share is a follow-up sub-project.)
```

(Use ⚠️ until the Dune query ID is configured and the first sync has populated the table; flip to ✅ in a follow-up commit once verified end-to-end.)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(staking): add v3-staking milestone line to CLAUDE.md"
```

---

## Task 10 — Backend test sweep

- [ ] **Step 1: Run the full backend suite**

```bash
cd backend && .venv/bin/pytest -q 2>&1 | tail -20
```

Expected: all of `test_staking_sync` (3) and `test_beacon_client` (3) pass. No NEW failures vs. main. Pre-existing failures (e.g. `test_flows_api` that need a real Postgres) persist.

- [ ] **Step 2: Run the new tests in isolation to confirm**

```bash
cd backend && .venv/bin/pytest tests/test_staking_sync.py tests/test_beacon_client.py -v
```

Expected: 6 passed.

- [ ] **Step 3: Run the frontend build once more**

```bash
cd frontend && npm run build
```

Expected: succeeds.

- [ ] **Step 4: No-op commit gate**

If any of the above failed, fix the root cause and create a NEW commit (do not amend). If they all passed, no commit needed for this task.

---

## Task 11 — Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/eth-staking-flows
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "feat(staking): ETH staking flows — beacon deposits + withdrawals + active validator count" --body "$(cat <<'EOF'
## Summary
First v3 sub-project. Adds a Beacon Flows panel:
- Net ETH staked (deposits − full validator exits) over the selected range
- Partial-withdrawal rewards skim shown separately (it's income, not de-staking)
- Live active-validator count tile (Lighthouse beacon API, optional via \`BEACON_HTTP_URL\`)

Sourced from Dune's curated \`staking_ethereum.flows\` spell — one table covers all three flow legs.

Spec: \`docs/superpowers/specs/2026-05-02-eth-staking-flows-design.md\`.

## Files
**Backend**
- new: alembic 0009 — \`staking_flows\` table
- new: \`backend/dune/staking_flows.sql\`
- new: \`backend/app/clients/beacon.py\` — Lighthouse beacon-API client
- new: \`backend/app/api/staking.py\` — \`/api/staking/{flows,summary}\`
- mod: \`models.py\`, \`flow_sync.py\`, \`flow_jobs.py\`, \`config.py\`, \`schemas.py\`, \`api/__init__.py\`

**Frontend**
- new: \`StakingFlowsPanel.tsx\` — divergent legs + sparklines + validator-count tile
- mod: \`api.ts\`, \`panelRegistry.ts\`

**Config**
- \`.env.example\` — \`BEACON_HTTP_URL\`, \`DUNE_QUERY_ID_STAKING_FLOWS\`
- \`CLAUDE.md\` — v3-staking milestone

## Test plan
- [x] \`pytest tests/test_staking_sync.py tests/test_beacon_client.py -v\` — 6 passed
- [x] \`npm run build\` — succeeds
- [ ] Post-merge: paste \`backend/dune/staking_flows.sql\` into a new Dune query via MCP, copy the ID into \`.env\` as \`DUNE_QUERY_ID_STAKING_FLOWS\`, run worker sync, verify \`staking_flows\` populates.
- [ ] Post-merge: set \`BEACON_HTTP_URL\` on the prod box, restart api, confirm validator-count tile renders.

## Out of scope (follow-ups)
- LST market share (sub-project B): \`totalSupply()\` reads on stETH/wstETH/rETH/cbETH/sfrxETH/mETH, separate panel
- Per-entity (Lido / Coinbase / Rocket Pool) breakdown
- Validator exit-queue length / clearance ETA

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Merge after self-review**

If the PR diff and the build/test outputs look clean:

```bash
gh pr merge --squash --delete-branch
```

(The local branch deletion may warn if you're on a worktree — run `git worktree remove …` first or just ignore the warning and clean up after.)

- [ ] **Step 4: Sync local main**

```bash
cd /Users/zianvalles/Projects/Eth
git fetch origin
git reset --hard origin/main
```

---

## Task 12 — Live Dune query (controller-side, post-merge)

This step is performed by the controller using the Dune MCP `createDuneQuery` + `updateDuneQuery` tools, **not** by an implementer subagent.

- [ ] **Step 1:** `mcp__dune__createDuneQuery` with the contents of `backend/dune/staking_flows.sql` (set `is_temp=false`, name "Etherscope: staking flows (v3)").
- [ ] **Step 2:** Set the returned `query_id` as `DUNE_QUERY_ID_STAKING_FLOWS=<id>` in `.env`.
- [ ] **Step 3:** Restart the worker:
  ```bash
  docker compose restart worker
  ```
- [ ] **Step 4:** Trigger a sync inline:
  ```bash
  docker compose exec -T worker python -c "
  import asyncio
  from app.workers.flow_jobs import sync_dune_flows
  print(asyncio.run(sync_dune_flows({})))"
  ```
  Expected output includes `'staking_flows': <int>`.
- [ ] **Step 5:** Verify rows landed:
  ```bash
  docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -t -c \"select kind, count(*), round(sum(amount_eth)::numeric, 0) as total_eth from staking_flows group by kind order by count(*) desc;\""
  ```
  Expected: three rows (deposit / withdrawal_partial / withdrawal_full) with non-zero counts.
- [ ] **Step 6:** Flip CLAUDE.md milestone marker from ⚠️ to ✅ in a one-line follow-up commit.

---

## Self-review

**Spec coverage:**
- Net ETH staked + both legs + partial as separate row → Tasks 3, 8 (panel `LegRow` + sub-line).
- Live active-validator count → Tasks 5, 6, 8 (client + summary endpoint + tile).
- Dune query against `staking_ethereum.flows` → Task 2.
- New `staking_flows` table → Task 1.
- 8h cron cadence (no new cron) → Task 4 (added to existing `sync_dune_flows`).
- BEACON_HTTP_URL optional / panel degrades → Task 6 (`if settings.beacon_http_url:` guard).
- Backend tests for upsert + beacon client → Tasks 3, 5.
- LST market share NOT included → out of scope, called out in PR description and CLAUDE.md.
- Operator step (Dune query upload) → Task 12.

**Type consistency:**
- `kind` is `Literal["deposit","withdrawal_partial","withdrawal_full"]` everywhere (model, upsert filter `_STAKING_KINDS`, schema, frontend `StakingFlowKind`, panel `aggregate` keys, CHECK constraint).
- `amount_eth` is `Numeric(38,18)` in DB → `float` at API boundary → `number` in TS. Same as how the existing flow tables go DB → API → frontend.
- `amount_usd` is nullable end-to-end (DB nullable, schema `float | None`, TS `number | null`).
- Settings names: `dune_query_id_staking_flows`, `beacon_http_url` — snake_case, mirrors existing `dune_query_id_*` and `alchemy_*_url` conventions in `config.py`.

**Placeholder scan:** none — every step has runnable code or a runnable command with expected output.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-02-eth-staking-flows.md`.**

Two execution options:

**1. Subagent-Driven (recommended for this plan)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Tasks 1–8 are tightly coupled (model → service → worker → API → frontend) but each has a clean test/build gate, so per-task isolation works well here.

**2. Inline Execution** — I execute the tasks in this session using the executing-plans skill, batched at the natural boundaries (1–4 backend plumbing, 5 client, 6 API, 7–8 frontend, 9–11 polish + PR).

Which approach?
