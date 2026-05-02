# LST Market Share Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an "LST market share" panel showing 30d stacked-area `totalSupply()` for 7 major liquid-staking tokens (stETH / rETH / cbETH / sfrxETH / mETH / swETH / ETHx), driven by an hourly JSON-RPC batch-call cron against the existing self-hosted Geth node.

**Architecture:** New `lst_supply` table fed by a new arq cron `sync_lst_supply` that issues a single 7-call `eth_call(totalSupply)` batch via the existing `EthRpcClient`. New `/api/staking/lst-supply` endpoint extends the existing `/api/staking/*` router. Frontend renders Recharts stacked area + per-token legend with current share %.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy, alembic, arq, httpx, web3 hex helpers), Postgres 16, Redis 7, React + Vite + TypeScript + Recharts.

**Spec:** `docs/superpowers/specs/2026-05-02-lst-market-share-design.md`.

**File map:**
- Create: `backend/alembic/versions/0010_lst_supply.py` — migration
- Create: `backend/app/services/lst_tokens.py` — LST registry tuple
- Create: `backend/app/services/lst_sync.py` — `upsert_lst_supply` upsert
- Create: `backend/app/workers/lst_jobs.py` — `sync_lst_supply` arq task
- Create: `backend/tests/test_lst_sync.py`
- Create: `backend/tests/test_lst_jobs.py`
- Create: `frontend/src/components/LstMarketSharePanel.tsx`
- Modify: `backend/app/core/models.py` — `LstSupply` ORM class
- Modify: `backend/app/api/schemas.py` — `LstSupplyPoint`, `LstSupplyResponse`
- Modify: `backend/app/api/staking.py` — `GET /lst-supply` endpoint
- Modify: `backend/app/workers/arq_settings.py` — register `sync_lst_supply` cron + import
- Modify: `frontend/src/api.ts` — `LstSupplyPoint` type + `fetchLstSupply`
- Modify: `frontend/src/lib/panelRegistry.ts` — register the new panel
- Modify: `CLAUDE.md` — add v3-lst milestone line

No new env vars (reuses `ALCHEMY_HTTP_URL`).

---

## Task 1 — Database table & ORM model

**Files:**
- Create: `backend/alembic/versions/0010_lst_supply.py`
- Modify: `backend/app/core/models.py`

- [ ] **Step 1: Write the alembic migration**

Create `backend/alembic/versions/0010_lst_supply.py`:

```python
"""lst supply

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lst_supply",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("token", sa.String(10), primary_key=True),
        sa.Column("supply", sa.Numeric(38, 18), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lst_supply")
```

- [ ] **Step 2: Add the ORM model**

In `backend/app/core/models.py`, immediately after the existing `StakingFlow` class, add:

```python
class LstSupply(Base):
    """Hourly totalSupply() snapshot per liquid-staking token. Source:
    JSON-RPC eth_call against each LST contract on the self-hosted Geth
    node. (v3-lst)"""
    __tablename__ = "lst_supply"
    ts_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    token: Mapped[str] = mapped_column(String(10), primary_key=True)
    supply: Mapped[float] = mapped_column(Numeric(38, 18))
```

- [ ] **Step 3: Run the migration**

```bash
cd /Users/zianvalles/Projects/Eth-lst && docker compose -f /Users/zianvalles/Projects/Eth/docker-compose.yml exec -T api alembic upgrade head
```

If the api container doesn't see the new file (worktree isn't mounted into the container), use the `docker cp` workaround established in PR #26's Task 1 — copy `0010_lst_supply.py` into the api container's `/app/backend/alembic/versions/` and re-run `alembic upgrade head`.

Expected: `INFO  [alembic.runtime.migration] Running upgrade 0009 -> 0010, lst supply`.

Verify the table:

```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '\\d lst_supply'"
```

