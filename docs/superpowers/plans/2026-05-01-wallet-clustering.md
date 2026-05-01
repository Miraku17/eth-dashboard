# Wallet Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the on-demand wallet-clustering drawer that closes v2: any address rendered in the dashboard becomes clickable; click opens a side panel showing labels, probably-linked wallets with confidence + reason, and aggregate stats. Backed by Etherscan REST API with a 7-day Postgres cache.

**Architecture:** Synchronous lookup. `GET /api/clusters/{address}` returns from Postgres if a fresh cache row exists, otherwise calls the Etherscan client (~6 calls in parallel), runs two heuristics (shared gas funder, same CEX deposit address), assembles a `ClusterResult`, upserts the cache, and returns. A daily arq cron purges expired rows. Frontend wraps every address render site in a shared `<AddressLink>` that opens a `<WalletDrawer>`.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy + alembic + arq + httpx (backend); React + TanStack Query + Tailwind + Zustand (frontend). Tests: pytest + pytest-asyncio + testcontainers + httpx.MockTransport (backend); vitest + RTL (frontend).

**Spec:** `docs/superpowers/specs/2026-05-01-wallet-clustering-design.md`.

**File map:**
- Create:
  - `backend/alembic/versions/0007_wallet_clusters.py`
  - `backend/app/clients/etherscan.py`
  - `backend/app/services/clustering/__init__.py`
  - `backend/app/services/clustering/public_funders.json`
  - `backend/app/services/clustering/public_funders.py`
  - `backend/app/services/clustering/gas_funder.py`
  - `backend/app/services/clustering/cex_deposit.py`
  - `backend/app/services/clustering/cluster_engine.py`
  - `backend/app/api/clusters.py`
  - `backend/app/workers/cluster_jobs.py`
  - `backend/tests/test_etherscan_client.py`
  - `backend/tests/test_public_funders.py`
  - `backend/tests/test_gas_funder.py`
  - `backend/tests/test_cex_deposit.py`
  - `backend/tests/test_cluster_engine.py`
  - `backend/tests/test_clusters_api.py`
  - `backend/tests/test_cluster_purge.py`
  - `frontend/src/components/AddressLink.tsx`
  - `frontend/src/components/WalletDrawer.tsx`
  - `frontend/src/state/walletDrawer.ts`
  - `frontend/src/components/__tests__/AddressLink.test.tsx`
  - `frontend/src/components/__tests__/WalletDrawer.test.tsx`
- Modify:
  - `backend/app/core/config.py` (add 4 cluster settings)
  - `backend/app/core/models.py` (add `WalletCluster`)
  - `backend/app/api/schemas.py` (add cluster Pydantic schemas)
  - `backend/app/main.py` (register clusters router)
  - `backend/app/workers/arq_settings.py` (register `purge_expired_clusters` cron)
  - `frontend/src/api.ts` (add `fetchCluster`, `refreshCluster`, types)
  - `frontend/src/components/WhaleTransfersPanel.tsx` (use `<AddressLink>`)
  - `frontend/src/components/SmartMoneyLeaderboardPanel.tsx` (use `<AddressLink>`)
  - `frontend/src/App.tsx` (mount `<WalletDrawer />` at root)
  - `CLAUDE.md` (flip wallet-clustering to ✅ in final task)

---

## Task 1 — Add cluster settings to config

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py` (existing)

- [ ] **Step 1: Read existing config test to match style**

Run: `cat backend/tests/test_config.py | head -40`

- [ ] **Step 2: Append cluster-config assertions**

Add to the bottom of the existing test that loads `Settings()` (or write a new tiny test if the file has none yet):

```python
def test_cluster_settings_have_defaults(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "x")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("POSTGRES_DB", "x")
    monkeypatch.setenv("POSTGRES_HOST", "x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    from app.core.config import Settings
    s = Settings(_env_file=None)
    assert s.cluster_cache_ttl_days == 7
    assert s.cluster_max_linked_wallets == 50
    assert s.cluster_max_deposit_candidates == 10
    assert s.cluster_funder_strong_threshold == 50
```

- [ ] **Step 3: Run test, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_config.py::test_cluster_settings_have_defaults -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'cluster_cache_ttl_days'`

- [ ] **Step 4: Add the settings**

In `backend/app/core/config.py`, after the `whale_stable_threshold_usd` block, add:

```python
    # Wallet clustering (v2-final). Cache TTL is days because clustering signals
    # are stable over time (a wallet's funding history is fixed).
    cluster_cache_ttl_days: int = 7
    cluster_max_linked_wallets: int = 50
    cluster_max_deposit_candidates: int = 10
    cluster_funder_strong_threshold: int = 50
```

- [ ] **Step 5: Run test, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_config.py::test_cluster_settings_have_defaults -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(clusters): add cluster_* settings to config"
```

---

## Task 2 — `WalletCluster` model + migration 0007

**Files:**
- Modify: `backend/app/core/models.py`
- Create: `backend/alembic/versions/0007_wallet_clusters.py`
- Test: `backend/tests/test_db_schema.py` (existing)

- [ ] **Step 1: Add a schema test**

Append to `backend/tests/test_db_schema.py`:

```python
def test_wallet_clusters_table_exists(session):
    from sqlalchemy import inspect
    insp = inspect(session.bind)
    assert "wallet_clusters" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("wallet_clusters")}
    assert cols == {"address", "computed_at", "ttl_expires_at", "payload"}
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_db_schema.py::test_wallet_clusters_table_exists -v`
Expected: FAIL — table doesn't exist.

- [ ] **Step 3: Add the model**

Append to `backend/app/core/models.py` (after `SmartMoneyLeaderboard`):

```python
class WalletCluster(Base):
    """Cached wallet-clustering result. One row per queried address.

    `payload` is the full serialized ClusterResult (Pydantic) so the engine
    can evolve without schema migrations.
    """
    __tablename__ = "wallet_clusters"
    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB)
```

- [ ] **Step 4: Create the migration**

`backend/alembic/versions/0007_wallet_clusters.py`:

```python
"""wallet clusters

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_clusters",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )
    op.create_index(
        "ix_wallet_clusters_ttl_expires_at",
        "wallet_clusters",
        ["ttl_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_clusters_ttl_expires_at", table_name="wallet_clusters")
    op.drop_table("wallet_clusters")
```

- [ ] **Step 5: Run schema test, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_db_schema.py::test_wallet_clusters_table_exists -v`
Expected: PASS — testcontainers fixture runs alembic up to head before the test.

- [ ] **Step 6: Run the full schema test file as a sanity check**

Run: `cd backend && .venv/bin/pytest tests/test_db_schema.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/models.py backend/alembic/versions/0007_wallet_clusters.py backend/tests/test_db_schema.py
git commit -m "feat(clusters): WalletCluster model + 0007 migration"
```

---

## Task 3 — Etherscan async client

**Files:**
- Create: `backend/app/clients/etherscan.py`
- Test: `backend/tests/test_etherscan_client.py`

- [ ] **Step 1: Write the test (mocked transport)**

Create `backend/tests/test_etherscan_client.py`:

```python
import json
import httpx
import pytest

from app.clients.etherscan import (
    EtherscanClient,
    EtherscanRateLimited,
    EtherscanUnavailable,
)


def _ok(rows):
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})


def _empty():
    return httpx.Response(200, json={"status": "0", "message": "No transactions found", "result": []})


async def test_txlist_asc_returns_rows():
    rows = [{"hash": "0xabc", "from": "0xfrom", "to": "0xto", "value": "1000000000000000000",
             "blockNumber": "100", "timeStamp": "1714000000"}]

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api"
        params = dict(req.url.params)
        assert params["module"] == "account"
        assert params["action"] == "txlist"
        assert params["address"] == "0xtarget"
        assert params["sort"] == "asc"
        assert params["page"] == "1"
        return _ok(rows)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget", sort="asc", page=1, offset=10)
    assert out == rows


async def test_empty_result_treated_as_empty_list():
    transport = httpx.MockTransport(lambda r: _empty())
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget")
    assert out == []


async def test_rate_limit_message_raises_typed_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "0",
            "message": "NOTOK",
            "result": "Max rate limit reached",
        })
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        with pytest.raises(EtherscanRateLimited):
            await client.txlist("0xtarget", _max_attempts=1)


async def test_5xx_retries_then_raises():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="bad gateway")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        with pytest.raises(EtherscanUnavailable):
            await client.txlist("0xtarget", _max_attempts=3, _backoff_s=0.0)
    assert calls["n"] == 3


async def test_5xx_retry_then_recover():
    seq = [
        httpx.Response(502, text="bad"),
        _ok([{"hash": "0x1"}]),
    ]
    it = iter(seq)

    def handler(req: httpx.Request) -> httpx.Response:
        return next(it)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        out = await client.txlist("0xtarget", _max_attempts=3, _backoff_s=0.0)
    assert out == [{"hash": "0x1"}]


async def test_tokentx_passes_contract_filter():
    rows = [{"hash": "0xabc", "contractAddress": "0xusdc"}]
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params))
        return _ok(rows)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.etherscan.io") as http:
        client = EtherscanClient(http, api_key="key")
        await client.tokentx("0xtarget", contract_address="0xusdc")
    assert seen["action"] == "tokentx"
    assert seen["contractaddress"] == "0xusdc"
```

- [ ] **Step 2: Run, expect import failure**

Run: `cd backend && .venv/bin/pytest tests/test_etherscan_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.clients.etherscan'`

- [ ] **Step 3: Implement the client**

Create `backend/app/clients/etherscan.py`:

```python
"""Async wrapper around Etherscan's REST API. Used by wallet clustering.

