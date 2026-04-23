# M2 — On-Chain Flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull three flow datasets from Dune Analytics — exchange inflows/outflows (5 major CEXes × ETH + stables), stablecoin net supply change, and stacked on-chain tx volume by asset — sync them on a cron, expose via REST, render three panels on the dashboard.

**Architecture:** `DuneClient` (httpx-async) triggers a query execution, polls for completion, fetches rows. `FlowSyncService` maps rows to three ORM tables (`exchange_flows`, `stablecoin_flows`, `onchain_volume`) using the same `on_conflict_do_update` pattern as M1. A single arq job `sync_dune_flows` runs on a 4-hour cron (tunable — free-tier Dune caps executions at ~500/month). Three REST endpoints serve the panels; three small React components render them.

**Tech Stack:** httpx async Dune REST client, existing M1 infra (arq, FastAPI, SQLAlchemy ORM, Recharts on the frontend for non-candlestick charts).

**Spec reference:** `docs/superpowers/specs/2026-04-23-eth-analytics-dashboard-design.md`

**Confirmed assumptions:**
- Write our own 3 Dune queries (SQL committed to the repo; user saves them in Dune UI and pastes query IDs into `.env`)
- Panels for M2: exchange flows, stablecoin supply change, on-chain tx volume
- 4-hour sync cadence (configurable) to stay within free Dune tier (500 executions/month)
- "Significant change" alerting still deferred to M4

---

## File Structure

```
backend/
├── dune/                                (create) — SQL files to save in Dune UI
│   ├── exchange_flows.sql
│   ├── stablecoin_supply.sql
│   └── onchain_volume.sql
├── app/
│   ├── clients/
│   │   └── dune.py                      (create) — execute / poll / fetch results
│   ├── services/
│   │   └── flow_sync.py                 (create) — map Dune rows → 3 tables
│   ├── workers/
│   │   ├── flow_jobs.py                 (create) — arq job wrapper
│   │   └── arq_settings.py              (modify) — register flow sync cron
│   ├── api/
│   │   ├── flows.py                     (create) — /api/flows/* endpoints
│   │   └── schemas.py                   (modify) — add flow response models
│   └── core/
│       └── config.py                    (modify) — add dune query ID settings
└── tests/
    ├── fixtures/
    │   ├── dune_exchange_flows.json     (create)
    │   ├── dune_stablecoin_supply.json  (create)
    │   └── dune_onchain_volume.json     (create)
    ├── test_dune_client.py              (create)
    ├── test_flow_sync.py                (create)
    └── test_flows_api.py                (create)

frontend/
├── package.json                         (modify) — add recharts
└── src/
    ├── api.ts                           (modify) — add flow fetchers + types
    ├── components/
    │   ├── ExchangeFlowsPanel.tsx       (create)
    │   ├── StablecoinSupplyPanel.tsx    (create)
    │   └── OnchainVolumePanel.tsx       (create)
    └── App.tsx                          (modify) — 2-column grid layout

docs/
└── dune-setup.md                        (create) — how to save the queries
```

---

### Task 1: Config — add Dune query IDs + sync cadence

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env` (user's local; not checked in)
- Modify: `.env.example`

- [ ] **Step 1: Extend `Settings` in `backend/app/core/config.py`**

Append the following fields inside the `Settings` class (keep existing fields):

```python
    dune_query_id_exchange_flows: int = 0
    dune_query_id_stablecoin_supply: int = 0
    dune_query_id_onchain_volume: int = 0

    # Minutes between Dune syncs. Free tier ≈ 500 executions/month total.
    # 3 queries × every 240 min = ~540/month.
    dune_sync_interval_min: int = 240
```

- [ ] **Step 2: Extend `.env.example`**

Replace the `External APIs` block (lines around `DUNE_API_KEY=`) with:

```
# External APIs
ALCHEMY_API_KEY=
DUNE_API_KEY=
ETHERSCAN_API_KEY=
COINGECKO_API_KEY=

