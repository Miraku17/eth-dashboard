# DeFi Protocol TVL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `DefiTvlPanel` showing per-protocol per-asset locked TVL on Ethereum mainnet for 10 major DeFi protocols (Aave v3, Sky, Morpho, Compound v2/v3, Spark, Lido, EigenLayer, Pendle, Uniswap v3), driven by an hourly arq cron against the free DefiLlama public API.

**Architecture:** New `protocol_tvl` table fed by an hourly arq cron `sync_defi_tvl` that fan-outs HTTP calls to DefiLlama's `/protocol/{slug}` endpoint and parses `chainTvls.Ethereum.tokensInUsd[-1]`. Two new endpoints under `/api/defi/*` (raw points + pre-aggregated latest). Frontend panel uses the shadcn Select for protocol picking and renders horizontal bars per asset.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy, alembic, arq, httpx), Postgres 16, Redis 7, React + Vite + TypeScript + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-05-02-defi-protocol-tvl-design.md`.

**File map:**
- Create: `backend/alembic/versions/0011_protocol_tvl.py`
- Create: `backend/app/services/defi_protocols.py` — DEFI_PROTOCOLS registry tuple
- Create: `backend/app/clients/defillama.py` — async DefiLlama API client
- Create: `backend/app/services/defi_tvl_sync.py` — `upsert_protocol_tvl`
- Create: `backend/app/workers/defi_jobs.py` — `sync_defi_tvl` arq task
- Create: `backend/app/api/defi.py` — `/api/defi/tvl` + `/api/defi/tvl/latest` router
- Create: `backend/tests/test_defillama_client.py`, `test_defi_tvl_sync.py`, `test_defi_jobs.py`
- Create: `frontend/src/components/DefiTvlPanel.tsx`
- Modify: `backend/app/core/models.py` — add `ProtocolTvl`
- Modify: `backend/app/api/schemas.py` — add 4 response models
- Modify: `backend/app/main.py` — register defi router
- Modify: `backend/app/workers/arq_settings.py` — register sync_defi_tvl cron at minute 17
- Modify: `frontend/src/api.ts` — types + fetchDefiTvlLatest
- Modify: `frontend/src/lib/panelRegistry.ts` — register the panel
- Modify: `CLAUDE.md` — add v3-defi-tvl milestone line

---

## Task 1 — Database table + ORM model

**Files:**
- Create: `backend/alembic/versions/0011_protocol_tvl.py`
- Modify: `backend/app/core/models.py`

- [ ] **Step 1: Write the migration**

Create `backend/alembic/versions/0011_protocol_tvl.py`:

```python
"""protocol tvl

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_tvl",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("protocol", sa.String(32), primary_key=True),
        sa.Column("asset", sa.String(20), primary_key=True),
        sa.Column("tvl_usd", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("protocol_tvl")
```

- [ ] **Step 2: Add the ORM class**

In `backend/app/core/models.py`, after the existing `LstSupply` class, add:

```python
class ProtocolTvl(Base):
    """Hourly per-protocol per-asset locked TVL snapshot on Ethereum mainnet.
    Source: DefiLlama public API. (v3-defi-tvl)"""
    __tablename__ = "protocol_tvl"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset: Mapped[str] = mapped_column(String(20), primary_key=True)
    tvl_usd: Mapped[float] = mapped_column(Numeric(38, 6))
```

- [ ] **Step 3: Run the migration**

Use the same `docker cp` workaround as the prior migrations (the api container's alembic versions dir is `/app/alembic/versions/` — verified during PR #27 / sub-project A's Task 1):

```bash
docker cp /Users/zianvalles/Projects/Eth-defi/backend/alembic/versions/0011_protocol_tvl.py eth-api-1:/app/alembic/versions/0011_protocol_tvl.py
docker compose -f /Users/zianvalles/Projects/Eth/docker-compose.yml exec -T api alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 0010 -> 0011, protocol tvl`.

Verify:
```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '\\d protocol_tvl'"
```