Etherscan free tier: 5 req/s, 100k req/day. We cap concurrency at 4 via an
internal semaphore (see EtherscanClient.__init__). Soft-fail with typed
exceptions so callers can serve stale cache during outages.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

ETHERSCAN_BASE_URL = "https://api.etherscan.io"

log = logging.getLogger(__name__)


class EtherscanRateLimited(RuntimeError):
    pass


class EtherscanUnavailable(RuntimeError):
    pass


class EtherscanClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str, *, max_concurrency: int = 4) -> None:
        self._http = http
        self._api_key = api_key
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _get(
        self,
        params: dict[str, Any],
        *,
        _max_attempts: int = 3,
        _backoff_s: float = 0.5,
    ) -> list[dict] | dict:
        params = {**params, "apikey": self._api_key}
        attempt = 0
        async with self._sem:
            while True:
                attempt += 1
                try:
                    r = await self._http.get("/api", params=params)
                except httpx.HTTPError as e:
                    if attempt >= _max_attempts:
                        raise EtherscanUnavailable(str(e)) from e
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                if r.status_code >= 500:
                    if attempt >= _max_attempts:
                        raise EtherscanUnavailable(f"HTTP {r.status_code}")
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                if r.status_code == 429:
                    if attempt >= _max_attempts:
                        raise EtherscanRateLimited("HTTP 429")
                    await asyncio.sleep(_backoff_s * attempt)
                    continue

                r.raise_for_status()
                body = r.json()

                # Etherscan returns 200 with status "0" for both "no results" and rate limits.
                if body.get("status") == "0":
                    msg = str(body.get("message", "")).lower()
                    res = body.get("result")
                    if msg == "no transactions found":
                        return []
                    if isinstance(res, str) and "rate limit" in res.lower():
                        if attempt >= _max_attempts:
                            raise EtherscanRateLimited(res)
                        await asyncio.sleep(_backoff_s * attempt)
                        continue
                    # Other "0" with empty result list — treat as empty.
                    if isinstance(res, list):
                        return res
                    raise EtherscanUnavailable(f"unexpected response: {body!r}")

                return body.get("result", [])

    async def txlist(
        self,
        address: str,
        *,
        startblock: int = 0,
        endblock: int = 99_999_999,
        sort: str = "asc",
        page: int = 1,
        offset: int = 100,
        **kwargs: Any,
    ) -> list[dict]:
        return await self._get(
            {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": startblock,
                "endblock": endblock,
                "sort": sort,
                "page": page,
                "offset": offset,
            },
            **kwargs,
        )

    async def txlistinternal(self, address: str, **kwargs: Any) -> list[dict]:
        return await self._get(
            {
                "module": "account",
                "action": "txlistinternal",
                "address": address,
                "sort": "asc",
                "page": 1,
                "offset": 50,
            },
            **kwargs,
        )

    async def tokentx(
        self,
        address: str,
        *,
        contract_address: str | None = None,
        sort: str = "desc",
        page: int = 1,
        offset: int = 100,
        **kwargs: Any,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "sort": sort,
            "page": page,
            "offset": offset,
        }
        if contract_address:
            params["contractaddress"] = contract_address
        return await self._get(params, **kwargs)
```

- [ ] **Step 4: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_etherscan_client.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/etherscan.py backend/tests/test_etherscan_client.py
git commit -m "feat(clusters): async Etherscan client with rate-limit + 5xx retry"
```

---

## Task 4 — Public-funder denylist

**Files:**
- Create: `backend/app/services/clustering/__init__.py`
- Create: `backend/app/services/clustering/public_funders.json`
- Create: `backend/app/services/clustering/public_funders.py`
- Test: `backend/tests/test_public_funders.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_public_funders.py`:

```python
from app.services.clustering.public_funders import (
    is_public_funder,
    public_funder_label,
    load_public_funders,
)


def test_known_binance_hot_wallet_is_public():
    # Binance 14, also in realtime/labels.py
    assert is_public_funder("0x28c6c06298d514db089934071355e5743bf21d60") is True


def test_label_lookup_returns_kind():
    label = public_funder_label("0x28c6c06298d514db089934071355e5743bf21d60")
    assert label is not None
    assert label["kind"] == "cex"


def test_unknown_address_is_not_public():
    assert is_public_funder("0x" + "a" * 40) is False


def test_lookup_is_case_insensitive():
    upper = "0x28C6C06298D514DB089934071355E5743BF21D60"
    assert is_public_funder(upper) is True


def test_load_returns_dict_keyed_by_lowercased_address():
    data = load_public_funders()
    assert isinstance(data, dict)
    for addr in data:
        assert addr == addr.lower()
        assert addr.startswith("0x") and len(addr) == 42
```

- [ ] **Step 2: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_public_funders.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the JSON denylist**

Create `backend/app/services/clustering/public_funders.json`:

```json
{
  "addresses": [
    {"address": "0x28c6c06298d514db089934071355e5743bf21d60", "label": "Binance 14", "kind": "cex"},
    {"address": "0x21a31ee1afc51d94c2efccaa2092ad1028285549", "label": "Binance 15", "kind": "cex"},
    {"address": "0xdfd5293d8e347dfe59e90efd55b2956a1343963d", "label": "Binance 16", "kind": "cex"},
    {"address": "0x56eddb7aa87536c09ccc2793473599fd21a8b17f", "label": "Binance 17", "kind": "cex"},
    {"address": "0x9696f59e4d72e237be84ffd425dcad154bf96976", "label": "Binance 18", "kind": "cex"},
    {"address": "0x4976a4a02f38326660d17bf34b431dc6e2eb2327", "label": "Binance 19", "kind": "cex"},
    {"address": "0xf977814e90da44bfa03b6295a0616a897441acec", "label": "Binance 8", "kind": "cex"},
    {"address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3", "label": "Coinbase 1", "kind": "cex"},
    {"address": "0x503828976d22510aad0201ac7ec88293211d23da", "label": "Coinbase 2", "kind": "cex"},
    {"address": "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740", "label": "Coinbase 3", "kind": "cex"},
    {"address": "0x3cd751e6b0078be393132286c442345e5dc49699", "label": "Coinbase 4", "kind": "cex"},
    {"address": "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511", "label": "Coinbase 5", "kind": "cex"},
    {"address": "0xeb2629a2734e272bcc07bda959863f316f4bd4cf", "label": "Coinbase 6", "kind": "cex"},
    {"address": "0xa090e606e30bd747d4e6245a1517ebe430f0057e", "label": "Coinbase 10", "kind": "cex"},
    {"address": "0x2910543af39aba0cd09dbb2d50200b3e800a63d2", "label": "Kraken 1", "kind": "cex"},
    {"address": "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13", "label": "Kraken 2", "kind": "cex"},
    {"address": "0xe853c56864a2ebe4576a807d26fdc4a0ada51919", "label": "Kraken 3", "kind": "cex"},
    {"address": "0x53d284357ec70ce289d6d64134dfac8e511c8a3d", "label": "Kraken 4", "kind": "cex"},
    {"address": "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b", "label": "OKX 1", "kind": "cex"},
    {"address": "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3", "label": "OKX 2", "kind": "cex"},
    {"address": "0xa7efae728d2936e78bda97dc267687568dd593f3", "label": "OKX 3", "kind": "cex"},
    {"address": "0x1151314c646ce4e0efd76d1af4760ae66a9fe30f", "label": "Bitfinex 2", "kind": "cex"},
    {"address": "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa", "label": "Bitfinex 3", "kind": "cex"},
    {"address": "0xf89d7b9c864f589bbf53a82105107622b35eaa40", "label": "Bybit", "kind": "cex"},
    {"address": "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf", "label": "Tornado 0.1 ETH", "kind": "mixer"},
    {"address": "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936", "label": "Tornado 1 ETH", "kind": "mixer"},
    {"address": "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf", "label": "Tornado 10 ETH", "kind": "mixer"},
    {"address": "0xa160cdab225685da1d56aa342ad8841c3b53f291", "label": "Tornado 100 ETH", "kind": "mixer"},
    {"address": "0xb8901acb165ed027e32754e0ffe830802919727f", "label": "Hop ETH Bridge", "kind": "bridge"},
    {"address": "0x3666f603cc164936c1b87e207f36beba4ac5f18a", "label": "Stargate Bridge", "kind": "bridge"},
    {"address": "0x4f4495243837681061c4743b74b3eedf548d56a5", "label": "Across Bridge", "kind": "bridge"},
    {"address": "0x3ee18b2214aff97000d974cf647e7c347e8fa585", "label": "Wormhole Token Bridge", "kind": "bridge"}
  ]
}
```