Expected: shows three columns with `(ts_bucket, token)` composite primary key.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0010_lst_supply.py backend/app/core/models.py
git commit -m "feat(lst): add lst_supply table + LstSupply model"
```

---

## Task 2 — LST registry

**Files:**
- Create: `backend/app/services/lst_tokens.py`

- [ ] **Step 1: Create the registry**

Write `backend/app/services/lst_tokens.py`:

```python
"""Liquid-staking token registry. Single source of truth for the panel +
the hourly totalSupply() cron.

Note: wstETH is intentionally excluded. It's wrapped stETH and would
double-count Lido in the stacked-area chart.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LstToken:
    symbol: str          # display + DB key
    address: str         # lowercase 0x… contract address on mainnet
    decimals: int        # always 18 for the v1 set, kept explicit for safety


# Mainnet LST contracts. Verified via Etherscan + the issuers' docs.
LST_TOKENS: tuple[LstToken, ...] = (
    LstToken("stETH",   "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", 18),  # Lido
    LstToken("rETH",    "0xae78736cd615f374d3085123a210448e74fc6393", 18),  # Rocket Pool
    LstToken("cbETH",   "0xbe9895146f7af43049ca1c1ae358b0541ea49704", 18),  # Coinbase
    LstToken("sfrxETH", "0xac3e018457b222d93114458476f3e3416abbe38f", 18),  # Frax
    LstToken("mETH",    "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa", 18),  # Mantle
    LstToken("swETH",   "0xf951e335afb289353dc249e82926178eac7ded78", 18),  # Swell
    LstToken("ETHx",    "0xa35b1b31ce002fbf2058d22f30f95d405200a15b", 18),  # Stader
)

# ABI-encoded selector for `totalSupply()` (keccak256("totalSupply()")[0:4]).
TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/lst_tokens.py
git commit -m "feat(lst): LST token registry (7 mainnet contracts)"
```

---

## Task 3 — `upsert_lst_supply` service + tests

**Files:**
- Create: `backend/app/services/lst_sync.py`
- Create: `backend/tests/test_lst_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lst_sync.py`:

```python
"""Tests for the lst_supply upsert path. Mirrors test_flow_sync conventions."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import LstSupply
from app.services.lst_sync import upsert_lst_supply


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(LstSupply).delete()
        s.commit()
        yield s


def test_upsert_lst_supply_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH", "supply": 9_876_543.21},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "rETH",  "supply":   876_543.21},
    ]
    n = upsert_lst_supply(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(LstSupply).order_by(LstSupply.token)).scalars().all()
    assert {r.token for r in stored} == {"stETH", "rETH"}


def test_upsert_lst_supply_idempotent(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH", "supply": 9_876_543.21},
    ]
    upsert_lst_supply(session, rows)
    session.commit()
    rows[0]["supply"] = 9_900_000.0
    upsert_lst_supply(session, rows)
    session.commit()
    stored = session.execute(select(LstSupply)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].supply)) == Decimal("9900000.000000000000000000")


def test_upsert_lst_supply_multi_token_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH",   "supply": 9_876_543.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "rETH",    "supply": 876_543.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "cbETH",   "supply": 234_000.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "sfrxETH", "supply": 250_000.0},
    ]
    assert upsert_lst_supply(session, rows) == 4
    session.commit()
    assert session.query(LstSupply).count() == 4
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest tests/test_lst_sync.py -v 2>&1 | tail -10
```

Expected: ImportError (cannot import name 'upsert_lst_supply').

- [ ] **Step 3: Implement the upsert service**

Create `backend/app/services/lst_sync.py`:

```python
"""Upsert path for hourly LST totalSupply() snapshots. Mirrors the flow_sync
chunked-upsert pattern; one row per (ts_bucket, token)."""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.models import LstSupply


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # Accept both ISO-8601 ("…Z") and Dune-style ("YYYY-MM-DD HH:MM:SS UTC").
    cleaned = value.replace("Z", "+00:00").replace(" UTC", "+00:00")
    return datetime.fromisoformat(cleaned)


def upsert_lst_supply(session: Session, rows: list[dict]) -> int:
    """Upsert one row per (ts_bucket, token). Returns the number of rows written."""
    if not rows:
        return 0
    values = [
        {
            "ts_bucket": _parse_ts(r["ts_bucket"]),
            "token": r["token"],
            "supply": r["supply"],
        }
        for r in rows
    ]
    stmt = pg_insert(LstSupply).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_bucket", "token"],
        set_={"supply": stmt.excluded.supply},
    )
    session.execute(stmt)
    return len(values)