Expected: 4 columns (`ts_bucket`, `protocol`, `asset`, `tvl_usd`) with PK on the first three.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0011_protocol_tvl.py backend/app/core/models.py
git commit -m "feat(defi): add protocol_tvl table + ProtocolTvl model"
```

---

## Task 2 — DEFI_PROTOCOLS registry

**Files:**
- Create: `backend/app/services/defi_protocols.py`

- [ ] **Step 1: Create the registry**

Write `backend/app/services/defi_protocols.py`:

```python
"""DeFi protocol registry. Single source of truth for the TVL cron + panel.

Each entry has a stable `slug` (matches DefiLlama's protocol slug used in
GET /protocol/{slug}) and a human-readable `display_name` used in the
panel's protocol picker.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DefiProtocol:
    slug: str          # DefiLlama slug, lowercase-kebab
    display_name: str  # shown in the panel picker


# 10 protocols on Ethereum mainnet. Slugs verified against
# https://api.llama.fi/v2/protocols on 2026-05-02.
DEFI_PROTOCOLS: tuple[DefiProtocol, ...] = (
    DefiProtocol("aave-v3",      "Aave v3"),
    DefiProtocol("sky-lending",  "Sky (Lending)"),
    DefiProtocol("morpho",       "Morpho"),
    DefiProtocol("compound-v3",  "Compound v3"),
    DefiProtocol("compound-v2",  "Compound v2"),
    DefiProtocol("spark",        "Spark"),
    DefiProtocol("lido",         "Lido"),
    DefiProtocol("eigenlayer",   "EigenLayer"),
    DefiProtocol("pendle",       "Pendle"),
    DefiProtocol("uniswap-v3",   "Uniswap v3"),
)

DEFI_PROTOCOLS_BY_SLUG: dict[str, DefiProtocol] = {p.slug: p for p in DEFI_PROTOCOLS}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/defi_protocols.py
git commit -m "feat(defi): DeFi protocol registry (10 mainnet protocols)"
```

---

## Task 3 — DefiLlama client + tests

**Files:**
- Create: `backend/app/clients/defillama.py`
- Create: `backend/tests/test_defillama_client.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_defillama_client.py`:

```python
"""Unit tests for the DefiLlama public-API client. Mock httpx via MockTransport."""
import httpx
import pytest

from app.clients.defillama import DefiLlamaClient


def _fake_protocol_response(token_breakdown: dict[str, float] | None) -> dict:
    """Build a minimal /protocol/{slug} response shape DefiLlama returns."""
    chain_tvls = {}
    if token_breakdown is not None:
        chain_tvls["Ethereum"] = {
            "tokensInUsd": [
                # earlier daily snapshot (ignored)
                {"date": 1714540800, "tokens": {k: v * 0.9 for k, v in token_breakdown.items()}},
                # latest snapshot (consumed)
                {"date": 1714627200, "tokens": token_breakdown},
            ]
        }
    return {"name": "Test Protocol", "chainTvls": chain_tvls}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_parses_latest_eth_snapshot():
    fake = _fake_protocol_response({"USDC": 4_320_000_000.0, "USDT": 3_100_000_000.0})
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {"USDC": 4_320_000_000.0, "USDT": 3_100_000_000.0}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_returns_empty_on_http_error():
    def boom(req):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {}


@pytest.mark.asyncio
async def test_fetch_protocol_tvl_returns_empty_when_no_ethereum_chain():
    fake = _fake_protocol_response(None)  # no Ethereum entry
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://llama.test") as http:
        client = DefiLlamaClient(http)
        out = await client.fetch_protocol_tvl("aave-v3")
    assert out == {}
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defillama_client.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError: No module named 'app.clients.defillama'.

- [ ] **Step 3: Implement the client**

Create `backend/app/clients/defillama.py`:

```python
"""Thin client over the DefiLlama public API (api.llama.fi).

No auth required. We only consume one endpoint:
    GET /protocol/{slug}  →  {chainTvls: {Ethereum: {tokensInUsd: [...]}}}