- [ ] **Step 4: Create the loader**

`backend/app/services/clustering/__init__.py` — empty file.

`backend/app/services/clustering/public_funders.py`:

```python
"""Static denylist of addresses that fund many unrelated wallets.

Without this list, the shared-gas-funder heuristic would falsely link any
two wallets that ever received ETH from a CEX, a bridge, or Tornado Cash.
The list is hand-curated; extend by editing public_funders.json.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_DATA_PATH = Path(__file__).parent / "public_funders.json"


class FunderEntry(TypedDict):
    label: str
    kind: str  # "cex" | "mixer" | "bridge" | "faucet" | "builder"


@lru_cache(maxsize=1)
def load_public_funders() -> dict[str, FunderEntry]:
    raw = json.loads(_DATA_PATH.read_text())
    out: dict[str, FunderEntry] = {}
    for row in raw["addresses"]:
        addr = row["address"].lower()
        out[addr] = {"label": row["label"], "kind": row["kind"]}
    return out


def is_public_funder(address: str) -> bool:
    return address.lower() in load_public_funders()


def public_funder_label(address: str) -> FunderEntry | None:
    return load_public_funders().get(address.lower())
```

- [ ] **Step 5: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_public_funders.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/clustering/__init__.py \
        backend/app/services/clustering/public_funders.json \
        backend/app/services/clustering/public_funders.py \
        backend/tests/test_public_funders.py
git commit -m "feat(clusters): public-funder denylist + loader"
```

---

## Task 5 — Gas-funder heuristic

**Files:**
- Create: `backend/app/services/clustering/gas_funder.py`
- Test: `backend/tests/test_gas_funder.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_gas_funder.py`:

```python
from unittest.mock import AsyncMock

import pytest

from app.services.clustering.gas_funder import (
    FunderInfo,
    find_first_funder,
    find_co_funded_wallets,
)


async def test_first_funder_picks_lowest_block_inbound_with_value():
    client = AsyncMock()
    client.txlist.return_value = [
        # outbound (skip)
        {"from": "0xtarget", "to": "0xother", "value": "1", "blockNumber": "5",
         "timeStamp": "100", "hash": "0xa"},
        # inbound zero value (skip)
        {"from": "0xfunder", "to": "0xtarget", "value": "0", "blockNumber": "6",
         "timeStamp": "101", "hash": "0xb"},
        # the real first inflow
        {"from": "0xfunder", "to": "0xtarget", "value": "1000000000000000000",
         "blockNumber": "7", "timeStamp": "102", "hash": "0xc"},
        {"from": "0xother", "to": "0xtarget", "value": "1", "blockNumber": "8",
         "timeStamp": "103", "hash": "0xd"},
    ]

    funder = await find_first_funder(client, "0xtarget")
    assert funder == FunderInfo(address="0xfunder", tx_hash="0xc", block_number=7)


async def test_first_funder_returns_none_for_empty_history():
    client = AsyncMock()
    client.txlist.return_value = []
    client.txlistinternal.return_value = []
    funder = await find_first_funder(client, "0xtarget")
    assert funder is None


async def test_first_funder_falls_back_to_internal_tx():
    client = AsyncMock()
    client.txlist.return_value = []  # contract-funded wallet has no normal inbound
    client.txlistinternal.return_value = [
        {"from": "0xmsigsender", "to": "0xtarget", "value": "5000000000000000000",
         "blockNumber": "10", "timeStamp": "200", "hash": "0xe"},
    ]
    funder = await find_first_funder(client, "0xtarget")
    assert funder is not None
    assert funder.address == "0xmsigsender"


async def test_co_funded_wallets_returns_unique_recipients_excluding_target():
    client = AsyncMock()
    client.txlist.return_value = [
        {"from": "0xfunder", "to": "0xtarget", "value": "1", "blockNumber": "5",
         "timeStamp": "100", "hash": "0xa"},
        {"from": "0xfunder", "to": "0xa", "value": "1", "blockNumber": "6",
         "timeStamp": "101", "hash": "0xb"},
        {"from": "0xfunder", "to": "0xb", "value": "0", "blockNumber": "7",
         "timeStamp": "102", "hash": "0xc"},  # zero value still counts as a fund
        {"from": "0xfunder", "to": "0xa", "value": "1", "blockNumber": "8",
         "timeStamp": "103", "hash": "0xd"},  # dedup
    ]

    result = await find_co_funded_wallets(client, "0xfunder", target="0xtarget", limit=10)
    assert set(result) == {"0xa", "0xb"}


async def test_co_funded_respects_limit():
    rows = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(20)
    ]
    client = AsyncMock()
    client.txlist.return_value = rows
    result = await find_co_funded_wallets(client, "0xfunder", target=None, limit=5)
    assert len(result) == 5
```

- [ ] **Step 2: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_gas_funder.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`backend/app/services/clustering/gas_funder.py`:

```python
"""H1: shared gas funder.

Algorithm:
  - For wallet X, the *funder* is the `from` of the lowest-block inbound tx
    with non-zero value.
  - If no normal inbound exists, fall back to internal txs (contract payouts).
  - Co-funded wallets = unique `to` addresses across all txs sent FROM the
    funder (capped to limit).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.etherscan import EtherscanClient


@dataclass(frozen=True)
class FunderInfo:
    address: str
    tx_hash: str
    block_number: int


def _to_int(v: str | int | None) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


async def find_first_funder(client: EtherscanClient, target: str) -> FunderInfo | None:
    target_lc = target.lower()

    # Pass 1: normal external txs.
    rows = await client.txlist(target, sort="asc", page=1, offset=100)
    candidate = _earliest_inbound_with_value(rows, target_lc)
    if candidate is not None:
        return candidate

    # Pass 2: internal (contract-driven) txs.
    rows = await client.txlistinternal(target)
    candidate = _earliest_inbound_with_value(rows, target_lc)
    return candidate


def _earliest_inbound_with_value(rows: list[dict], target_lc: str) -> FunderInfo | None:
    best: FunderInfo | None = None
    best_block = 10**18
    for r in rows:
        if (r.get("to") or "").lower() != target_lc:
            continue
        if _to_int(r.get("value")) <= 0:
            continue
        bn = _to_int(r.get("blockNumber"))
        if bn < best_block:
            best_block = bn
            best = FunderInfo(
                address=(r.get("from") or "").lower(),
                tx_hash=r.get("hash") or "",
                block_number=bn,
            )
    return best


async def find_co_funded_wallets(
    client: EtherscanClient,
    funder: str,
    *,
    target: str | None,
    limit: int,
) -> list[str]:
    """Unique downstream recipients of `funder`, capped at `limit` (in iteration order).

    `target` is excluded so the target wallet doesn't appear as its own neighbor.
    """
    rows = await client.txlist(funder, sort="asc", page=1, offset=max(limit * 4, 100))
    target_lc = target.lower() if target else None
    seen: list[str] = []
    seen_set: set[str] = set()
    funder_lc = funder.lower()
    for r in rows:
        if (r.get("from") or "").lower() != funder_lc:
            continue
        to = (r.get("to") or "").lower()
        if not to or to == target_lc or to in seen_set:
            continue
        seen.append(to)
        seen_set.add(to)
        if len(seen) >= limit:
            break
    return seen
```

- [ ] **Step 4: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_gas_funder.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/clustering/gas_funder.py backend/tests/test_gas_funder.py
git commit -m "feat(clusters): shared gas-funder heuristic (H1)"
```

---

## Task 6 — CEX-deposit heuristic

**Files:**
- Create: `backend/app/services/clustering/cex_deposit.py`
- Test: `backend/tests/test_cex_deposit.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_cex_deposit.py`:

```python
from unittest.mock import AsyncMock

import pytest

from app.services.clustering.cex_deposit import (
    DepositMatch,
    find_deposit_addresses,
    find_co_depositors,
)

# These match `app.realtime.labels._LABELS` — Binance 14 + Coinbase 1.
BINANCE_HOT = "0x28c6c06298d514db089934071355e5743bf21d60"
COINBASE_HOT = "0x71660c4005ba85c37ccec55d0c4493e66fe775d3"


async def test_finds_deposit_when_forwarder_empties_into_hot_wallet():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        # target sent ETH to forwarder 0xfwd
        if addr.lower() == "0xtarget":
            return [
                {"from": "0xtarget", "to": "0xfwd", "value": "1000000000000000000",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
            ]
        # 0xfwd later forwarded into Binance hot wallet
        if addr.lower() == "0xfwd":
            return [
                {"from": "0xfwd", "to": BINANCE_HOT, "value": "1000000000000000000",
                 "blockNumber": "11", "timeStamp": "200", "hash": "0xb"},
            ]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=5)
    assert matches == [DepositMatch(deposit_address="0xfwd", exchange="binance")]


async def test_skips_when_forwarder_does_not_reach_known_hot_wallet():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xtarget":
            return [
                {"from": "0xtarget", "to": "0xnotaforwarder", "value": "1000000000000000000",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
            ]
        if addr.lower() == "0xnotaforwarder":
            return [
                {"from": "0xnotaforwarder", "to": "0xrandomeoa", "value": "1",
                 "blockNumber": "11", "timeStamp": "200", "hash": "0xb"},
            ]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=5)
    assert matches == []


async def test_picks_top_candidates_by_aggregate_value():
    """When the wallet sends to many addresses, we only investigate the top N
    by aggregate USD value to bound Etherscan calls."""
    client = AsyncMock()
    target_rows = []
    for i in range(20):
        # bigger values to lower-indexed forwarders
        target_rows.append({
            "from": "0xtarget",
            "to": f"0x{i:040x}",
            "value": str((20 - i) * 10**18),
            "blockNumber": str(i),
            "timeStamp": str(i),
            "hash": f"0x{i:064x}",
        })

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xtarget":
            return target_rows
        # only the top-1 (0x0...0) forwards into a hot wallet
        if addr == f"0x{0:040x}":
            return [{"from": addr, "to": BINANCE_HOT, "value": "1",
                     "blockNumber": "999", "timeStamp": "999", "hash": "0xff"}]
        return []

    client.txlist.side_effect = txlist_router
    client.tokentx.return_value = []

    matches = await find_deposit_addresses(client, "0xtarget", max_candidates=3)
    assert len(matches) == 1
    assert matches[0].deposit_address == f"0x{0:040x}"
    assert matches[0].exchange == "binance"


async def test_co_depositors_returns_unique_senders_to_same_forwarder():
    client = AsyncMock()

    async def txlist_router(addr, **kw):
        if addr.lower() == "0xfwd":
            return [
                {"from": "0xtarget", "to": "0xfwd", "value": "1",
                 "blockNumber": "10", "timeStamp": "100", "hash": "0xa"},
                {"from": "0xpeer1", "to": "0xfwd", "value": "1",
                 "blockNumber": "11", "timeStamp": "101", "hash": "0xb"},
                {"from": "0xpeer2", "to": "0xfwd", "value": "1",
                 "blockNumber": "12", "timeStamp": "102", "hash": "0xc"},
                {"from": "0xpeer1", "to": "0xfwd", "value": "1",
                 "blockNumber": "13", "timeStamp": "103", "hash": "0xd"},
                {"from": "0xfwd", "to": BINANCE_HOT, "value": "1",
                 "blockNumber": "14", "timeStamp": "104", "hash": "0xe"},
            ]
        return []

    client.txlist.side_effect = txlist_router

    peers = await find_co_depositors(client, deposit_address="0xfwd",
                                     target="0xtarget", limit=10)
    assert set(peers) == {"0xpeer1", "0xpeer2"}
```

- [ ] **Step 2: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_cex_deposit.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`backend/app/services/clustering/cex_deposit.py`:

```python
"""H2: same CEX deposit address.