```

(We define a local `_parse_ts` here rather than importing from `flow_sync.py` to keep the LST module independent — `lst_sync.py` doesn't depend on the flow infrastructure.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest tests/test_lst_sync.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lst_sync.py backend/tests/test_lst_sync.py
git commit -m "feat(lst): upsert_lst_supply service + tests"
```

---

## Task 4 — `sync_lst_supply` arq task + tests

**Files:**
- Create: `backend/app/workers/lst_jobs.py`
- Create: `backend/tests/test_lst_jobs.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lst_jobs.py`:

```python
"""Tests for the LST supply cron — exercises hex decoding + row construction
without hitting a real RPC node."""
from unittest.mock import AsyncMock

import pytest

from app.services.lst_tokens import LST_TOKENS
from app.workers.lst_jobs import _decode_uint256_to_supply, _build_rows_from_results


def test_decode_uint256_to_supply_basic():
    """`amount` (decimal-normalized) = raw / 10**decimals."""
    raw_hex = "0x" + (10**18).to_bytes(32, "big").hex()  # 1 token at 18 decimals
    assert _decode_uint256_to_supply(raw_hex, 18) == pytest.approx(1.0)


def test_decode_uint256_to_supply_large():
    """A 9.8M-token supply at 18 decimals should round-trip cleanly to float."""
    nine_point_eight_m = 9_876_543 * 10**18
    raw_hex = hex(nine_point_eight_m)
    assert _decode_uint256_to_supply(raw_hex, 18) == pytest.approx(9_876_543.0)


def test_decode_uint256_to_supply_handles_short_hex():
    """RPC nodes sometimes strip leading zeros — '0x1' should decode as 1 wei."""
    assert _decode_uint256_to_supply("0x1", 18) == pytest.approx(1e-18)


def test_decode_uint256_to_supply_returns_none_on_garbage():
    assert _decode_uint256_to_supply(None, 18) is None
    assert _decode_uint256_to_supply("not-hex", 18) is None
    assert _decode_uint256_to_supply("0x", 18) is None


def test_build_rows_from_results_pairs_tokens_in_order():
    """Token-ordering between LST_TOKENS and the RPC response must match."""
    # Fake a clean batch: each token reports 1.0 supply.
    one = "0x" + (10**18).to_bytes(32, "big").hex()
    results = [one] * len(LST_TOKENS)
    rows = _build_rows_from_results(results, ts_bucket="2026-05-02T03:00:00Z")
    assert len(rows) == len(LST_TOKENS)
    assert [r["token"] for r in rows] == [t.symbol for t in LST_TOKENS]
    assert all(r["supply"] == pytest.approx(1.0) for r in rows)


def test_build_rows_from_results_skips_failed_calls():
    """A None entry in the results list (per-call error) is skipped, not row-zeroed."""
    one = "0x" + (10**18).to_bytes(32, "big").hex()
    results: list[str | None] = [one] * len(LST_TOKENS)
    results[2] = None  # cbETH RPC failure
    rows = _build_rows_from_results(results, ts_bucket="2026-05-02T03:00:00Z")
    assert len(rows) == len(LST_TOKENS) - 1
    assert "cbETH" not in {r["token"] for r in rows}
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest tests/test_lst_jobs.py -v 2>&1 | tail -10
```

Expected: ImportError (cannot import name '_decode_uint256_to_supply' from 'app.workers.lst_jobs').

- [ ] **Step 3: Implement the cron**

Create `backend/app/workers/lst_jobs.py`:

```python
"""Hourly cron: read totalSupply() for each LST and upsert one row per token."""
import logging
from datetime import UTC, datetime

import httpx

from app.clients.eth_rpc import EthRpcClient, RpcError
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.sync_status import record_sync_ok
from app.services.lst_sync import upsert_lst_supply
from app.services.lst_tokens import LST_TOKENS, TOTAL_SUPPLY_SELECTOR

log = logging.getLogger(__name__)


def _decode_uint256_to_supply(hex_value: str | None, decimals: int) -> float | None:
    """Convert a hex-encoded uint256 RPC return into a decimal-normalized float.

    Returns None for missing / malformed responses so the caller can skip the row.
    """
    if not hex_value or not isinstance(hex_value, str):
        return None
    if not hex_value.startswith("0x"):
        return None
    body = hex_value[2:]
    if not body:
        return None
    try:
        raw = int(body, 16)
    except ValueError:
        return None
    return raw / (10 ** decimals)


def _build_rows_from_results(
    results: list[str | None], ts_bucket: str
) -> list[dict]:
    """Map (LST_TOKENS[i], results[i]) → row dicts. Skips None entries."""
    rows: list[dict] = []
    for token, raw in zip(LST_TOKENS, results):
        supply = _decode_uint256_to_supply(raw, token.decimals)
        if supply is None:
            log.warning("lst supply decode failed for %s", token.symbol)
            continue
        rows.append({"ts_bucket": ts_bucket, "token": token.symbol, "supply": supply})
    return rows


async def sync_lst_supply(ctx: dict) -> dict:
    """Read totalSupply() for each LST in a single batch call, upsert one row
    per token at the current top-of-hour bucket. No-op if ALCHEMY_HTTP_URL unset."""
    settings = get_settings()
    url = settings.effective_http_url()
    if not url:
        log.info("ALCHEMY_HTTP_URL not set — skipping lst supply sync")
        return {"skipped": "no rpc url"}

    ts_bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
    calls = [(t.address, TOTAL_SUPPLY_SELECTOR) for t in LST_TOKENS]

    async with httpx.AsyncClient(timeout=20.0) as http:
        client = EthRpcClient(http, url=url)
        try:
            results = await client.batch_eth_call(calls)
        except (httpx.HTTPError, RpcError) as e:
            log.error("lst supply batch_eth_call failed: %s", e)
            return {"error": str(e)}

    rows = _build_rows_from_results(results, ts_bucket=ts_bucket)
    if not rows:
        log.warning("lst supply: no rows decoded — skipping write")
        return {"lst_supply": 0}

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = upsert_lst_supply(session, rows)
        session.commit()

    record_sync_ok("lst_supply")
    log.info("synced lst_supply: %d rows", n)
    return {"lst_supply": n}
```

The `effective_http_url()` helper already exists on `Settings` (used by the wallet-profile feature) — verify by running `grep -n effective_http_url backend/app/core/config.py` if uncertain.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest tests/test_lst_jobs.py -v 2>&1 | tail -15
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/lst_jobs.py backend/tests/test_lst_jobs.py
git commit -m "feat(lst): sync_lst_supply arq task + tests"
```

---

## Task 5 — Wire cron into arq settings

**Files:**
- Modify: `backend/app/workers/arq_settings.py`

- [ ] **Step 1: Register the cron**

In `backend/app/workers/arq_settings.py`:

1. Add the import next to the existing flow-jobs import (around line 10):

```python
from app.workers.lst_jobs import sync_lst_supply
```

2. Add `sync_lst_supply` to the `functions` tuple (the list of registered arq tasks; it's the same block that lists `sync_dune_flows`, `sync_order_flow`, `sync_volume_buckets`, etc.).

3. Add a `cron(...)` entry to the `cron_jobs` list. Use minute=7 to offset from the on-the-hour syncs (e.g. price + alerts run at minute 0):

```python
        cron(sync_lst_supply, minute={7}, run_at_startup=False),
```

If you can't tell where exactly each block lives, search for `sync_dune_flows` — both the `functions` tuple and the `cron_jobs` list will be near it.

- [ ] **Step 2: Sanity-check arq imports cleanly**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/python -c "from app.workers.arq_settings import WorkerSettings; print(sorted(f.__name__ for f in WorkerSettings.functions))"
```

Expected output: a list including `sync_lst_supply` alongside the other sync_* functions.

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/arq_settings.py
git commit -m "feat(lst): register sync_lst_supply hourly cron (minute 7)"
```

---

## Task 6 — API schemas + endpoint

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/staking.py`

- [ ] **Step 1: Add response schemas**