The response shape is large; we parse just the latest Ethereum snapshot's
per-token USD breakdown.
"""
import logging

import httpx

DEFILLAMA_BASE_URL = "https://api.llama.fi"

log = logging.getLogger(__name__)


class DefiLlamaClient:
    """Minimal DefiLlama client. One method (per-protocol Ethereum TVL)."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_protocol_tvl(self, slug: str) -> dict[str, float]:
        """Return {asset_symbol: tvl_usd} for the latest Ethereum snapshot.

        Returns {} on any error (network, missing chain, malformed payload).
        Caller skips that protocol's row for this cron tick.
        """
        try:
            resp = await self._http.get(f"/protocol/{slug}", timeout=20.0)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("defillama %s fetch failed: %s", slug, e)
            return {}

        eth = body.get("chainTvls", {}).get("Ethereum")
        if not eth:
            return {}
        timeseries = eth.get("tokensInUsd") or []
        if not timeseries:
            return {}
        latest = timeseries[-1]
        tokens = latest.get("tokens") or {}
        # Defensive: ensure all values are coercible to float.
        out: dict[str, float] = {}
        for sym, val in tokens.items():
            try:
                out[sym] = float(val)
            except (TypeError, ValueError):
                continue
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defillama_client.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/defillama.py backend/tests/test_defillama_client.py
git commit -m "feat(defi): DefiLlama public-API client (per-protocol Ethereum TVL)"
```

---

## Task 4 — `upsert_protocol_tvl` service + tests

**Files:**
- Create: `backend/app/services/defi_tvl_sync.py`
- Create: `backend/tests/test_defi_tvl_sync.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_defi_tvl_sync.py`:

```python
"""Tests for the protocol_tvl upsert path. Uses migrated_engine testcontainer."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import ProtocolTvl
from app.services.defi_tvl_sync import upsert_protocol_tvl


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(ProtocolTvl).delete()
        s.commit()
        yield s


def test_upsert_protocol_tvl_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDC", "tvl_usd": 4_320_000_000.0},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDT", "tvl_usd": 3_100_000_000.0},
    ]
    n = upsert_protocol_tvl(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(ProtocolTvl).order_by(ProtocolTvl.asset)).scalars().all()
    assert {r.asset for r in stored} == {"USDC", "USDT"}


def test_upsert_protocol_tvl_idempotent(session):
    rows = [{"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDC", "tvl_usd": 4_000_000_000.0}]
    upsert_protocol_tvl(session, rows)
    session.commit()
    rows[0]["tvl_usd"] = 4_500_000_000.0
    upsert_protocol_tvl(session, rows)
    session.commit()
    stored = session.execute(select(ProtocolTvl)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].tvl_usd)) == Decimal("4500000000.000000")


def test_upsert_protocol_tvl_multi_protocol_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3",     "asset": "USDC", "tvl_usd": 4e9},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "morpho",      "asset": "USDC", "tvl_usd": 1e9},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "compound-v3", "asset": "USDC", "tvl_usd": 0.6e9},
    ]
    assert upsert_protocol_tvl(session, rows) == 3
    session.commit()
    assert session.query(ProtocolTvl).count() == 3
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defi_tvl_sync.py -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3: Implement the upsert**

Create `backend/app/services/defi_tvl_sync.py`:

```python
"""Upsert path for hourly DefiLlama TVL snapshots. One row per
(ts_bucket, protocol, asset). Postgres on_conflict_do_update for idempotency."""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import ProtocolTvl


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    cleaned = value.replace("Z", "+00:00").replace(" UTC", "+00:00")
    return datetime.fromisoformat(cleaned)


def upsert_protocol_tvl(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, protocol, asset)."""
    if not rows:
        return 0
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "protocol": r["protocol"],
            "asset": r["asset"],
            "tvl_usd": r["tvl_usd"],
        }
        for r in rows
    ]
    stmt = pg_insert(ProtocolTvl).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "protocol", "asset"],
        set_={"tvl_usd": stmt.excluded.tvl_usd},
    )
    session.execute(stmt)
    return len(values)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defi_tvl_sync.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/defi_tvl_sync.py backend/tests/test_defi_tvl_sync.py
git commit -m "feat(defi): upsert_protocol_tvl service + tests"
```

---

## Task 5 — `sync_defi_tvl` arq task + tests

**Files:**
- Create: `backend/app/workers/defi_jobs.py`
- Create: `backend/tests/test_defi_jobs.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_defi_jobs.py`:

```python
"""Tests for the DeFi TVL cron — covers row construction + partial-failure
handling without hitting the real DefiLlama API."""
import pytest

from app.services.defi_protocols import DEFI_PROTOCOLS
from app.workers.defi_jobs import _build_rows


def test_build_rows_pairs_protocol_and_asset():
    """One row per (protocol, asset). Protocols with empty TVL dicts are skipped."""
    fetched = {
        "aave-v3":  {"USDC": 4e9, "USDT": 3e9},
        "morpho":   {"USDC": 1e9},
        "compound-v3": {},  # empty → skipped
    }
    rows = _build_rows(fetched, ts_bucket="2026-05-02T12:00:00Z")
    by_protocol = {(r["protocol"], r["asset"]): r["tvl_usd"] for r in rows}
    assert by_protocol == {
        ("aave-v3", "USDC"): 4e9,
        ("aave-v3", "USDT"): 3e9,
        ("morpho",  "USDC"): 1e9,
    }