A CEX deposit address is unique per user: the exchange generates a fresh
forwarder per customer that empties into a known hot wallet within minutes.
If two wallets send funds to the same forwarder, they are with very high
probability the same CEX account holder.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.etherscan import EtherscanClient
from app.realtime.labels import _LABELS as HOT_WALLET_LABELS

# Map hot wallet -> exchange slug (binance/coinbase/kraken/...) used in our UI.
_HOT_WALLET_TO_EXCHANGE: dict[str, str] = {}
for _addr, _label in HOT_WALLET_LABELS.items():
    _HOT_WALLET_TO_EXCHANGE[_addr.lower()] = _label.split(" ")[0].lower()


@dataclass(frozen=True)
class DepositMatch:
    deposit_address: str
    exchange: str


def _to_int(v: str | int | None) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


async def find_deposit_addresses(
    client: EtherscanClient,
    target: str,
    *,
    max_candidates: int,
) -> list[DepositMatch]:
    target_lc = target.lower()

    # Aggregate outbound-by-recipient across normal txs and ERC-20 transfers.
    eth_rows = await client.txlist(target, sort="desc", page=1, offset=200)
    erc20_rows = await client.tokentx(target, sort="desc", page=1, offset=200)

    aggregate: dict[str, int] = {}
    for r in eth_rows + erc20_rows:
        if (r.get("from") or "").lower() != target_lc:
            continue
        to = (r.get("to") or "").lower()
        if not to or to in _HOT_WALLET_TO_EXCHANGE:
            # Direct sends to a hot wallet aren't deposits-via-forwarder.
            continue
        aggregate[to] = aggregate.get(to, 0) + _to_int(r.get("value"))

    candidates = sorted(aggregate.items(), key=lambda kv: kv[1], reverse=True)[:max_candidates]

    matches: list[DepositMatch] = []
    for addr, _ in candidates:
        forwarder_rows = await client.txlist(addr, sort="asc", page=1, offset=20)
        for fr in forwarder_rows:
            to = (fr.get("to") or "").lower()
            if (fr.get("from") or "").lower() != addr:
                continue
            ex = _HOT_WALLET_TO_EXCHANGE.get(to)
            if ex:
                matches.append(DepositMatch(deposit_address=addr, exchange=ex))
                break
    return matches


async def find_co_depositors(
    client: EtherscanClient,
    *,
    deposit_address: str,
    target: str,
    limit: int,
) -> list[str]:
    rows = await client.txlist(deposit_address, sort="desc", page=1, offset=max(limit * 4, 100))
    deposit_lc = deposit_address.lower()
    target_lc = target.lower()
    seen: list[str] = []
    seen_set: set[str] = set()
    for r in rows:
        if (r.get("to") or "").lower() != deposit_lc:
            continue  # we want INBOUND to the forwarder
        sender = (r.get("from") or "").lower()
        if not sender or sender == target_lc or sender in seen_set:
            continue
        seen.append(sender)
        seen_set.add(sender)
        if len(seen) >= limit:
            break
    return seen
```

- [ ] **Step 4: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_cex_deposit.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/clustering/cex_deposit.py backend/tests/test_cex_deposit.py
git commit -m "feat(clusters): same-CEX-deposit heuristic (H2)"
```

---

## Task 7 — Cluster engine orchestrator + Pydantic schemas

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/services/clustering/cluster_engine.py`
- Test: `backend/tests/test_cluster_engine.py`

- [ ] **Step 1: Add Pydantic schemas**

Append to `backend/app/api/schemas.py`:

```python
class GasFunderInfo(BaseModel):
    address: str
    label: str | None = None
    is_public: bool
    tx_hash: str
    block_number: int


class CexDepositInfo(BaseModel):
    address: str
    exchange: str


class LinkedWallet(BaseModel):
    address: str
    label: str | None = None
    confidence: Literal["strong", "weak"]
    reasons: list[str]


class ClusterStats(BaseModel):
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    tx_count: int = 0


class ClusterResult(BaseModel):
    address: str
    computed_at: datetime
    stale: bool = False
    labels: list[str] = []
    gas_funder: GasFunderInfo | None = None
    cex_deposits: list[CexDepositInfo] = []
    linked_wallets: list[LinkedWallet] = []
    stats: ClusterStats = ClusterStats()
```

If `Literal` and `datetime` aren't already imported in `schemas.py`, add:

```python
from datetime import datetime
from typing import Literal
```

- [ ] **Step 2: Write the engine test**

Create `backend/tests/test_cluster_engine.py`:

```python
from unittest.mock import AsyncMock

import pytest

from app.services.clustering import cluster_engine as ce


BINANCE_HOT = "0x28c6c06298d514db089934071355e5743bf21d60"


def _mk_client(txlist=None, txlist_internal=None, tokentx=None):
    client = AsyncMock()
    client.txlist.side_effect = txlist or (lambda addr, **kw: [])
    client.txlistinternal.side_effect = txlist_internal or (lambda addr, **kw: [])
    client.tokentx.side_effect = tokentx or (lambda addr, **kw: [])
    return client


async def test_engine_returns_empty_for_unknown_wallet():
    client = _mk_client()
    result = await ce.compute(client, "0xtarget", max_linked=10,
                              max_deposit_candidates=5, funder_strong_threshold=50)
    assert result.address == "0xtarget"
    assert result.linked_wallets == []
    assert result.gas_funder is None
    assert result.cex_deposits == []


async def test_engine_finds_strong_link_via_shared_funder():
    """Funder F is private (not on denylist) and has only 2 fan-out txs:
    target + peer. Both wallets share F → strong link."""
    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1000000000000000000",
                     "blockNumber": "5", "timeStamp": "100", "hash": "0xa"}]
        if addr.lower() == "0xfunder":
            return [
                {"from": "0xfunder", "to": "0xtarget", "value": "1", "blockNumber": "5",
                 "timeStamp": "100", "hash": "0xa"},
                {"from": "0xfunder", "to": "0xpeer", "value": "1", "blockNumber": "6",
                 "timeStamp": "101", "hash": "0xb"},
            ]
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=50,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert result.gas_funder is not None
    assert result.gas_funder.is_public is False
    assert len(result.linked_wallets) == 1
    lw = result.linked_wallets[0]
    assert lw.address == "0xpeer"
    assert lw.confidence == "strong"
    assert any(r.startswith("shared_gas_funder:") for r in lw.reasons)