# Dune query IDs (create queries from backend/dune/*.sql in the Dune UI and paste IDs here)
DUNE_QUERY_ID_EXCHANGE_FLOWS=0
DUNE_QUERY_ID_STABLECOIN_SUPPLY=0
DUNE_QUERY_ID_ONCHAIN_VOLUME=0
DUNE_SYNC_INTERVAL_MIN=240
```

- [ ] **Step 3: Failing test — extend `backend/tests/test_config.py`**

Append:

```python
def test_settings_dune_query_defaults(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")

    s = Settings(_env_file=None)

    assert s.dune_query_id_exchange_flows == 0
    assert s.dune_sync_interval_min == 240
```

- [ ] **Step 4: Run & commit**

```
cd backend && .venv/bin/pytest tests/test_config.py -v  # expect 2 passed
cd /Users/zianvalles/Projects/Eth
git add backend/app/core/config.py backend/tests/test_config.py .env.example
git commit -m "feat(backend): Dune query IDs + sync cadence in settings"
```

---

### Task 2: Dune SQL queries + setup doc

**Files:**
- Create: `backend/dune/exchange_flows.sql`
- Create: `backend/dune/stablecoin_supply.sql`
- Create: `backend/dune/onchain_volume.sql`
- Create: `docs/dune-setup.md`

- [ ] **Step 1: Write `backend/dune/exchange_flows.sql`**

```sql
-- Exchange netflow per major CEX for ETH + top stables, 1h buckets, last 48h.
-- Result columns: ts_bucket, exchange, direction, asset, usd_value
with labeled as (
  select address, name as exchange
  from dune.defi.cex_evm_addresses
  where chain = 'ethereum'
    and name in ('Binance','Coinbase','Kraken','OKX','Bitfinex')
),
eth_flows as (
  select
    date_trunc('hour', block_time) as ts_bucket,
    case when to_addr.exchange is not null then to_addr.exchange else from_addr.exchange end as exchange,
    case when to_addr.exchange is not null then 'in' else 'out' end as direction,
    'ETH' as asset,
    sum(value_usd) as usd_value
  from ethereum.traces t
    left join labeled to_addr on to_addr.address = t.to
    left join labeled from_addr on from_addr.address = t."from"
  where t.success
    and (to_addr.exchange is not null or from_addr.exchange is not null)
    and t.block_time > now() - interval '48' hour
    and t.value > 0
    and t.tx_success
  group by 1,2,3
),
token_flows as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    case when to_addr.exchange is not null then to_addr.exchange else from_addr.exchange end as exchange,
    case when to_addr.exchange is not null then 'in' else 'out' end as direction,
    tokens.symbol as asset,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
    left join labeled to_addr on to_addr.address = t.to
    left join labeled from_addr on from_addr.address = t."from"
  where (to_addr.exchange is not null or from_addr.exchange is not null)
    and tokens.symbol in ('USDT','USDC','DAI','WETH')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2,3,4
)
select * from eth_flows
union all
select * from token_flows
order by ts_bucket desc
```

- [ ] **Step 2: Write `backend/dune/stablecoin_supply.sql`**

```sql
-- Net supply change (mints - burns) per stablecoin, 1h buckets, last 48h.
-- Result columns: ts_bucket, asset, direction, usd_value
with mints as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    'in' as direction,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where t."from" = 0x0000000000000000000000000000000000000000
    and tokens.symbol in ('USDT','USDC','DAI')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2
),
burns as (
  select
    date_trunc('hour', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    'out' as direction,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where t.to = 0x0000000000000000000000000000000000000000
    and tokens.symbol in ('USDT','USDC','DAI')
    and t.evt_block_time > now() - interval '48' hour
  group by 1,2
)
select * from mints
union all
select * from burns
order by ts_bucket desc
```

- [ ] **Step 3: Write `backend/dune/onchain_volume.sql`**

```sql
-- Daily USD tx volume broken down by asset, last 30 days.
-- Result columns: ts_bucket, asset, tx_count, usd_value
with eth_volume as (
  select
    date_trunc('day', block_time) as ts_bucket,
    'ETH' as asset,
    count(*) as tx_count,
    sum(value_usd) as usd_value
  from ethereum.traces
  where block_time > now() - interval '30' day
    and success
    and value > 0
    and call_type = 'call'
  group by 1
),
token_volume as (
  select
    date_trunc('day', evt_block_time) as ts_bucket,
    tokens.symbol as asset,
    count(*) as tx_count,
    sum(value_usd) as usd_value
  from erc20_ethereum.evt_Transfer t
    join tokens.erc20 tokens on tokens.contract_address = t.contract_address and tokens.blockchain = 'ethereum'
  where tokens.symbol in ('USDT','USDC','DAI','WETH')
    and t.evt_block_time > now() - interval '30' day
  group by 1,2
)
select * from eth_volume
union all
select * from token_volume
order by ts_bucket desc, asset
```

- [ ] **Step 4: Write `docs/dune-setup.md`**

```markdown
# Dune Setup

This project reads 3 queries from Dune Analytics. You need to save them to your Dune account once, then paste the IDs into `.env`.

## Steps

1. Sign in at https://dune.com and go to https://dune.com/queries
2. Click **New Query** → **Spellbook (DuneSQL)** engine
3. For each file under `backend/dune/*.sql`:
   - Paste the SQL into the editor
   - Click **Run** once to verify it executes
   - Click **Save** → give it a name (e.g. "eth-analytics exchange flows")
   - The URL now reads `https://dune.com/queries/<QUERY_ID>/…` — copy the numeric ID
4. Paste the three IDs into `.env`:
   ```
   DUNE_QUERY_ID_EXCHANGE_FLOWS=<id from exchange_flows.sql>
   DUNE_QUERY_ID_STABLECOIN_SUPPLY=<id from stablecoin_supply.sql>
   DUNE_QUERY_ID_ONCHAIN_VOLUME=<id from onchain_volume.sql>
   ```
5. Restart the worker: `docker compose restart worker`

The worker will then begin syncing every `DUNE_SYNC_INTERVAL_MIN` minutes (default 240 = 4 hours).

## Execution quota

Free tier is ~500 executions/month. 3 queries × once per 240 minutes × 30 days ≈ 540/month — right at the limit. Tune `DUNE_SYNC_INTERVAL_MIN` up if you hit the cap, or upgrade to the $49/month Analyst plan (25k executions).
```

- [ ] **Step 5: Commit**

```
git add backend/dune docs/dune-setup.md
git commit -m "docs(dune): 3 flow queries + setup instructions"
```

---

### Task 3: Dune client — execute, poll, fetch results

**Files:**
- Create: `backend/app/clients/dune.py`
- Create: `backend/tests/fixtures/dune_execution_response.json`
- Create: `backend/tests/fixtures/dune_results_exchange_flows.json`
- Create: `backend/tests/test_dune_client.py`

- [ ] **Step 1: Write fixture `backend/tests/fixtures/dune_execution_response.json`**

```json
{"execution_id": "01H6V2ZZABCD1234", "state": "QUERY_STATE_PENDING"}
```

- [ ] **Step 2: Write fixture `backend/tests/fixtures/dune_results_exchange_flows.json`**

```json
{
  "execution_id": "01H6V2ZZABCD1234",
  "query_id": 12345,
  "state": "QUERY_STATE_COMPLETED",
  "result": {
    "rows": [
      {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "in",  "asset": "ETH",  "usd_value": 12000000},
      {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "out", "asset": "ETH",  "usd_value":  8000000},
      {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Coinbase","direction": "in",  "asset": "USDC", "usd_value":  4500000}
    ]
  }
}
```

- [ ] **Step 3: Failing test `backend/tests/test_dune_client.py`**

```python
import json
from pathlib import Path

import httpx
import pytest

from app.clients.dune import DuneClient, DuneExecutionError


FIX = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_execute_and_fetch_returns_rows():
    exec_response = json.loads((FIX / "dune_execution_response.json").read_text())
    results_response = json.loads((FIX / "dune_results_exchange_flows.json").read_text())

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/execute"):
            return httpx.Response(200, json=exec_response)
        if request.method == "GET" and request.url.path.endswith("/status"):
            return httpx.Response(200, json={"state": "QUERY_STATE_COMPLETED"})
        if request.method == "GET" and "/results" in request.url.path:
            return httpx.Response(200, json=results_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        rows = await client.execute_and_fetch(query_id=12345, poll_interval_s=0)

    assert len(rows) == 3
    assert rows[0]["exchange"] == "Binance"
    assert rows[2]["asset"] == "USDC"
    # Must have authenticated via header
    # (mock doesn't track headers easily — verify by a separate test below)


@pytest.mark.asyncio
async def test_execute_sends_api_key_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-dune-api-key") == "test-key"
        return httpx.Response(200, json={"execution_id": "x", "state": "QUERY_STATE_PENDING"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        eid = await client.execute(12345)

    assert eid == "x"


@pytest.mark.asyncio
async def test_execute_and_fetch_raises_on_failure():
    def handler(request):
        if request.url.path.endswith("/execute"):
            return httpx.Response(200, json={"execution_id": "x", "state": "QUERY_STATE_PENDING"})
        return httpx.Response(200, json={"state": "QUERY_STATE_FAILED"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.dune.com") as http:
        client = DuneClient(http, api_key="test-key")
        with pytest.raises(DuneExecutionError):
            await client.execute_and_fetch(12345, poll_interval_s=0)
```

- [ ] **Step 4: Implement `backend/app/clients/dune.py`**

```python
import asyncio
import logging

import httpx

DUNE_BASE_URL = "https://api.dune.com"

log = logging.getLogger(__name__)


class DuneExecutionError(RuntimeError):
    pass


class DuneClient:
    """Thin async wrapper around Dune Analytics REST API."""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._headers = {"X-DUNE-API-KEY": api_key}

    async def execute(self, query_id: int) -> str:
        r = await self._http.post(
            f"/api/v1/query/{query_id}/execute", headers=self._headers
        )
        r.raise_for_status()
        return r.json()["execution_id"]

    async def status(self, execution_id: str) -> str:
        r = await self._http.get(
            f"/api/v1/execution/{execution_id}/status", headers=self._headers
        )
        r.raise_for_status()
        return r.json()["state"]

    async def results(self, execution_id: str) -> list[dict]:
        r = await self._http.get(
            f"/api/v1/execution/{execution_id}/results", headers=self._headers
        )
        r.raise_for_status()
        return r.json()["result"]["rows"]

    async def execute_and_fetch(
        self,
        query_id: int,
        *,
        poll_interval_s: float = 3.0,
        max_wait_s: float = 300.0,
    ) -> list[dict]:
        """Trigger a fresh execution, wait for completion, return rows."""
        execution_id = await self.execute(query_id)
        waited = 0.0
        while waited < max_wait_s:
            state = await self.status(execution_id)
            if state == "QUERY_STATE_COMPLETED":
                return await self.results(execution_id)
            if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"):
                raise DuneExecutionError(f"query {query_id} ended in state {state}")
            await asyncio.sleep(poll_interval_s)
            waited += poll_interval_s
        raise DuneExecutionError(f"query {query_id} timed out after {max_wait_s}s")
```

- [ ] **Step 5: Run + commit**

```
cd backend && .venv/bin/pytest tests/test_dune_client.py -v  # expect 3 passed
cd /Users/zianvalles/Projects/Eth
git add backend/app/clients/dune.py backend/tests/fixtures/dune_*.json backend/tests/test_dune_client.py
git commit -m "feat(backend): Dune API client (execute/poll/fetch)"
```

---

### Task 4: Flow sync service — map rows to 3 tables

**Files:**
- Create: `backend/app/services/flow_sync.py`
- Create: `backend/tests/test_flow_sync.py`

- [ ] **Step 1: Failing test `backend/tests/test_flow_sync.py`**

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow
from app.services.flow_sync import (
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_stablecoin_flows,
)


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(ExchangeFlow).delete()
        s.query(StablecoinFlow).delete()
        s.query(OnchainVolume).delete()
        s.commit()
        yield s


def test_upsert_exchange_flows(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "in",  "asset": "ETH",  "usd_value": 12_000_000},
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "out", "asset": "ETH",  "usd_value":  8_000_000},
    ]
    n = upsert_exchange_flows(session, rows)
    assert n == 2

    # Updating the same keys overwrites.
    rows2 = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "in",  "asset": "ETH",  "usd_value": 15_000_000},
    ]
    upsert_exchange_flows(session, rows2)
    r = session.execute(select(ExchangeFlow).where(ExchangeFlow.direction == "in")).scalar_one()
    assert float(r.usd_value) == 15_000_000


def test_upsert_stablecoin_flows(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "asset": "USDT", "direction": "in",  "usd_value": 340_000_000},
        {"ts_bucket": "2026-04-23T10:00:00Z", "asset": "USDC", "direction": "out", "usd_value":  80_000_000},
    ]
    n = upsert_stablecoin_flows(session, rows)
    assert n == 2
    assert session.query(StablecoinFlow).count() == 2


def test_upsert_onchain_volume(session):
    rows = [
        {"ts_bucket": "2026-04-22T00:00:00Z", "asset": "ETH",  "tx_count": 1_234_567, "usd_value": 4_500_000_000},
        {"ts_bucket": "2026-04-22T00:00:00Z", "asset": "USDT", "tx_count":   900_000, "usd_value": 2_100_000_000},
    ]
    n = upsert_onchain_volume(session, rows)
    assert n == 2
    total = sum(float(r.usd_value) for r in session.execute(select(OnchainVolume)).scalars())
    assert total == 6_600_000_000


def test_upsert_handles_empty_lists(session):
    assert upsert_exchange_flows(session, []) == 0
    assert upsert_stablecoin_flows(session, []) == 0
    assert upsert_onchain_volume(session, []) == 0
```

- [ ] **Step 2: Implement `backend/app/services/flow_sync.py`**

```python
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # Dune returns ISO 8601 with trailing Z; fromisoformat handles it in py3.11+
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def upsert_exchange_flows(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "exchange": r["exchange"],
            "direction": r["direction"],
            "asset": r["asset"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(ExchangeFlow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["exchange", "direction", "asset", "ts_bucket"],
        set_={"usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)


def upsert_stablecoin_flows(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "asset": r["asset"],
            "direction": r["direction"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(StablecoinFlow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "direction", "ts_bucket"],
        set_={"usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)


def upsert_onchain_volume(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        {
            "asset": r["asset"],
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "tx_count": r["tx_count"],
            "usd_value": r["usd_value"],
        }
        for r in rows
    ]
    stmt = pg_insert(OnchainVolume).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset", "ts_bucket"],
        set_={"tx_count": stmt.excluded.tx_count, "usd_value": stmt.excluded.usd_value},
    )
    session.execute(stmt)
    session.commit()
    return len(values)
```

- [ ] **Step 3: Run + commit**

```
cd backend && .venv/bin/pytest tests/test_flow_sync.py -v  # expect 4 passed
cd /Users/zianvalles/Projects/Eth
git add backend/app/services/flow_sync.py backend/tests/test_flow_sync.py
git commit -m "feat(backend): flow_sync upserts for exchange/stablecoin/onchain_volume"
```

---

### Task 5: arq job + register cron

**Files:**
- Create: `backend/app/workers/flow_jobs.py`
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Write `backend/app/workers/flow_jobs.py`**

```python
"""arq task entrypoints for Dune flow sync."""
import logging

import httpx

from app.clients.dune import DUNE_BASE_URL, DuneClient, DuneExecutionError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services.flow_sync import (
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_stablecoin_flows,
)

log = logging.getLogger(__name__)


async def sync_dune_flows(ctx: dict) -> dict:
    """Execute and fetch all 3 Dune queries, upsert into their respective tables.

    Skips any query whose ID is 0 (not configured). Logs execution errors but continues
    so one broken query doesn't halt the rest.
    """
    settings = get_settings()
    if not settings.dune_api_key:
        log.warning("DUNE_API_KEY not set — skipping flow sync")
        return {"skipped": "no api key"}

    SessionLocal = get_sessionmaker()
    results: dict[str, int | str] = {}

    async with httpx.AsyncClient(base_url=DUNE_BASE_URL, timeout=300.0) as http:
        client = DuneClient(http, api_key=settings.dune_api_key)

        jobs = [
            ("exchange_flows", settings.dune_query_id_exchange_flows, upsert_exchange_flows),
            ("stablecoin_flows", settings.dune_query_id_stablecoin_supply, upsert_stablecoin_flows),
            ("onchain_volume", settings.dune_query_id_onchain_volume, upsert_onchain_volume),
        ]

        for name, query_id, upsert_fn in jobs:
            if query_id == 0:
                log.info("skipping %s: query ID not configured", name)
                results[name] = "not configured"
                continue
            try:
                rows = await client.execute_and_fetch(query_id)
            except (DuneExecutionError, httpx.HTTPError) as e:
                log.error("dune sync %s failed: %s", name, e)
                results[name] = f"error: {e}"
                continue
            with SessionLocal() as session:
                n = upsert_fn(session, rows)
            log.info("synced %s: %d rows", name, n)
            results[name] = n

    return results
```

- [ ] **Step 2: Modify `backend/app/workers/arq_settings.py`**

Replace the entire file with:

```python
import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from app.clients.binance import BINANCE_BASE_URL
from app.core.config import get_settings
from app.workers.flow_jobs import sync_dune_flows
from app.workers.price_jobs import backfill_price_history, sync_price_latest


async def startup(ctx: dict) -> None:
    ctx["http"] = httpx.AsyncClient(base_url=BINANCE_BASE_URL, timeout=15.0)
    await ctx["redis"].enqueue_job("backfill_price_history")
    # Also trigger an initial flow sync on startup (skipped internally if unconfigured).
    await ctx["redis"].enqueue_job("sync_dune_flows")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()


_settings = get_settings()
_dune_minute_bitmap = set(range(0, 60, max(1, min(59, _settings.dune_sync_interval_min % 60)))) or {0}
# For intervals ≥ 60 min, run at minute=0 of each matching hour instead.


def _dune_cron_kwargs() -> dict:
    interval = _settings.dune_sync_interval_min
    if interval < 60:
        return {"minute": set(range(0, 60, max(1, interval)))}
    # run at minute 0 of matching hours
    hours = set(range(0, 24, max(1, interval // 60)))
    return {"minute": {0}, "hour": hours}


class WorkerSettings:
    functions = [backfill_price_history, sync_price_latest, sync_dune_flows]
    cron_jobs = [
        cron(sync_price_latest, minute=set(range(0, 60)), run_at_startup=False),
        cron(sync_dune_flows, **_dune_cron_kwargs(), run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
```

- [ ] **Step 3: Verify imports**

```
cd backend && POSTGRES_USER=u POSTGRES_PASSWORD=p POSTGRES_DB=d POSTGRES_HOST=h REDIS_URL=redis://localhost:6379/0 \
  .venv/bin/python -c "from app.workers import arq_settings; print([f.__name__ for f in arq_settings.WorkerSettings.functions]); print('cron_jobs:', len(arq_settings.WorkerSettings.cron_jobs))"
```

Expected:
```
['backfill_price_history', 'sync_price_latest', 'sync_dune_flows']
cron_jobs: 2
```

- [ ] **Step 4: Full pytest**

`cd backend && .venv/bin/pytest -v` → all previous tests still green (~20 passing now).

- [ ] **Step 5: Commit**

```
git add backend/app/workers/flow_jobs.py backend/app/workers/arq_settings.py
git commit -m "feat(backend): arq sync_dune_flows job + cron"
```

---

### Task 6: REST endpoints for the three flow panels

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/api/flows.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_flows_api.py`

- [ ] **Step 1: Append to `backend/app/api/schemas.py`**

```python
from datetime import datetime


class ExchangeFlowPoint(BaseModel):
    ts_bucket: datetime
    exchange: str
    direction: str
    asset: str
    usd_value: float


class ExchangeFlowsResponse(BaseModel):
    points: list[ExchangeFlowPoint]


class StablecoinFlowPoint(BaseModel):
    ts_bucket: datetime
    asset: str
    direction: str
    usd_value: float


class StablecoinFlowsResponse(BaseModel):
    points: list[StablecoinFlowPoint]


class OnchainVolumePoint(BaseModel):
    ts_bucket: datetime
    asset: str
    tx_count: int
    usd_value: float


class OnchainVolumeResponse(BaseModel):
    points: list[OnchainVolumePoint]
```

- [ ] **Step 2: Write `backend/app/api/flows.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ExchangeFlowPoint,
    ExchangeFlowsResponse,
    OnchainVolumePoint,
    OnchainVolumeResponse,
    StablecoinFlowPoint,
    StablecoinFlowsResponse,
)
from app.core.db import get_session
from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("/exchange", response_model=ExchangeFlowsResponse)
def exchange_flows(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> ExchangeFlowsResponse:
    rows = session.execute(
        select(ExchangeFlow).order_by(ExchangeFlow.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        ExchangeFlowPoint(
            ts_bucket=r.ts_bucket,
            exchange=r.exchange,
            direction=r.direction,
            asset=r.asset,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return ExchangeFlowsResponse(points=points)


@router.get("/stablecoins", response_model=StablecoinFlowsResponse)
def stablecoin_flows(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> StablecoinFlowsResponse:
    rows = session.execute(
        select(StablecoinFlow).order_by(StablecoinFlow.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        StablecoinFlowPoint(
            ts_bucket=r.ts_bucket,
            asset=r.asset,
            direction=r.direction,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return StablecoinFlowsResponse(points=points)


@router.get("/onchain-volume", response_model=OnchainVolumeResponse)
def onchain_volume(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(500, ge=1, le=5000),
) -> OnchainVolumeResponse:
    rows = session.execute(
        select(OnchainVolume).order_by(OnchainVolume.ts_bucket.desc()).limit(limit)
    ).scalars().all()
    points = [
        OnchainVolumePoint(
            ts_bucket=r.ts_bucket,
            asset=r.asset,
            tx_count=r.tx_count,
            usd_value=float(r.usd_value),
        )
        for r in reversed(rows)
    ]
    return OnchainVolumeResponse(points=points)
```

- [ ] **Step 3: Register router — modify `backend/app/main.py`**

Replace with:

```python
from fastapi import FastAPI

from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.price import router as price_router

app = FastAPI(title="Eth Analytics API", version="0.1.0")
app.include_router(health_router, prefix="/api")
app.include_router(price_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
```

- [ ] **Step 4: Write `backend/tests/test_flows_api.py`**

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow
from app.main import app


@pytest.fixture
def seeded(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    ts = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
    with Session() as s:
        s.query(ExchangeFlow).delete()
        s.query(StablecoinFlow).delete()
        s.query(OnchainVolume).delete()
        s.add(ExchangeFlow(exchange="Binance", direction="in", asset="ETH", ts_bucket=ts, usd_value=Decimal("12000000")))
        s.add(StablecoinFlow(asset="USDT", direction="in", ts_bucket=ts, usd_value=Decimal("340000000")))
        s.add(OnchainVolume(asset="ETH", ts_bucket=ts, tx_count=1_234_567, usd_value=Decimal("4500000000")))
        s.commit()
        yield s


def test_exchange_endpoint(seeded):
    client = TestClient(app)
    r = client.get("/api/flows/exchange")
    assert r.status_code == 200
    data = r.json()
    assert len(data["points"]) == 1
    assert data["points"][0]["exchange"] == "Binance"


def test_stablecoins_endpoint(seeded):
    client = TestClient(app)
    r = client.get("/api/flows/stablecoins")
    assert r.status_code == 200
    assert r.json()["points"][0]["asset"] == "USDT"


def test_onchain_volume_endpoint(seeded):
    client = TestClient(app)
    r = client.get("/api/flows/onchain-volume")
    assert r.status_code == 200
    assert r.json()["points"][0]["tx_count"] == 1_234_567
```

- [ ] **Step 5: Run + commit**

```
cd backend && .venv/bin/pytest -v  # expect ~23 passed
cd /Users/zianvalles/Projects/Eth
git add backend/app/api/schemas.py backend/app/api/flows.py backend/app/main.py backend/tests/test_flows_api.py
git commit -m "feat(backend): /api/flows/{exchange,stablecoins,onchain-volume} endpoints"
```

---

### Task 7: Frontend — api client additions + 3 panels + grid layout

**Files:**
- Modify: `frontend/package.json` (recharts)
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/ExchangeFlowsPanel.tsx`
- Create: `frontend/src/components/StablecoinSupplyPanel.tsx`
- Create: `frontend/src/components/OnchainVolumePanel.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Install recharts**

```
cd /Users/zianvalles/Projects/Eth/frontend && npm install recharts@^2.15.0
```

- [ ] **Step 2: Append to `frontend/src/api.ts`**

```ts
export type ExchangeFlowPoint = {
  ts_bucket: string;
  exchange: string;
  direction: "in" | "out";
  asset: string;
  usd_value: number;
};

export async function fetchExchangeFlows(limit = 500): Promise<ExchangeFlowPoint[]> {
  const r = await fetch(`/api/flows/exchange?limit=${limit}`);
  if (!r.ok) throw new Error(`exchange flows ${r.status}`);
  return (await r.json()).points;
}

export type StablecoinFlowPoint = {
  ts_bucket: string;
  asset: string;
  direction: "in" | "out";
  usd_value: number;
};

export async function fetchStablecoinFlows(limit = 500): Promise<StablecoinFlowPoint[]> {
  const r = await fetch(`/api/flows/stablecoins?limit=${limit}`);
  if (!r.ok) throw new Error(`stablecoin flows ${r.status}`);
  return (await r.json()).points;
}

export type OnchainVolumePoint = {
  ts_bucket: string;
  asset: string;
  tx_count: number;
  usd_value: number;
};

export async function fetchOnchainVolume(limit = 500): Promise<OnchainVolumePoint[]> {
  const r = await fetch(`/api/flows/onchain-volume?limit=${limit}`);
  if (!r.ok) throw new Error(`onchain volume ${r.status}`);
  return (await r.json()).points;
}
```

- [ ] **Step 3: Write `frontend/src/components/ExchangeFlowsPanel.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchExchangeFlows } from "../api";

function formatUsd(n: number): string {
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(2)}K`;
  return `$${n.toFixed(0)}`;
}

export default function ExchangeFlowsPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["exchange-flows"],
    queryFn: () => fetchExchangeFlows(1000),
    refetchInterval: 60_000,
  });

  const summary: Record<string, number> = {};
  if (data) {
    for (const p of data) {
      const sign = p.direction === "in" ? 1 : -1;
      summary[p.exchange] = (summary[p.exchange] ?? 0) + sign * p.usd_value;
    }
  }
  const sorted = Object.entries(summary).sort((a, b) => b[1] - a[1]);

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="text-lg font-semibold mb-3">Exchange netflows (48h)</h2>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && sorted.length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      <ul className="space-y-2">
        {sorted.map(([exchange, net]) => (
          <li key={exchange} className="flex justify-between text-sm">
            <span className="text-neutral-300">{exchange}</span>
            <span className={net >= 0 ? "text-emerald-400" : "text-red-400"}>
              {net >= 0 ? "+" : ""}
              {formatUsd(net)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/StablecoinSupplyPanel.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchStablecoinFlows } from "../api";

function formatUsd(n: number): string {
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(0)}`;
}

export default function StablecoinSupplyPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stablecoin-flows"],
    queryFn: () => fetchStablecoinFlows(500),
    refetchInterval: 60_000,
  });

  const net: Record<string, number> = {};
  if (data) {
    for (const p of data) {
      const sign = p.direction === "in" ? 1 : -1;
      net[p.asset] = (net[p.asset] ?? 0) + sign * p.usd_value;
    }
  }

  const max = Math.max(1, ...Object.values(net).map((v) => Math.abs(v)));

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="text-lg font-semibold mb-3">Stablecoin supply change (48h)</h2>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && Object.keys(net).length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      <ul className="space-y-2">
        {Object.entries(net).map(([asset, delta]) => {
          const pct = (Math.abs(delta) / max) * 100;
          return (
            <li key={asset} className="text-sm">
              <div className="flex justify-between mb-1">
                <span className="text-neutral-300">{asset}</span>
                <span className={delta >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {delta >= 0 ? "+" : ""}
                  {formatUsd(delta)}
                </span>
              </div>
              <div className="h-1.5 rounded bg-neutral-800 overflow-hidden">
                <div
                  className={delta >= 0 ? "bg-emerald-500 h-full" : "bg-red-500 h-full"}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/OnchainVolumePanel.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchOnchainVolume } from "../api";

const ASSETS = ["ETH", "USDT", "USDC", "DAI", "WETH"] as const;
const COLORS: Record<string, string> = {
  ETH: "#10b981",
  USDT: "#06b6d4",
  USDC: "#3b82f6",
  DAI: "#f59e0b",
  WETH: "#a855f7",
};

type Row = Record<string, number | string>;

export default function OnchainVolumePanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["onchain-volume"],
    queryFn: () => fetchOnchainVolume(500),
    refetchInterval: 60_000,
  });

  const pivot: Row[] = [];
  if (data) {
    const byDay = new Map<string, Row>();
    for (const p of data) {
      const day = p.ts_bucket.slice(0, 10);
      const existing = byDay.get(day) ?? { day };
      existing[p.asset] = p.usd_value;
      byDay.set(day, existing);
    }
    pivot.push(...Array.from(byDay.values()).sort((a, b) => String(a.day).localeCompare(String(b.day))));
  }

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="text-lg font-semibold mb-3">On-chain tx volume (30d, USD)</h2>
      {isLoading && <p className="text-sm text-neutral-500">loading…</p>}
      {error && <p className="text-sm text-red-400">unavailable</p>}
      {!isLoading && !error && pivot.length === 0 && (
        <p className="text-sm text-neutral-500">no data yet — waiting for Dune sync</p>
      )}
      {pivot.length > 0 && (
        <div className="h-64">
          <ResponsiveContainer>
            <AreaChart data={pivot}>
              <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#737373" tick={{ fontSize: 11 }} />
              <YAxis
                stroke="#737373"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => (v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : `${(v / 1e6).toFixed(0)}M`)}
              />
              <Tooltip
                contentStyle={{ background: "#0a0a0a", border: "1px solid #262626" }}
              />
              {ASSETS.map((a) => (
                <Area
                  key={a}
                  type="monotone"
                  dataKey={a}
                  stackId="1"
                  stroke={COLORS[a]}
                  fill={COLORS[a]}
                  fillOpacity={0.35}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Replace `frontend/src/App.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth, type Timeframe } from "./api";
import ExchangeFlowsPanel from "./components/ExchangeFlowsPanel";
import OnchainVolumePanel from "./components/OnchainVolumePanel";
import PriceChart from "./components/PriceChart";
import StablecoinSupplyPanel from "./components/StablecoinSupplyPanel";
import TimeframeSelector from "./components/TimeframeSelector";

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="min-h-screen p-8 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Eth Analytics</h1>
        {health && (
          <span className="text-xs text-neutral-500">
            api: {health.status} (v{health.version})
          </span>
        )}
      </header>
      <div className="flex items-center gap-4">
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PriceChart timeframe={timeframe} />
        </div>
        <div className="space-y-6">
          <ExchangeFlowsPanel />
          <StablecoinSupplyPanel />
        </div>
      </div>
      <OnchainVolumePanel />
    </main>
  );
}
```

- [ ] **Step 7: Build**

```
cd /Users/zianvalles/Projects/Eth/frontend && npm run build 2>&1 | tail -8
```

Expected: successful build.

- [ ] **Step 8: Commit**

```
git add frontend/package.json frontend/package-lock.json frontend/src/api.ts frontend/src/components frontend/src/App.tsx
git commit -m "feat(frontend): 3 flow panels + grid layout"
```

---

### Task 8: End-to-end smoke test + CLAUDE.md + PR prep

**Files:** only docs.

- [ ] **Step 1: Setup Dune queries in UI (MANUAL — user does this step)**

This step requires a human. Instruct the controller to pause and ask the user to:
1. Follow `docs/dune-setup.md`
2. Paste the 3 query IDs into `.env`

If user says "defer Dune setup", record that as a known-empty-data exit state (panels show "no data yet") and proceed.

- [ ] **Step 2: Bring up stack**

```
cd /Users/zianvalles/Projects/Eth
docker compose down
docker compose up --build -d
```

- [ ] **Step 3: Wait for worker to start and trigger flow sync**

```
sleep 15
docker compose logs worker --tail=30 | grep -iE "(sync_dune|flow)"
```

If Dune query IDs are set, expect lines like `synced exchange_flows: N rows`.
If unset, expect `skipping exchange_flows: query ID not configured`.

- [ ] **Step 4: Hit endpoints**

```
for e in exchange stablecoins onchain-volume; do
  echo "--- /api/flows/$e ---"
  curl -s "http://localhost:8000/api/flows/$e" | python3 -c "import sys,json; d=json.load(sys.stdin); print('points:', len(d['points']))"
done
```

- [ ] **Step 5: Visual check at http://localhost:5173**

Expect the 2-column layout, chart spanning left 2 cols, 2 small flow panels stacked on the right, full-width tx-volume area chart below. If Dune has data: numbers + colored bars + stacked area. If not: "no data yet" state in each panel.

- [ ] **Step 6: Shut down + update CLAUDE.md**

```
docker compose down
```

Append to the Milestone status section of `CLAUDE.md`:

```markdown
- M2 ✅ on-chain flows (3 Dune queries → exchange/stablecoin/onchain-volume panels)
```

- [ ] **Step 7: Commit + push**

```
git add CLAUDE.md
git commit -m "docs: mark M2 complete"
git push -u origin feature/m2-onchain-flows
```

Open PR via browser: https://github.com/Miraku17/eth-dashboard/pull/new/feature/m2-onchain-flows

---

## Exit criteria for M2

- `docker compose up` brings up stack cleanly
- `curl /api/flows/exchange`, `/stablecoins`, `/onchain-volume` all 200
- If Dune IDs set: worker logs show `synced exchange_flows: N rows` and panels render data
- If Dune IDs not set: panels show "no data yet — waiting for Dune sync" gracefully
- `pytest -v` passes (~23 tests, +10 for M2)
- Branch pushed + PR opened

## Next plan

After M2 merges, write `docs/superpowers/plans/<date>-m3-whale-tracking.md`: Alchemy WebSocket listener, watched-wallets CRUD, live transfer feed, frontend watchlist + whale-transfer panel.