def test_build_rows_skips_zero_or_negative():
    """A 0 / negative TVL value is a sign of bad upstream data — skip it."""
    fetched = {"aave-v3": {"USDC": 4e9, "JUNK": 0.0, "BAD": -1.0}}
    rows = _build_rows(fetched, ts_bucket="2026-05-02T12:00:00Z")
    assets = {r["asset"] for r in rows}
    assert assets == {"USDC"}


def test_build_rows_handles_no_data():
    rows = _build_rows({}, ts_bucket="2026-05-02T12:00:00Z")
    assert rows == []


def test_defi_protocols_registry_intact():
    """Defensive: assert the curated registry has all expected slugs."""
    slugs = {p.slug for p in DEFI_PROTOCOLS}
    expected = {"aave-v3", "sky-lending", "morpho", "compound-v3", "compound-v2",
                "spark", "lido", "eigenlayer", "pendle", "uniswap-v3"}
    assert slugs == expected
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defi_jobs.py -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3: Implement the cron**

Create `backend/app/workers/defi_jobs.py`:

```python
"""Hourly cron: snapshot DeFi-protocol TVL on Ethereum mainnet.

Fan-out: one DefiLlama HTTP call per protocol (5 concurrent), parse latest
Ethereum chain TVL per asset, upsert one row per (ts_bucket, protocol, asset).
"""
import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.clients.defillama import DEFILLAMA_BASE_URL, DefiLlamaClient
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.defi_protocols import DEFI_PROTOCOLS
from app.services.defi_tvl_sync import upsert_protocol_tvl

log = logging.getLogger(__name__)

_CONCURRENCY = 5


def _build_rows(fetched: dict[str, dict[str, float]], ts_bucket: str) -> list[dict]:
    """Flatten {protocol: {asset: tvl_usd}} into row dicts. Skips empty
    protocols and non-positive TVL values."""
    rows: list[dict] = []
    for protocol, by_asset in fetched.items():
        if not by_asset:
            continue
        for asset, tvl in by_asset.items():
            if not isinstance(tvl, (int, float)) or tvl <= 0:
                continue
            rows.append(
                {"ts_bucket": ts_bucket, "protocol": protocol, "asset": asset, "tvl_usd": float(tvl)}
            )
    return rows


async def _fetch_one(
    sem: asyncio.Semaphore, client: DefiLlamaClient, slug: str
) -> tuple[str, dict[str, float]]:
    async with sem:
        return slug, await client.fetch_protocol_tvl(slug)


async def sync_defi_tvl(ctx: dict) -> dict:
    """Snapshot DefiLlama TVL for the curated 10-protocol list at top-of-hour."""
    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(
        base_url=DEFILLAMA_BASE_URL,
        headers={"User-Agent": "etherscope/3 (+https://etherscope.duckdns.org)"},
        timeout=20.0,
    ) as http:
        client = DefiLlamaClient(http)
        results = await asyncio.gather(
            *(_fetch_one(sem, client, p.slug) for p in DEFI_PROTOCOLS)
        )

    fetched = dict(results)
    rows = _build_rows(fetched, ts_bucket=ts_bucket)
    if not rows:
        log.warning("defi tvl: no rows after fetch — skipping write")
        return {"protocol_tvl": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_protocol_tvl(session, rows)
        session.commit()

    record_sync_ok("protocol_tvl")
    log.info("synced protocol_tvl: %d rows across %d protocols", n, len(fetched))
    return {"protocol_tvl": n}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest tests/test_defi_jobs.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/defi_jobs.py backend/tests/test_defi_jobs.py
git commit -m "feat(defi): sync_defi_tvl arq task + tests"
```

---

## Task 6 — Wire cron into arq settings

**Files:**
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Register the cron**

In `backend/app/workers/arq_settings.py`:

1. Add import alphabetically with the other worker imports:

```python
from app.workers.defi_jobs import sync_defi_tvl
```

2. Add `sync_defi_tvl` to the `WorkerSettings.functions` tuple, alphabetical:

```python
        sync_defi_tvl,
```

3. Add a `cron(...)` entry to `cron_jobs`. Use minute=17 (LST is on minute 7, derivatives is on minute 5; minute 17 keeps each cron in its own bucket):

```python
        cron(sync_defi_tvl, minute={17}, run_at_startup=False),
```

- [ ] **Step 2: Sanity check**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/python -c "
import ast
with open('app/workers/arq_settings.py') as f:
    ast.parse(f.read())