async def test_engine_suppresses_link_when_funder_is_public():
    """Binance funded both wallets — must NOT show as linked."""
    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": BINANCE_HOT, "to": "0xtarget", "value": "1000000000000000000",
                     "blockNumber": "5", "timeStamp": "100", "hash": "0xa"}]
        if addr.lower() == BINANCE_HOT:
            return [
                {"from": BINANCE_HOT, "to": "0xtarget", "value": "1", "blockNumber": "5",
                 "timeStamp": "100", "hash": "0xa"},
                {"from": BINANCE_HOT, "to": "0xrandom", "value": "1", "blockNumber": "6",
                 "timeStamp": "101", "hash": "0xb"},
            ]
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=50,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert result.gas_funder is not None
    assert result.gas_funder.is_public is True
    assert result.linked_wallets == []  # suppressed


async def test_engine_classifies_funder_as_weak_above_threshold():
    """Funder with >threshold fan-out → linked wallets get `weak` confidence."""
    fanout = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(60)
    ]

    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1",
                     "blockNumber": "0", "timeStamp": "0", "hash": "0xaa"}]
        if addr.lower() == "0xfunder":
            return fanout
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=10,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert all(lw.confidence == "weak" for lw in result.linked_wallets)


async def test_engine_caps_linked_wallets_to_max():
    fanout = [
        {"from": "0xfunder", "to": f"0x{i:040x}", "value": "1",
         "blockNumber": str(i), "timeStamp": str(i), "hash": f"0x{i:064x}"}
        for i in range(20)
    ]

    async def txlist(addr, **kw):
        if addr.lower() == "0xtarget":
            return [{"from": "0xfunder", "to": "0xtarget", "value": "1",
                     "blockNumber": "0", "timeStamp": "0", "hash": "0xaa"}]
        if addr.lower() == "0xfunder":
            return fanout
        return []

    client = _mk_client(txlist=txlist)
    result = await ce.compute(client, "0xtarget", max_linked=5,
                              max_deposit_candidates=5, funder_strong_threshold=50)

    assert len(result.linked_wallets) == 5
```

- [ ] **Step 3: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_cluster_engine.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement the engine**

`backend/app/services/clustering/cluster_engine.py`:

```python
"""Cluster engine orchestrator: address -> ClusterResult.

Synchronous, stateless. Caller is responsible for caching the result.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.api.schemas import (
    CexDepositInfo,
    ClusterResult,
    ClusterStats,
    GasFunderInfo,
    LinkedWallet,
)
from app.clients.etherscan import EtherscanClient
from app.realtime.labels import label_for
from app.services.clustering.cex_deposit import (
    DepositMatch,
    find_co_depositors,
    find_deposit_addresses,
)
from app.services.clustering.gas_funder import (
    FunderInfo,
    find_co_funded_wallets,
    find_first_funder,
)
from app.services.clustering.public_funders import (
    is_public_funder,
    public_funder_label,
)


def _to_int(v: str | int | None) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


async def compute(
    client: EtherscanClient,
    address: str,
    *,
    max_linked: int,
    max_deposit_candidates: int,
    funder_strong_threshold: int,
) -> ClusterResult:
    target = address.lower()

    # H1 + stats source: first funder + a peek at recent activity in parallel.
    funder, deposits = await asyncio.gather(
        find_first_funder(client, target),
        find_deposit_addresses(client, target, max_candidates=max_deposit_candidates),
    )

    gas_funder_info: GasFunderInfo | None = None
    co_funded: list[str] = []
    is_pub = False
    if funder is not None:
        is_pub = is_public_funder(funder.address)
        funder_label_entry = public_funder_label(funder.address)
        gas_funder_info = GasFunderInfo(
            address=funder.address,
            label=(funder_label_entry["label"] if funder_label_entry else label_for(funder.address)),
            is_public=is_pub,
            tx_hash=funder.tx_hash,
            block_number=funder.block_number,
        )
        if not is_pub:
            co_funded = await find_co_funded_wallets(
                client,
                funder.address,
                target=target,
                limit=funder_strong_threshold + 1,
            )

    # H2: co-depositors per deposit address.
    co_depositors_by_dep: dict[str, list[str]] = {}
    for dep in deposits:
        peers = await find_co_depositors(
            client,
            deposit_address=dep.deposit_address,
            target=target,
            limit=max_linked,
        )
        co_depositors_by_dep[dep.deposit_address] = peers

    # Assemble linked-wallet rows. Strong = H2 OR (H1 with funder fan-out below threshold).
    funder_strong = (
        funder is not None
        and not is_pub
        and len(co_funded) <= funder_strong_threshold
    )

    rows: dict[str, LinkedWallet] = {}

    for dep, peers in co_depositors_by_dep.items():
        for peer in peers:
            row = rows.get(peer) or LinkedWallet(
                address=peer, confidence="strong", reasons=[]
            )
            ex = next((d.exchange for d in deposits if d.deposit_address == dep), "")
            row.reasons.append(f"shared_cex_deposit:{ex}:{dep}")
            row.confidence = "strong"
            rows[peer] = row

    if funder is not None and not is_pub:
        for peer in co_funded[:max_linked]:
            row = rows.get(peer) or LinkedWallet(
                address=peer,
                confidence="strong" if funder_strong else "weak",
                reasons=[],
            )
            row.reasons.append(f"shared_gas_funder:{funder.address}")
            # Strong from H2 wins over weak from H1.
            if row.confidence != "strong" and funder_strong:
                row.confidence = "strong"
            rows[peer] = row

    # Label-enrich every linked wallet via local CEX label list (cheap, no I/O).
    for peer, row in rows.items():
        if row.label is None:
            row.label = label_for(peer)

    linked = list(rows.values())[:max_linked]

    # Stats: derived from a desc page of the target's normal txs (1 call).
    stats = await _compute_stats(client, target)

    labels = [lbl for lbl in [label_for(target)] if lbl]

    return ClusterResult(
        address=target,
        computed_at=datetime.now(timezone.utc),
        stale=False,
        labels=labels,
        gas_funder=gas_funder_info,
        cex_deposits=[CexDepositInfo(address=d.deposit_address, exchange=d.exchange) for d in deposits],
        linked_wallets=linked,
        stats=stats,
    )


async def _compute_stats(client: EtherscanClient, target: str) -> ClusterStats:
    # Last-seen / first-seen approximation: latest desc + earliest asc page-1.
    desc = await client.txlist(target, sort="desc", page=1, offset=1)
    asc = await client.txlist(target, sort="asc", page=1, offset=1)
    last_seen = None
    first_seen = None
    if desc:
        ts = _to_int(desc[0].get("timeStamp"))
        if ts > 0:
            last_seen = datetime.fromtimestamp(ts, tz=timezone.utc)
    if asc:
        ts = _to_int(asc[0].get("timeStamp"))
        if ts > 0:
            first_seen = datetime.fromtimestamp(ts, tz=timezone.utc)
    # tx_count: cheap count via desc page-1 of length 1 doesn't tell us total.
    # Etherscan's free API exposes totals only via paginated counts; we use a
    # capped fetch instead and surface "≥ N" client-side.
    bulk = await client.txlist(target, sort="desc", page=1, offset=100)
    return ClusterStats(first_seen=first_seen, last_seen=last_seen, tx_count=len(bulk))
```

- [ ] **Step 5: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_cluster_engine.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/clustering/cluster_engine.py \
        backend/app/api/schemas.py \
        backend/tests/test_cluster_engine.py
git commit -m "feat(clusters): cluster engine orchestrator + Pydantic schemas"
```

---

## Task 8 — `/api/clusters` routes + auth + Postgres cache

**Files:**
- Create: `backend/app/api/clusters.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_clusters_api.py`

- [ ] **Step 1: Write the API test**

Create `backend/tests/test_clusters_api.py`:

```python
"""End-to-end clusters API: cache hit, cache miss, refresh, stale-fallback."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import ClusterResult, ClusterStats
from app.core.models import WalletCluster
from app.main import app


def _login(client: TestClient):
    """Reuse the helper from test_auth.py — log in via /api/auth/login."""
    from tests.conftest import login as login_helper  # if exists; otherwise inline
    return login_helper(client)


@pytest.fixture
def authed_client(client: TestClient):
    _login(client)
    return client


def _store_cache_row(session, address: str, payload: dict, ttl_expires_at: datetime):
    row = WalletCluster(
        address=address,
        computed_at=ttl_expires_at - timedelta(days=7),
        ttl_expires_at=ttl_expires_at,
        payload=payload,
    )
    session.add(row)
    session.commit()


def _fresh_payload(address: str) -> dict:
    return ClusterResult(
        address=address,
        computed_at=datetime.now(timezone.utc),
        labels=["Some Label"],
        linked_wallets=[],
        stats=ClusterStats(),
    ).model_dump(mode="json")


def test_get_cluster_returns_cached_result(authed_client, db_session):
    addr = "0x" + "1" * 40
    _store_cache_row(db_session, addr, _fresh_payload(addr),
                     datetime.now(timezone.utc) + timedelta(days=3))
    r = authed_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200
    assert r.json()["address"] == addr
    assert r.json()["stale"] is False