In `backend/app/api/schemas.py`, find the existing `StakingSummary` class (added in PR #26). Immediately after it, add:

```python
class LstSupplyPoint(BaseModel):
    ts_bucket: datetime
    token: str
    supply: float


class LstSupplyResponse(BaseModel):
    points: list[LstSupplyPoint]
```

(All required imports — `datetime`, `BaseModel` — are already at the top of the file.)

- [ ] **Step 2: Add the endpoint to the existing staking router**

In `backend/app/api/staking.py`:

1. Update the `app.api.schemas` import to include the new response types:

```python
from app.api.schemas import (
    LstSupplyPoint,
    LstSupplyResponse,
    StakingFlowPoint,
    StakingFlowsResponse,
    StakingSummary,
)
```

2. Add an import for the new model (sort alphabetically with existing model imports):

```python
from app.core.models import LstSupply, StakingFlow
```

3. At the bottom of the file, after the existing `staking_summary` endpoint, add:

```python
@router.get("/lst-supply", response_model=LstSupplyResponse)
def lst_supply(
    session: Annotated[Session, Depends(get_session)],
    hours: HoursParam = 720,  # default 30 days for the panel
    limit: int = Query(20000, ge=1, le=200000),
) -> LstSupplyResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(LstSupply)
        .where(LstSupply.ts_bucket >= cutoff)
        .order_by(LstSupply.ts_bucket.asc(), LstSupply.token.asc())
        .limit(limit)
    ).scalars().all()
    return LstSupplyResponse(
        points=[
            LstSupplyPoint(
                ts_bucket=r.ts_bucket,
                token=r.token,
                supply=float(r.supply),
            )
            for r in rows
        ]
    )
```

- [ ] **Step 3: Smoke check the import graph**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/python -c "
from app.api.staking import router
from app.api.schemas import LstSupplyPoint, LstSupplyResponse
print('imports OK')
print('routes:', [r.path for r in router.routes])
"
```

Expected: `routes: ['/staking/flows', '/staking/summary', '/staking/lst-supply']`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/staking.py
git commit -m "feat(lst): /api/staking/lst-supply endpoint + schemas"
```

---

## Task 7 — Frontend types + fetcher

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetcher**

In `frontend/src/api.ts`, after the existing `fetchStakingSummary` function (added in PR #26), add:

```typescript
export type LstSupplyPoint = {
  ts_bucket: string;
  token: string;
  supply: number;
};

export async function fetchLstSupply(hours: number): Promise<LstSupplyPoint[]> {
  const r = await apiFetch(`/api/staking/lst-supply?hours=${hours}`);
  if (!r.ok) throw new Error(`lst supply ${r.status}`);
  return (await r.json()).points;
}
```

- [ ] **Step 2: Verify the build**

```bash
cd /Users/zianvalles/Projects/Eth-lst/frontend && npm run build 2>&1 | tail -8
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(lst): frontend fetchLstSupply + LstSupplyPoint type"
```

---

## Task 8 — `LstMarketSharePanel` React component

**Files:**
- Create: `frontend/src/components/LstMarketSharePanel.tsx`
- Modify: `frontend/src/lib/panelRegistry.ts`

- [ ] **Step 1: Write the panel component**

Create `frontend/src/components/LstMarketSharePanel.tsx`:

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchLstSupply,
  rangeToHours,
  type FlowRange,
  type LstSupplyPoint,
} from "../api";
import Card from "./ui/Card";
import FlowRangeSelector from "./FlowRangeSelector";

// Stable per-token color so the eye can track each band over time.
// Order matches typical market-share rank desc.
const TOKEN_ORDER = ["stETH", "rETH", "cbETH", "sfrxETH", "mETH", "swETH", "ETHx"] as const;
type LstSymbol = (typeof TOKEN_ORDER)[number];

const COLORS: Record<LstSymbol, string> = {
  stETH: "rgb(56 189 248)",   // sky-400
  rETH: "rgb(244 114 182)",   // pink-400
  cbETH: "rgb(96 165 250)",   // blue-400
  sfrxETH: "rgb(251 146 60)", // orange-400
  mETH: "rgb(52 211 153)",    // emerald-400
  swETH: "rgb(167 139 250)",  // violet-400
  ETHx: "rgb(250 204 21)",    // yellow-400
};

type StackRow = {
  ts: string;
  // Each token symbol -> supply at that bucket. Missing tokens absent.
  [k: string]: string | number | undefined;
};

export default function LstMarketSharePanel() {
  const [range, setRange] = useState<FlowRange>("30d");
  const hours = rangeToHours(range);

  const { data, isLoading, error } = useQuery({
    queryKey: ["lst-supply", hours],
    queryFn: () => fetchLstSupply(hours),
    refetchInterval: 5 * 60_000,
  });

  const stacked = pivot(data ?? []);
  const latest = stacked.at(-1);
  const totalLatest = latest
    ? TOKEN_ORDER.reduce((acc, t) => acc + ((latest[t] as number) ?? 0), 0)
    : 0;

  return (
    <Card
      title="LST market share"
      subtitle={`last ${range} · totalSupply per token (raw, not ETH-normalized)`}
      actions={<FlowRangeSelector value={range} onChange={setRange} />}
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && stacked.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — waiting for first hourly sync
        </p>
      )}
      {stacked.length > 0 && (
        <div className="space-y-3">
          <ul className="space-y-1.5">
            {TOKEN_ORDER.map((t) => {
              const cur = latest ? ((latest[t] as number) ?? 0) : 0;
              const pct = totalLatest > 0 ? (cur / totalLatest) * 100 : 0;
              return (
                <li
                  key={t}
                  className="flex items-center justify-between text-xs font-mono tabular-nums"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-sm"
                      style={{ backgroundColor: COLORS[t] }}
                    />
                    <span className="text-slate-300">{t}</span>
                  </span>
                  <span className="text-slate-400">
                    {pct.toFixed(1)}%
                  </span>
                </li>
              );
            })}
          </ul>

          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stacked} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="ts"
                  tickFormatter={(v: string) => v.slice(5, 10)}
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={32}
                />
                <YAxis
                  tick={{ fill: "rgb(148 163 184)", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={48}
                  tickFormatter={(v: number) =>
                    v >= 1e6
                      ? `${(v / 1e6).toFixed(1)}M`
                      : v >= 1e3
                        ? `${(v / 1e3).toFixed(0)}k`
                        : v.toString()
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: "rgb(15 23 42)",
                    border: "1px solid rgb(51 65 85)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "rgb(148 163 184)" }}
                />
                {TOKEN_ORDER.map((t) => (
                  <Area
                    key={t}
                    type="monotone"
                    dataKey={t}
                    stackId="lst"
                    stroke={COLORS[t]}
                    fill={COLORS[t]}
                    fillOpacity={0.7}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
}

function pivot(points: LstSupplyPoint[]): StackRow[] {
  // Group by ts_bucket → { ts, stETH: ..., rETH: ..., ... }.
  const byTs = new Map<string, StackRow>();
  for (const p of points) {
    let row = byTs.get(p.ts_bucket);
    if (!row) {
      row = { ts: p.ts_bucket };
      byTs.set(p.ts_bucket, row);
    }
    row[p.token] = p.supply;
  }
  return [...byTs.values()].sort((a, b) =>
    (a.ts as string).localeCompare(b.ts as string),
  );
}
```

- [ ] **Step 2: Register the panel**

In `frontend/src/lib/panelRegistry.ts`:

1. Add the import alongside the other panel imports (alphabetical):

```typescript
import LstMarketSharePanel from "../components/LstMarketSharePanel";
```

2. Add a new entry in the `PANELS` array, immediately after the `staking-flows` entry:

```typescript
  { id: "lst-market-share", label: "LST market share", component: LstMarketSharePanel, defaultPage: "onchain", defaultWidth: 2 },
```

(width `2` because the stacked-area chart needs more horizontal real estate than the divergent-bar Beacon Flows panel.)

- [ ] **Step 3: Build the frontend**

```bash
cd /Users/zianvalles/Projects/Eth-lst/frontend && npm run build 2>&1 | tail -8
```

Expected: succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LstMarketSharePanel.tsx frontend/src/lib/panelRegistry.ts
git commit -m "feat(lst): LstMarketSharePanel (Recharts stacked area) + registry entry"
```

---

## Task 9 — CLAUDE.md milestone update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the v3-lst milestone line**

In `CLAUDE.md`, find the existing `v3-staking ✅` line (under `## v3 status`). Immediately after it, add:

```markdown
- v3-lst ⚠️ LST market share — hourly arq cron (`sync_lst_supply`, minute 7) batches 7 `eth_call(totalSupply())` reads against the self-hosted Geth node for stETH/rETH/cbETH/sfrxETH/mETH/swETH/ETHx; persists to `lst_supply`; `/api/staking/lst-supply` endpoint; `LstMarketSharePanel` renders Recharts stacked area + per-token current % share. Reuses `ALCHEMY_HTTP_URL` (no new env var). v1 displays raw `totalSupply()` (not ETH-equivalent) — share-tokens like rETH/sfrxETH read ~10% under their ETH backing; future work to normalize. Spec: `docs/superpowers/specs/2026-05-02-lst-market-share-design.md`.
```

(Use ⚠️ until the cron has populated at least a few rows; flip to ✅ in a follow-up commit.)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(lst): add v3-lst milestone line to CLAUDE.md"
```

---

## Task 10 — Backend test sweep

- [ ] **Step 1: Run the new tests**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest tests/test_lst_sync.py tests/test_lst_jobs.py -v 2>&1 | tail -20
```

Expected: 9 passed (3 sync + 6 jobs).

- [ ] **Step 2: Run full suite**

```bash
cd /Users/zianvalles/Projects/Eth-lst/backend && .venv/bin/pytest -q 2>&1 | tail -10
```

Expected: all of `test_lst_sync` + `test_lst_jobs` pass; no NEW failures vs main. Pre-existing `test_flows_api` failures persist (unrelated, on main).

- [ ] **Step 3: Run frontend build once more**

```bash
cd /Users/zianvalles/Projects/Eth-lst/frontend && npm run build 2>&1 | tail -8
```

Expected: succeeds.

- [ ] **Step 4: No-op commit gate**

If any of the above failed, fix the root cause and create a NEW commit (not `--amend`). If they all passed, no commit needed for this task.

---

## Task 11 — Open and merge the PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/zianvalles/Projects/Eth-lst && git push -u origin feat/lst-market-share
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "feat(lst): LST market share panel — hourly totalSupply() snapshots for 7 LSTs" --body "$(cat <<'EOF'
## Summary
Sub-project B of v3-staking. Adds an LST market share panel showing 30d stacked-area \`totalSupply()\` for the 7 dominant liquid-staking tokens:
- **stETH** (Lido), **rETH** (Rocket Pool), **cbETH** (Coinbase), **sfrxETH** (Frax), **mETH** (Mantle), **swETH** (Swell), **ETHx** (Stader)

Hourly arq cron batches all 7 \`eth_call(totalSupply())\` reads in a single JSON-RPC request against the self-hosted Geth node. No new env vars (reuses \`ALCHEMY_HTTP_URL\`).

Skips wstETH (wrapped stETH would double-count Lido).

Spec: \`docs/superpowers/specs/2026-05-02-lst-market-share-design.md\`.

## Files
**Backend**
- new: alembic 0010 — \`lst_supply\` table
- new: \`backend/app/services/lst_tokens.py\` — 7-entry registry
- new: \`backend/app/services/lst_sync.py\` — \`upsert_lst_supply\`
- new: \`backend/app/workers/lst_jobs.py\` — \`sync_lst_supply\` arq task (cron at minute 7)
- mod: \`models.py\`, \`arq_settings.py\`, \`api/schemas.py\`, \`api/staking.py\`

**Frontend**
- new: \`LstMarketSharePanel.tsx\` — Recharts stacked area + per-token current % share legend
- mod: \`api.ts\`, \`panelRegistry.ts\`

**Config**
- \`CLAUDE.md\` — v3-lst milestone

## Test plan
- [x] \`pytest tests/test_lst_sync.py tests/test_lst_jobs.py -v\` — 9 passed
- [x] full \`pytest -q\` — no NEW failures vs main
- [x] \`npm run build\` — succeeds
- [ ] **Post-merge:** restart worker, wait for next minute-7 cron tick (or trigger manually with \`docker compose exec worker python -c "import asyncio; from app.workers.lst_jobs import sync_lst_supply; print(asyncio.run(sync_lst_supply({})))\"\`), verify \`lst_supply\` table populates with 7 rows.
- [ ] **Post-merge:** refresh dashboard Onchain page, confirm LST market share panel renders.

## Out of scope (follow-ups)
- ETH-equivalent normalization (per-token \`getExchangeRate()\` for rETH/sfrxETH/etc.)
- Restaking layer / LRTs (eETH, ezETH, rsETH, pufETH) — separate panel
- Per-token mint/burn flow

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Self-review the PR diff**

Open the PR URL, eyeball the diff. Run no other commands; just check it visually.

- [ ] **Step 4: Squash-merge**

```bash
gh pr merge --squash --delete-branch
```

(The local-branch deletion warning is expected when running from the worktree — ignore it; the worktree cleanup happens in the next step.)

- [ ] **Step 5: Cleanup the worktree, sync local main**

```bash
cd /Users/zianvalles/Projects/Eth
git worktree remove /Users/zianvalles/Projects/Eth-lst --force
git branch -D feat/lst-market-share || true
git fetch origin
git reset --hard origin/main
```

---

## Task 12 — Trigger first sync, verify, flip ⚠️→✅

This step is performed by the controller (or whoever has Docker access on the box). Runs against the merged code on `main`.

- [ ] **Step 1: Recreate worker container so it picks up the new arq task**

```bash
cd /Users/zianvalles/Projects/Eth && docker compose up -d worker
```

- [ ] **Step 2: Apply the migration (if not already applied)**

```bash
docker compose exec -T api alembic upgrade head
```

Expected: `Running upgrade 0009 -> 0010` (or already-at-head if Task 1 ran it earlier).

- [ ] **Step 3: Trigger the cron inline**

```bash
docker compose exec -T worker python -c "
import asyncio
from app.workers.lst_jobs import sync_lst_supply
print(asyncio.run(sync_lst_supply({})))
"
```

Expected: `{'lst_supply': 7}` (one row per LST).

- [ ] **Step 4: Verify rows landed**

```bash
docker compose exec -T postgres bash -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -t -c \"select token, round(supply::numeric, 0) from lst_supply order by supply desc;\""
```

Expected: 7 rows, stETH dominant (~9-10M), rETH/cbETH/etc. trailing.

- [ ] **Step 5: Flip CLAUDE.md ⚠️→✅**

```bash
sed -i '' 's/v3-lst ⚠️ LST/v3-lst ✅ LST/' CLAUDE.md
git add CLAUDE.md
git commit -m "docs(lst): flip v3-lst ⚠️→✅ — first sync produced 7 rows"
git push
```

---

## Self-review

**Spec coverage:**
- Hourly cron with 7 LST batch read → Tasks 4, 5.
- `lst_supply` table with composite PK → Task 1.
- LST registry as single source of truth → Task 2.
- `/api/staking/lst-supply` endpoint extending the existing router → Task 6.
- Recharts stacked area + per-token legend with current % → Task 8.
- Skips wstETH (documented) → Task 2 registry.
- No new env vars (reuses `ALCHEMY_HTTP_URL`) → Task 4 uses `settings.effective_http_url()`.
- v1 displays raw supply, not ETH-equivalent → Task 8 panel subtitle calls it out.
- Backend tests: upsert + decode + row construction → Tasks 3, 4.
- Failure modes (RPC error → skip; missing url → no-op) → Task 4 cron implementation.
- CLAUDE.md milestone → Task 9, flipped in Task 12.

**Type consistency:**
- `token: str` everywhere (DB column, ORM `Mapped[str]`, schema `str`, registry `LstToken.symbol: str`, panel `keyof typeof COLORS`).
- `supply` is `Numeric(38, 18)` → `float` at API boundary → `number` in TS — same shape as the `amount_eth` chain in the Beacon Flows panel.
- `ts_bucket` is `DateTime(timezone=True)` → `datetime` in schema → `string` in TS — same chain as the rest of the project.
- Cron task name: `sync_lst_supply` everywhere (worker file name, registered function, log line, sync_status key).

**Placeholder scan:** none — every step has runnable code or an exact command with expected output.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-02-lst-market-share.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, controller reviews between, fast iteration. Same flow used for v3-staking sub-project A.

**2. Inline Execution** — run tasks here in this session at natural boundaries (1–5 backend plumbing, 6 API, 7–8 frontend, 9–11 polish + ship, 12 verify).

Which approach?