print('syntax OK')
"
```

Expected: `syntax OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/arq_settings.py
git commit -m "feat(defi): register sync_defi_tvl hourly cron (minute 17)"
```

---

## Task 7 — API schemas + endpoints

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/api/defi.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add response schemas**

In `backend/app/api/schemas.py`, find the existing `LstSupplyResponse` class. Immediately after it, add:

```python
class DefiTvlPoint(BaseModel):
    ts_bucket: datetime
    protocol: str
    asset: str
    tvl_usd: float


class DefiTvlPointsResponse(BaseModel):
    points: list[DefiTvlPoint]


class DefiTvlAsset(BaseModel):
    asset: str
    tvl_usd: float


class DefiTvlProtocolSnapshot(BaseModel):
    protocol: str
    display_name: str
    total_usd: float
    assets: list[DefiTvlAsset]


class DefiTvlLatestResponse(BaseModel):
    ts_bucket: datetime | None
    protocols: list[DefiTvlProtocolSnapshot]
```

- [ ] **Step 2: Create the defi router**

Create `backend/app/api/defi.py`:

```python
"""DeFi protocol TVL endpoints. Reads from protocol_tvl table populated by
the hourly DefiLlama sync."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DefiTvlAsset,
    DefiTvlLatestResponse,
    DefiTvlPoint,
    DefiTvlPointsResponse,
    DefiTvlProtocolSnapshot,
)
from app.core.db import get_session
from app.core.models import ProtocolTvl
from app.services.defi_protocols import DEFI_PROTOCOLS_BY_SLUG

router = APIRouter(prefix="/defi", tags=["defi"])

HoursParam = Annotated[int, Query(ge=1, le=24 * 60, description="look-back window in hours")]


@router.get("/tvl", response_model=DefiTvlPointsResponse)
def defi_tvl(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 168,
    limit: int = Query(20000, ge=1, le=200000),
) -> DefiTvlPointsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(ProtocolTvl)
        .where(ProtocolTvl.ts_bucket >= cutoff)
        .order_by(ProtocolTvl.ts_bucket.asc(), ProtocolTvl.protocol.asc(), ProtocolTvl.asset.asc())
        .limit(limit)
    ).scalars().all()
    return DefiTvlPointsResponse(
        points=[
            DefiTvlPoint(
                ts_bucket=r.ts_bucket,
                protocol=r.protocol,
                asset=r.asset,
                tvl_usd=float(r.tvl_usd),
            )
            for r in rows
        ]
    )


@router.get("/tvl/latest", response_model=DefiTvlLatestResponse)
def defi_tvl_latest(
    session: Annotated[Session, Depends(get_session)],
) -> DefiTvlLatestResponse:
    """Latest hourly snapshot, pre-aggregated per protocol with totals."""
    latest_ts = session.execute(select(ProtocolTvl.ts_bucket).order_by(ProtocolTvl.ts_bucket.desc()).limit(1)).scalar()
    if latest_ts is None:
        return DefiTvlLatestResponse(ts_bucket=None, protocols=[])
    rows = session.execute(
        select(ProtocolTvl).where(ProtocolTvl.ts_bucket == latest_ts)
    ).scalars().all()

    by_protocol: dict[str, list[ProtocolTvl]] = {}
    for r in rows:
        by_protocol.setdefault(r.protocol, []).append(r)

    snapshots: list[DefiTvlProtocolSnapshot] = []
    for slug, prot_rows in by_protocol.items():
        meta = DEFI_PROTOCOLS_BY_SLUG.get(slug)
        display = meta.display_name if meta else slug
        sorted_assets = sorted(prot_rows, key=lambda x: float(x.tvl_usd), reverse=True)
        snapshots.append(
            DefiTvlProtocolSnapshot(
                protocol=slug,
                display_name=display,
                total_usd=float(sum(float(r.tvl_usd) for r in prot_rows)),
                assets=[DefiTvlAsset(asset=r.asset, tvl_usd=float(r.tvl_usd)) for r in sorted_assets],
            )
        )
    snapshots.sort(key=lambda s: s.total_usd, reverse=True)
    return DefiTvlLatestResponse(ts_bucket=latest_ts, protocols=snapshots)
```

- [ ] **Step 3: Register the router in main.py**

In `backend/app/main.py`:

1. Add the import alphabetically with other api imports:

```python
from app.api.defi import router as defi_router
```

2. Register with auth dependency, alongside the other auth-gated routers:

```python
app.include_router(defi_router, prefix="/api", dependencies=[AuthDep])
```

- [ ] **Step 4: Smoke-check imports + routes**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/python -c "
from app.api.defi import router
from app.api.schemas import DefiTvlLatestResponse, DefiTvlProtocolSnapshot
print('imports OK')
print('routes:', [r.path for r in router.routes])
"
```

Expected: `routes: ['/defi/tvl', '/defi/tvl/latest']`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/defi.py backend/app/main.py
git commit -m "feat(defi): /api/defi/tvl + /api/defi/tvl/latest endpoints + schemas"
```

---

## Task 8 — Frontend types + fetcher

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetcher**

In `frontend/src/api.ts`, after the existing `fetchLstSupply` function, add:

```typescript
export type DefiTvlAsset = {
  asset: string;
  tvl_usd: number;
};

export type DefiTvlProtocolSnapshot = {
  protocol: string;
  display_name: string;
  total_usd: number;
  assets: DefiTvlAsset[];
};

export type DefiTvlLatestResponse = {
  ts_bucket: string | null;
  protocols: DefiTvlProtocolSnapshot[];
};

export async function fetchDefiTvlLatest(): Promise<DefiTvlLatestResponse> {
  const r = await apiFetch(`/api/defi/tvl/latest`);
  if (!r.ok) throw new Error(`defi tvl latest ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Verify the build**

```bash
cd /Users/zianvalles/Projects/Eth-defi/frontend && npm run build 2>&1 | tail -8
```

Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(defi): frontend fetchDefiTvlLatest + types"
```

---

## Task 9 — `DefiTvlPanel` React component + registry

**Files:**
- Create: `frontend/src/components/DefiTvlPanel.tsx`
- Modify: `frontend/src/lib/panelRegistry.ts`

- [ ] **Step 1: Create the panel**

Create `frontend/src/components/DefiTvlPanel.tsx`:

```typescript
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDefiTvlLatest, type DefiTvlProtocolSnapshot } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import { SimpleSelect } from "./ui/Select";

const TOP_N_ASSETS = 12;

export default function DefiTvlPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["defi-tvl-latest"],
    queryFn: fetchDefiTvlLatest,
    refetchInterval: 5 * 60_000,
  });

  const protocols = data?.protocols ?? [];
  const [selectedSlug, setSelectedSlug] = useState<string>("");

  // First-render and refetch sync: pick the first (highest-TVL) protocol if
  // the user hasn't picked one yet, or if their pick has dropped out of the
  // current snapshot.
  const effectiveSlug = useMemo(() => {
    if (selectedSlug && protocols.some((p) => p.protocol === selectedSlug)) {
      return selectedSlug;
    }
    return protocols[0]?.protocol ?? "";
  }, [protocols, selectedSlug]);

  const current: DefiTvlProtocolSnapshot | undefined = protocols.find(
    (p) => p.protocol === effectiveSlug,
  );

  const options = protocols.map((p) => ({ value: p.protocol, label: p.display_name }));

  return (
    <Card
      title="DeFi TVL"
      subtitle="Ethereum mainnet · per-protocol locked balances · DefiLlama"
      actions={
        options.length > 0 && (
          <SimpleSelect
            value={effectiveSlug}
            onChange={setSelectedSlug}
            options={options}
            ariaLabel="Select DeFi protocol"
          />
        )
      }
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && protocols.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — first hourly sync pending
        </p>
      )}
      {current && <ProtocolBreakdown snapshot={current} />}
    </Card>
  );
}

function ProtocolBreakdown({ snapshot }: { snapshot: DefiTvlProtocolSnapshot }) {
  const top = snapshot.assets.slice(0, TOP_N_ASSETS);
  const restCount = Math.max(0, snapshot.assets.length - TOP_N_ASSETS);
  const restUsd = snapshot.assets
    .slice(TOP_N_ASSETS)
    .reduce((s, a) => s + a.tvl_usd, 0);
  const max = Math.max(1, ...top.map((a) => a.tvl_usd));

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-slate-300">{snapshot.display_name}</span>
        <span className="font-mono tabular-nums text-base text-slate-100">
          {formatUsdCompact(snapshot.total_usd)} locked
        </span>
      </div>

      <ul className="space-y-2">
        {top.map((a) => {
          const pct = (a.tvl_usd / snapshot.total_usd) * 100;
          const barPct = (a.tvl_usd / max) * 100;
          return (
            <li key={a.asset} className="text-sm">
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-medium">{a.asset}</span>
                <span className="font-mono tabular-nums text-slate-200 @xs:hidden">
                  {formatUsdCompact(a.tvl_usd)}{" "}
                  <span className="text-slate-500">{pct.toFixed(1)}%</span>
                </span>
                <span className="font-mono tabular-nums text-slate-200 hidden @xs:inline">
                  {formatUsdCompact(a.tvl_usd)}
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

      {restCount > 0 && (
        <div className="text-[11px] text-slate-500 font-mono tabular-nums @xs:hidden">
          + {restCount} more assets · {formatUsdCompact(restUsd)} combined
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register the panel**

In `frontend/src/lib/panelRegistry.ts`:

1. Add the import alphabetically:

```typescript
import DefiTvlPanel from "../components/DefiTvlPanel";
```

2. Add a new entry in the `PANELS` array, after the `lst-market-share` entry:

```typescript
  { id: "defi-tvl", label: "DeFi TVL", component: DefiTvlPanel, defaultPage: "onchain", defaultWidth: 2 },
```

- [ ] **Step 3: Build the frontend**

```bash
cd /Users/zianvalles/Projects/Eth-defi/frontend && npm run build 2>&1 | tail -5
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DefiTvlPanel.tsx frontend/src/lib/panelRegistry.ts
git commit -m "feat(defi): DefiTvlPanel React component + registry entry"
```

---

## Task 10 — CLAUDE.md milestone update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the milestone line**

In `CLAUDE.md`, find the existing `v3-lst` line under `## v3 status`. Immediately after it, add:

```markdown
- v3-defi-tvl ⚠️ DeFi protocol TVL — hourly arq cron (`sync_defi_tvl`, minute 17) hits DefiLlama's free public API for 10 protocols (Aave v3, Sky-Lending, Morpho, Compound v2/v3, Spark, Lido, EigenLayer, Pendle, Uniswap v3); persists per-asset Ethereum-mainnet locked balances to `protocol_tvl`; `/api/defi/tvl/latest` endpoint pre-aggregates per-protocol totals; `DefiTvlPanel` renders a protocol picker + per-asset horizontal bar (top 12 assets, "+N more" overflow). No new env var (DefiLlama is unauthenticated). v1 displays raw DefiLlama snapshot, daily granularity. Spec: `docs/superpowers/specs/2026-05-02-defi-protocol-tvl-design.md`.
```

(Use ⚠️ until first sync; flip to ✅ after Task 12 confirms rows landed.)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(defi): add v3-defi-tvl milestone line to CLAUDE.md"
```

---

## Task 11 — Test sweep + push + PR + merge

- [ ] **Step 1: Run full backend suite**

```bash
cd /Users/zianvalles/Projects/Eth-defi/backend && .venv/bin/pytest -q 2>&1 | tail -10
```

Expected: 9 new tests pass (3 client + 3 sync + 3-4 jobs); no NEW failures vs main. Pre-existing `test_flows_api` failures persist.

- [ ] **Step 2: Frontend build**

```bash
cd /Users/zianvalles/Projects/Eth-defi/frontend && npm run build 2>&1 | tail -5
```

Expected: succeeds.

- [ ] **Step 3: Push branch + open PR**

```bash
cd /Users/zianvalles/Projects/Eth-defi && git push -u origin feat/defi-protocol-tvl
gh pr create --title "feat(defi): protocol TVL panel — Aave/Sky/Morpho/Compound/Spark/Lido/EigenLayer/Pendle/Uniswap" --body "$(cat <<'EOF'
## Summary
Per-protocol per-asset locked TVL on Ethereum mainnet, sourced hourly from DefiLlama's free public API. Ten protocols: Aave v3, Sky-Lending, Morpho, Compound v2/v3, Spark, Lido, EigenLayer, Pendle, Uniswap v3.

Answers the operator's question "how much USDC/USDT/DAI/GHO/USDe is locked in Aave / Sky / Morpho right now?" with a single panel.

Spec: \`docs/superpowers/specs/2026-05-02-defi-protocol-tvl-design.md\`.

## Files
**Backend**
- new: alembic 0011 — \`protocol_tvl\` table
- new: \`backend/app/clients/defillama.py\` — async client
- new: \`backend/app/services/defi_protocols.py\` — 10-entry registry
- new: \`backend/app/services/defi_tvl_sync.py\` — upsert
- new: \`backend/app/workers/defi_jobs.py\` — sync_defi_tvl arq task (minute 17)
- new: \`backend/app/api/defi.py\` — /api/defi/tvl + /api/defi/tvl/latest
- mod: \`models.py\`, \`arq_settings.py\`, \`api/schemas.py\`, \`main.py\`

**Frontend**
- new: \`DefiTvlPanel.tsx\` — protocol picker (shadcn Select) + per-asset horizontal bars
- mod: \`api.ts\`, \`panelRegistry.ts\`

**Config**
- \`CLAUDE.md\` — v3-defi-tvl milestone

## Test plan
- [x] backend pytest — 9 new tests pass
- [x] \`npm run build\` — succeeds
- [ ] **Post-merge:** trigger first sync inline, verify ~50–100 rows land across 10 protocols.

## Out of scope (follow-ups)
- Per-asset flow overlay (deposit / withdraw events from \`lending.supply\`)
- Borrow-side / utilization metrics
- DEX LP TVL (Uniswap v3 pools, Balancer, Curve) — different shape
- Per-protocol historical TVL trend (sparkline)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Squash-merge**

```bash
gh pr merge --squash --delete-branch
```

(Local-branch deletion may warn if running from worktree — ignore.)

- [ ] **Step 5: Cleanup worktree, sync local main**

```bash
cd /Users/zianvalles/Projects/Eth
git worktree remove /Users/zianvalles/Projects/Eth-defi --force
git branch -D feat/defi-protocol-tvl || true
git fetch origin && git reset --hard origin/main
```

---

## Task 12 — Trigger first sync, verify, ⚠️→✅

- [ ] **Step 1: Recreate worker container so it picks up the new arq task**

```bash
cd /Users/zianvalles/Projects/Eth && docker compose up -d worker api
```

- [ ] **Step 2: Apply the migration on the running container**

```bash
docker compose exec -T api alembic upgrade head
```

Expected: `Running upgrade 0010 -> 0011`.

- [ ] **Step 3: Trigger the cron inline**

```bash
echo 'import asyncio' > /tmp/defi.py
echo 'from app.workers.defi_jobs import sync_defi_tvl' >> /tmp/defi.py
echo 'print(asyncio.run(sync_defi_tvl({})))' >> /tmp/defi.py
docker compose exec -T worker python < /tmp/defi.py
```

Expected: `{'protocol_tvl': N}` where N is ~50-100 (10 protocols × ~5-10 assets each).

- [ ] **Step 4: Verify rows landed**

```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -t -c \"select protocol, count(*) as assets, round(sum(tvl_usd)::numeric / 1e9, 2) as total_busd from protocol_tvl group by protocol order by total_busd desc;\""
```

Expected: 10 rows (Aave / Sky / Morpho etc.), per-protocol totals in $B range.

- [ ] **Step 5: Flip CLAUDE.md ⚠️→✅**

```bash
sed -i '' 's/v3-defi-tvl ⚠️/v3-defi-tvl ✅/' CLAUDE.md
git add CLAUDE.md
git commit -m "docs(defi): flip v3-defi-tvl ⚠️→✅ — first sync produced rows"
git push origin main
```

---

## Self-review

**Spec coverage:**
- 10 mainnet protocols → Task 2 registry.
- Hourly cron with 5-way concurrent fan-out → Task 5 (`asyncio.Semaphore(5)`).
- DefiLlama client returns {} on errors so partial failures don't crash → Task 3.
- `protocol_tvl` table with composite PK → Task 1.
- Auth-gated endpoints → Task 7.
- Pre-aggregated `/latest` endpoint → Task 7 (`defi_tvl_latest`).
- Protocol picker via shadcn Select → Task 9 (`SimpleSelect` from `ui/Select`).
- Top-12 assets + "+N more" overflow → Task 9.
- Container-query responsive (% column hides at @xs) → Task 9.
- CLAUDE.md → Tasks 10, 12.
- 9 new backend tests → Tasks 3, 4, 5.

**Type consistency:**
- `protocol: str` everywhere (DB, ORM, schema, registry `.slug`, frontend `protocol: string`).
- `asset: str` mirrors `protocol`.
- `tvl_usd` is `Numeric(38,6)` → `float` at API → `number` in TS.
- `display_name` lives only in the registry + endpoint response; frontend uses it as-is.
- Cron name: `sync_defi_tvl` everywhere (worker file, registered fn, log line, sync_status key).

**Placeholder scan:** none — every step has runnable code or a runnable command with expected output.

---

## Execution Handoff

Subagent-Driven (recommended) or Inline. Both work for this 12-task plan.