def test_get_cluster_computes_when_no_cache(authed_client, db_session):
    addr = "0x" + "2" * 40

    fake = ClusterResult(address=addr, computed_at=datetime.now(timezone.utc))
    with patch("app.api.clusters._compute_for_address", AsyncMock(return_value=fake)):
        r = authed_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200
    assert r.json()["address"] == addr

    # And it was upserted into the cache.
    row = db_session.get(WalletCluster, addr)
    assert row is not None


def test_post_refresh_busts_cache_and_recomputes(authed_client, db_session):
    addr = "0x" + "3" * 40
    _store_cache_row(db_session, addr, _fresh_payload(addr),
                     datetime.now(timezone.utc) + timedelta(days=3))

    new = ClusterResult(address=addr, computed_at=datetime.now(timezone.utc),
                        labels=["After Refresh"])
    with patch("app.api.clusters._compute_for_address", AsyncMock(return_value=new)):
        r = authed_client.post(f"/api/clusters/{addr}/refresh")
    assert r.status_code == 200
    assert r.json()["labels"] == ["After Refresh"]


def test_get_cluster_serves_stale_during_etherscan_outage(authed_client, db_session):
    """Expired row + Etherscan unavailable → return stale row with stale=true."""
    from app.clients.etherscan import EtherscanUnavailable
    addr = "0x" + "4" * 40
    _store_cache_row(db_session, addr, _fresh_payload(addr),
                     datetime.now(timezone.utc) - timedelta(days=1))  # expired

    with patch("app.api.clusters._compute_for_address",
               AsyncMock(side_effect=EtherscanUnavailable("down"))):
        r = authed_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 200
    assert r.json()["stale"] is True


def test_get_cluster_503_when_no_cache_and_etherscan_down(authed_client):
    from app.clients.etherscan import EtherscanUnavailable
    addr = "0x" + "5" * 40
    with patch("app.api.clusters._compute_for_address",
               AsyncMock(side_effect=EtherscanUnavailable("down"))):
        r = authed_client.get(f"/api/clusters/{addr}")
    assert r.status_code == 503


def test_malformed_address_returns_400(authed_client):
    r = authed_client.get("/api/clusters/not-an-address")
    assert r.status_code == 400


def test_requires_auth(client: TestClient):
    addr = "0x" + "6" * 40
    r = client.get(f"/api/clusters/{addr}")
    assert r.status_code == 401
```

> If `tests/conftest.py` doesn't already provide a `login` helper, copy the
> 4-line login block from `tests/test_auth.py` inline at the top of this file.
> The existing fixtures `client` and `db_session` are already available
> (Postgres + Redis testcontainers + autoflush).

- [ ] **Step 2: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_clusters_api.py -v`
Expected: FAIL — module `app.api.clusters` doesn't exist.

- [ ] **Step 3: Implement the API**

Create `backend/app/api/clusters.py`:

```python
"""Wallet clustering API.

GET  /api/clusters/{address}            return cached or compute inline
POST /api/clusters/{address}/refresh    invalidate cache and recompute
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.schemas import ClusterResult
from app.clients.etherscan import (
    ETHERSCAN_BASE_URL,
    EtherscanClient,
    EtherscanRateLimited,
    EtherscanUnavailable,
)
from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import WalletCluster
from app.services.clustering import cluster_engine

router = APIRouter(prefix="/clusters", tags=["clusters"])

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _validate(address: str) -> str:
    if not _ADDR_RE.match(address):
        raise HTTPException(status_code=400, detail="malformed_address")
    return address.lower()


def _read_cache(session: Session, address: str) -> WalletCluster | None:
    return session.get(WalletCluster, address)


def _write_cache(session: Session, result: ClusterResult, ttl_days: int) -> None:
    payload = result.model_dump(mode="json")
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    stmt = insert(WalletCluster).values(
        address=result.address,
        computed_at=result.computed_at,
        ttl_expires_at=expires,
        payload=payload,
    ).on_conflict_do_update(
        index_elements=["address"],
        set_={
            "computed_at": result.computed_at,
            "ttl_expires_at": expires,
            "payload": payload,
        },
    )
    session.execute(stmt)
    session.commit()


def _hydrate_stale(row: WalletCluster) -> ClusterResult:
    data = dict(row.payload)
    data["stale"] = True
    return ClusterResult.model_validate(data)


async def _compute_for_address(address: str) -> ClusterResult:
    settings = get_settings()
    if not settings.etherscan_api_key:
        raise EtherscanUnavailable("ETHERSCAN_API_KEY not configured")
    async with httpx.AsyncClient(base_url=ETHERSCAN_BASE_URL, timeout=20.0) as http:
        client = EtherscanClient(http, api_key=settings.etherscan_api_key)
        return await cluster_engine.compute(
            client,
            address,
            max_linked=settings.cluster_max_linked_wallets,
            max_deposit_candidates=settings.cluster_max_deposit_candidates,
            funder_strong_threshold=settings.cluster_funder_strong_threshold,
        )


@router.get("/{address}", response_model=ClusterResult)
async def get_cluster(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> ClusterResult:
    addr = _validate(address)
    settings = get_settings()
    row = _read_cache(session, addr)
    now = datetime.now(timezone.utc)
    if row is not None and row.ttl_expires_at > now:
        return ClusterResult.model_validate(row.payload)

    try:
        result = await _compute_for_address(addr)
    except (EtherscanUnavailable, EtherscanRateLimited):
        if row is not None:
            return _hydrate_stale(row)
        raise HTTPException(status_code=503, detail="etherscan_unavailable")

    _write_cache(session, result, settings.cluster_cache_ttl_days)
    return result


@router.post("/{address}/refresh", response_model=ClusterResult)
async def refresh_cluster(
    address: str,
    session: Annotated[Session, Depends(get_session)],
) -> ClusterResult:
    addr = _validate(address)
    settings = get_settings()
    try:
        result = await _compute_for_address(addr)
    except (EtherscanUnavailable, EtherscanRateLimited):
        row = _read_cache(session, addr)
        if row is not None:
            return _hydrate_stale(row)
        raise HTTPException(status_code=503, detail="etherscan_unavailable")
    _write_cache(session, result, settings.cluster_cache_ttl_days)
    return result
```

- [ ] **Step 4: Mount the router**

Edit `backend/app/main.py`:

```python
# add to imports near the others
from app.api.clusters import router as clusters_router
```

and add at the bottom of the auth-gated block:

```python
app.include_router(clusters_router, prefix="/api", dependencies=[AuthDep])
```

- [ ] **Step 5: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_clusters_api.py -v`
Expected: 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/clusters.py backend/app/main.py backend/tests/test_clusters_api.py
git commit -m "feat(clusters): /api/clusters routes with cache + stale-fallback"
```

---

## Task 9 — Daily purge cron for expired cluster rows

**Files:**
- Create: `backend/app/workers/cluster_jobs.py`
- Modify: `backend/app/workers/arq_settings.py`
- Test: `backend/tests/test_cluster_purge.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_cluster_purge.py`:

```python
from datetime import datetime, timedelta, timezone

from app.core.models import WalletCluster
from app.workers.cluster_jobs import purge_expired_clusters


async def test_purge_deletes_rows_older_than_grace_period(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        # fresh — keep
        WalletCluster(
            address="0x" + "a" * 40,
            computed_at=now,
            ttl_expires_at=now + timedelta(days=3),
            payload={},
        ),
        # expired but within grace — keep
        WalletCluster(
            address="0x" + "b" * 40,
            computed_at=now - timedelta(days=8),
            ttl_expires_at=now - timedelta(days=1),
            payload={},
        ),
        # expired beyond grace — delete
        WalletCluster(
            address="0x" + "c" * 40,
            computed_at=now - timedelta(days=20),
            ttl_expires_at=now - timedelta(days=8),
            payload={},
        ),
    ])
    db_session.commit()

    deleted = await purge_expired_clusters({"_db_session_for_test": db_session})

    assert deleted == 1
    db_session.expire_all()
    surviving = {row.address for row in db_session.query(WalletCluster).all()}
    assert "0x" + "c" * 40 not in surviving
    assert "0x" + "a" * 40 in surviving
    assert "0x" + "b" * 40 in surviving
```

- [ ] **Step 2: Run, expect failure**

Run: `cd backend && .venv/bin/pytest tests/test_cluster_purge.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `backend/app/workers/cluster_jobs.py`:

```python
"""Daily cron: drop wallet_clusters rows that are past their grace window.

We keep rows for `cluster_cache_ttl_days` past expiry as a stale-fallback
during Etherscan outages. After that window, they're permanently deleted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import WalletCluster

log = logging.getLogger(__name__)


async def purge_expired_clusters(ctx: dict) -> int:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.cluster_cache_ttl_days)

    # Allow tests to inject a session without spinning up SessionLocal.
    test_session = ctx.get("_db_session_for_test") if isinstance(ctx, dict) else None
    if test_session is not None:
        result = test_session.execute(
            delete(WalletCluster).where(WalletCluster.ttl_expires_at < cutoff)
        )
        test_session.commit()
        n = result.rowcount or 0
    else:
        with SessionLocal() as session:
            result = session.execute(
                delete(WalletCluster).where(WalletCluster.ttl_expires_at < cutoff)
            )
            session.commit()
            n = result.rowcount or 0

    log.info("purged %d expired wallet_clusters rows", n)
    return n
```

- [ ] **Step 4: Wire the cron**

Edit `backend/app/workers/arq_settings.py`. Add to imports near the top:

```python
from app.workers.cluster_jobs import purge_expired_clusters
```

Add `purge_expired_clusters` to the `functions` tuple (alongside `sync_volume_buckets`, etc.).

Add a cron entry in the `cron_jobs` tuple (match style of existing entries):

```python
cron(purge_expired_clusters, hour={3}, minute={11}, run_at_startup=False),
```

(03:11 UTC daily — picks an off-peak slot away from existing crons.)

- [ ] **Step 5: Run, expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_cluster_purge.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/cluster_jobs.py \
        backend/app/workers/arq_settings.py \
        backend/tests/test_cluster_purge.py
git commit -m "feat(clusters): daily purge cron for expired wallet_clusters rows"
```

---

## Task 10 — Frontend: api client + types

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add types and fetchers**

Append to `frontend/src/api.ts` (use the existing `apiFetch` wrapper present there):

```typescript
// ---- Wallet clustering --------------------------------------------------

export type ClusterConfidence = "strong" | "weak";

export type LinkedWallet = {
  address: string;
  label: string | null;
  confidence: ClusterConfidence;
  reasons: string[];
};

export type GasFunderInfo = {
  address: string;
  label: string | null;
  is_public: boolean;
  tx_hash: string;
  block_number: number;
};

export type CexDepositInfo = {
  address: string;
  exchange: string;
};

export type ClusterStats = {
  first_seen: string | null;
  last_seen: string | null;
  tx_count: number;
};

export type ClusterResult = {
  address: string;
  computed_at: string;
  stale: boolean;
  labels: string[];
  gas_funder: GasFunderInfo | null;
  cex_deposits: CexDepositInfo[];
  linked_wallets: LinkedWallet[];
  stats: ClusterStats;
};

export async function fetchCluster(address: string): Promise<ClusterResult> {
  const r = await apiFetch(`/api/clusters/${address}`);
  if (!r.ok) throw new Error(`fetchCluster failed: ${r.status}`);
  return r.json();
}

export async function refreshCluster(address: string): Promise<ClusterResult> {
  const r = await apiFetch(`/api/clusters/${address}/refresh`, { method: "POST" });
  if (!r.ok) throw new Error(`refreshCluster failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Build to confirm types compile**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(clusters): frontend api client + types for /api/clusters"
```

---

## Task 11 — Frontend: drawer state + `<AddressLink>` component

**Files:**
- Create: `frontend/src/state/walletDrawer.ts`
- Create: `frontend/src/components/AddressLink.tsx`
- Create: `frontend/src/components/__tests__/AddressLink.test.tsx`

- [ ] **Step 1: Write the test**

Create `frontend/src/components/__tests__/AddressLink.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import AddressLink from "../AddressLink";
import { useWalletDrawer } from "../../state/walletDrawer";

describe("AddressLink", () => {
  beforeEach(() => {
    useWalletDrawer.setState({ address: null, open: false });
  });

  it("renders a truncated address by default", () => {
    render(<AddressLink address="0x1234567890abcdef1234567890abcdef12345678" />);
    expect(screen.getByRole("button")).toHaveTextContent("0x1234…5678");
  });

  it("opens the drawer with the address on click", () => {
    render(<AddressLink address="0x1234567890abcdef1234567890abcdef12345678" />);
    fireEvent.click(screen.getByRole("button"));
    const state = useWalletDrawer.getState();
    expect(state.address).toBe("0x1234567890abcdef1234567890abcdef12345678");
    expect(state.open).toBe(true);
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd frontend && npm run test -- AddressLink`
Expected: FAIL — module missing.

> If the project doesn't have vitest/RTL configured yet, skip the auto-run and
> rely on `npm run build` + manual smoke-test instead. Existing frontend tests
> already exercise vitest if any are present in the repo.

- [ ] **Step 3: Implement the drawer state (Zustand)**

Create `frontend/src/state/walletDrawer.ts`:

```typescript
import { create } from "zustand";

type State = {
  address: string | null;
  open: boolean;
  show: (address: string) => void;
  close: () => void;
};

export const useWalletDrawer = create<State>((set) => ({
  address: null,
  open: false,
  show: (address) => set({ address, open: true }),
  close: () => set({ open: false }),
}));
```

> If `zustand` isn't already in `frontend/package.json`, add it: `cd frontend && npm i zustand`. Otherwise skip.

- [ ] **Step 4: Implement `<AddressLink>`**

Create `frontend/src/components/AddressLink.tsx`:

```tsx
import { useWalletDrawer } from "../state/walletDrawer";

type Props = {
  address: string;
  className?: string;
  /** Optional override for the visible text (e.g. an existing label). */
  label?: string | null;
};

function truncate(addr: string): string {
  if (addr.length < 10) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export default function AddressLink({ address, className, label }: Props) {
  const show = useWalletDrawer((s) => s.show);
  return (
    <button
      type="button"
      onClick={() => show(address)}
      className={
        "font-mono tabular-nums underline decoration-dotted underline-offset-2 " +
        "hover:text-brand-soft transition " +
        (className ?? "")
      }
      title={address}
    >
      {label ?? truncate(address)}
    </button>
  );
}
```

- [ ] **Step 5: Run test, expect pass**

Run: `cd frontend && npm run test -- AddressLink`
Expected: PASS (or, if no test runner configured, run `npm run build`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/state/walletDrawer.ts \
        frontend/src/components/AddressLink.tsx \
        frontend/src/components/__tests__/AddressLink.test.tsx
git commit -m "feat(clusters): AddressLink component + zustand drawer state"
```

---

## Task 12 — Frontend: `<WalletDrawer>` component

**Files:**
- Create: `frontend/src/components/WalletDrawer.tsx`
- Create: `frontend/src/components/__tests__/WalletDrawer.test.tsx`
- Modify: `frontend/src/App.tsx` (mount drawer at root)

- [ ] **Step 1: Write the test**

Create `frontend/src/components/__tests__/WalletDrawer.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import WalletDrawer from "../WalletDrawer";
import { useWalletDrawer } from "../../state/walletDrawer";

vi.mock("../../api", () => ({
  fetchCluster: vi.fn(async (addr: string) => ({
    address: addr,
    computed_at: new Date().toISOString(),
    stale: false,
    labels: ["Whale"],
    gas_funder: null,
    cex_deposits: [],
    linked_wallets: [
      {
        address: "0xabc",
        label: null,
        confidence: "strong",
        reasons: ["shared_cex_deposit:binance:0xfwd"],
      },
    ],
    stats: { first_seen: null, last_seen: null, tx_count: 0 },
  })),
  refreshCluster: vi.fn(),
}));

function withQuery(node: React.ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

describe("WalletDrawer", () => {
  it("renders nothing when closed", () => {
    useWalletDrawer.setState({ address: null, open: false });
    const { container } = render(withQuery(<WalletDrawer />));
    expect(container.firstChild).toBeNull();
  });

  it("renders cluster body when open", async () => {
    useWalletDrawer.setState({ address: "0xtarget", open: true });
    render(withQuery(<WalletDrawer />));
    expect(await screen.findByText(/Whale/)).toBeInTheDocument();
    expect(await screen.findByText(/strong/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd frontend && npm run test -- WalletDrawer`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the drawer**

Create `frontend/src/components/WalletDrawer.tsx`:

```tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCluster,
  refreshCluster,
  type ClusterResult,
  type LinkedWallet,
} from "../api";
import { useWalletDrawer } from "../state/walletDrawer";

function ConfidenceChip({ confidence }: { confidence: LinkedWallet["confidence"] }) {
  const cls =
    confidence === "strong"
      ? "bg-up/15 text-up ring-up/30"
      : "bg-amber-400/15 text-amber-300 ring-amber-400/30";
  return (
    <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wider rounded ring-1 ${cls}`}>
      {confidence}
    </span>
  );
}

function ReasonLine({ reasons }: { reasons: string[] }) {
  return (
    <div className="text-[11px] text-slate-500 font-mono truncate">
      {reasons.map((r, i) => {
        const [kind, ...rest] = r.split(":");
        const human =
          kind === "shared_cex_deposit"
            ? `shared CEX deposit (${rest[0]})`
            : kind === "shared_gas_funder"
              ? `shared gas funder ${rest[0].slice(0, 6)}…`
              : r;
        return (
          <span key={i}>
            {human}
            {i < reasons.length - 1 ? " · " : ""}
          </span>
        );
      })}
    </div>
  );
}

function Body({ data }: { data: ClusterResult }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Address</div>
        <div className="font-mono text-sm break-all">{data.address}</div>
        {data.labels.length > 0 && (
          <div className="mt-1 flex gap-1 flex-wrap">
            {data.labels.map((l) => (
              <span key={l} className="px-1.5 py-0.5 text-[10px] rounded bg-brand/20 text-brand-soft">
                {l}
              </span>
            ))}
          </div>
        )}
      </div>

      {data.stale && (
        <div className="rounded ring-1 ring-amber-400/30 bg-amber-400/10 px-3 py-2 text-[12px] text-amber-200">
          Showing stale result — Etherscan unavailable.
          Computed {new Date(data.computed_at).toLocaleString()}.
        </div>
      )}

      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">
          Linked wallets ({data.linked_wallets.length})
        </div>
        {data.linked_wallets.length === 0 ? (
          <div className="text-sm text-slate-500">
            No linked wallets found. Common for fresh wallets and wallets funded
            only via public services.
          </div>
        ) : (
          <ul className="divide-y divide-surface-divider">
            {data.linked_wallets.map((lw) => (
              <li key={lw.address} className="py-2 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-sm truncate">
                    {lw.label ?? lw.address}
                  </div>
                  <ReasonLine reasons={lw.reasons} />
                </div>
                <ConfidenceChip confidence={lw.confidence} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">Stats</div>
        <dl className="grid grid-cols-2 gap-y-1 text-[12px]">
          <dt className="text-slate-500">tx count (sample)</dt>
          <dd className="font-mono tabular-nums">{data.stats.tx_count}</dd>
          <dt className="text-slate-500">first seen</dt>
          <dd className="font-mono tabular-nums">
            {data.stats.first_seen ? new Date(data.stats.first_seen).toLocaleDateString() : "—"}
          </dd>
          <dt className="text-slate-500">last seen</dt>
          <dd className="font-mono tabular-nums">
            {data.stats.last_seen ? new Date(data.stats.last_seen).toLocaleDateString() : "—"}
          </dd>
        </dl>
      </div>
    </div>
  );
}

export default function WalletDrawer() {
  const open = useWalletDrawer((s) => s.open);
  const address = useWalletDrawer((s) => s.address);
  const close = useWalletDrawer((s) => s.close);
  const qc = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["cluster", address],
    queryFn: () => fetchCluster(address!),
    enabled: open && !!address,
    refetchOnWindowFocus: false,
  });

  if (!open || !address) return null;

  async function handleRefresh() {
    if (!address) return;
    await refreshCluster(address);
    qc.invalidateQueries({ queryKey: ["cluster", address] });
    refetch();
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={close}>
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        aria-hidden
      />
      <aside
        className="relative z-50 w-full max-w-md h-full bg-surface-base ring-1 ring-surface-border shadow-2xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-surface-divider">
          <div className="font-medium text-slate-200">Wallet</div>
          <div className="flex items-center gap-2">
            <a
              href={`https://etherscan.io/address/${address}`}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] text-slate-400 hover:text-brand-soft underline decoration-dotted"
            >
              Etherscan ↗
            </a>
            <button
              type="button"
              onClick={handleRefresh}
              className="text-[12px] text-slate-400 hover:text-brand-soft"
            >
              ↻ Refresh
            </button>
            <button
              type="button"
              onClick={close}
              className="text-slate-400 hover:text-slate-100 text-lg leading-none px-1"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="p-5">
          {isLoading && <div className="text-sm text-slate-500">loading…</div>}
          {error && <div className="text-sm text-down">unavailable — try again</div>}
          {data && <Body data={data} />}
        </div>
      </aside>
    </div>
  );
}
```

- [ ] **Step 4: Mount the drawer at app root**

Edit `frontend/src/App.tsx`. Import:

```tsx
import WalletDrawer from "./components/WalletDrawer";
```

Add `<WalletDrawer />` near the very end of the rendered tree, just before the closing wrapper element. (It positions itself fixed; mount once at root.)

- [ ] **Step 5: Run, expect pass**

Run: `cd frontend && npm run test -- WalletDrawer`
Expected: PASS.
Then run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WalletDrawer.tsx \
        frontend/src/components/__tests__/WalletDrawer.test.tsx \
        frontend/src/App.tsx
git commit -m "feat(clusters): WalletDrawer component mounted at root"
```

---

## Task 13 — Wire `<AddressLink>` into existing panels

**Files:**
- Modify: `frontend/src/components/WhaleTransfersPanel.tsx`
- Modify: `frontend/src/components/SmartMoneyLeaderboardPanel.tsx`

- [ ] **Step 1: Inspect existing address rendering in WhaleTransfersPanel**

Run: `grep -n "from_addr\|to_addr\|from \|to " frontend/src/components/WhaleTransfersPanel.tsx | head -30`

- [ ] **Step 2: Replace raw address rendering with `<AddressLink>` in WhaleTransfersPanel**

Import:

```tsx
import AddressLink from "./AddressLink";
```

For each location that currently renders an address as text (typically a `<span className="font-mono">{truncate(addr)}</span>` or similar), replace with:

```tsx
<AddressLink address={addr} label={existingLabelOrNull} />
```

If the panel has its own truncation/label logic, prefer the existing label (pass it as the `label` prop) and let `AddressLink` handle truncation when no label exists.

Apply to **all** rows: confirmed transfers AND the pending section at the top (both `from_addr` and `to_addr`).

- [ ] **Step 3: Same for SmartMoneyLeaderboardPanel**

Import `AddressLink` and replace the wallet-address render in each row with:

```tsx
<AddressLink address={entry.wallet} label={entry.label} />
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 5: Manual smoke test**

Run: `make up` (or whatever brings the stack up locally).
Open `http://localhost:5173`, log in, click an address in the whale panel. Drawer should slide in from the right and show "loading…" then either a cluster body or an "unavailable" message (depending on whether `ETHERSCAN_API_KEY` is set in `.env`).

If `ETHERSCAN_API_KEY` is unset, the drawer correctly shows the 503 "unavailable" message — set the key to test the happy path.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WhaleTransfersPanel.tsx \
        frontend/src/components/SmartMoneyLeaderboardPanel.tsx
git commit -m "feat(clusters): wire AddressLink into whale + smart-money panels"
```

---

## Task 14 — Close v2 in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Flip the wallet-clustering bullet to ✅**

Replace the line:

```
- v2-wallet-clustering 🚧 design approved 2026-05-01; ...
```

with:

```
- v2-wallet-clustering ✅ On-demand wallet drawer (Etherscan-backed, sync, 7d Postgres cache); shared gas-funder + same-CEX-deposit heuristics suppress public funders via static denylist; clickable addresses across whale + smart-money panels; daily purge cron drops rows past grace window. Requires `ETHERSCAN_API_KEY` in `.env`. Spec: `docs/superpowers/specs/2026-05-01-wallet-clustering-design.md`.
```

And below the v2 list (where the "v2 pending — wallet clustering, ..." line used to be), add:

```
**v2 complete.**
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(clusters): mark v2 complete in CLAUDE.md"
```

---

## Self-review (executed by the plan author, not the implementer)

**Spec coverage:**
- §UX: covered by Tasks 11–13 (`AddressLink`, `WalletDrawer`, panel wiring).
- §Heuristics H1: Task 5 (`gas_funder.py`) + Task 7 engine integration.
- §Heuristics H2: Task 6 (`cex_deposit.py`) + Task 7 engine integration.
- §Heuristics H3 (label enrichment): Task 7 (`cluster_engine.py` calls `label_for`).
- §Public-funder denylist: Task 4.
- §Architecture / engine flow: Task 7.
- §API: Task 8 (routes + cache + stale fallback).
- §Data model: Task 2 (model + migration).
- §Caching (purge cron): Task 9.
- §Etherscan client: Task 3.
- §Configuration: Task 1.
- §Tests: each implementation task ships its own pytest file; frontend tests in Tasks 11–12.
- §Risks / known limits: addressed implicitly (denylist, stale fallback, capped traversal). No code change needed.
- §Future work: explicitly out of scope.
- §UI surfaces (Q4=B): Task 13 covers whale + smart-money panels. Pending panel uses the same component as whale (it's a section *within* `WhaleTransfersPanel.tsx`) so step 2 of Task 13 covers it.

**Placeholder scan:** none — every step has explicit code or commands.

**Type consistency:**
- `ClusterResult`, `LinkedWallet`, `GasFunderInfo`, `CexDepositInfo`, `ClusterStats` defined identically in `backend/app/api/schemas.py` (Task 7) and `frontend/src/api.ts` (Task 10).
- `FunderInfo` (Task 5) is internal to the engine — not surfaced over the wire.
- `DepositMatch` (Task 6) is internal to the engine — translated to `CexDepositInfo` in the engine (Task 7).
- Engine signature `cluster_engine.compute(client, address, *, max_linked, max_deposit_candidates, funder_strong_threshold)` — matches API call site in Task 8.
- `find_co_funded_wallets(client, funder, *, target, limit)` — matches engine call site in Task 7.
- `find_co_depositors(client, *, deposit_address, target, limit)` — matches engine call site in Task 7.
- `find_deposit_addresses(client, target, *, max_candidates)` — matches engine call site in Task 7.
- `find_first_funder(client, target)` — matches engine call site in Task 7.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-wallet-clustering.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batched checkpoints for review.

**Which approach?**
