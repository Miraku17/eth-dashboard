from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core import sync_status
from app.core.models import NetworkActivity, PriceCandle
from app.main import app


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(sync_status, "_client", lambda: fake)
    return fake


@pytest.fixture
def fresh_data(migrated_engine, fake_redis):
    """Seed critical sources (price + blocks) + dune sync timestamp so
    the health endpoint reports ok."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    now = datetime.now(UTC).replace(microsecond=0)
    with Session() as s:
        s.query(PriceCandle).delete()
        s.query(NetworkActivity).delete()
        s.add(
            PriceCandle(
                symbol="ETHUSDT",
                timeframe="1m",
                ts=now,
                open=Decimal("3000"),
                high=Decimal("3000"),
                low=Decimal("3000"),
                close=Decimal("3000"),
                volume=Decimal("1"),
            )
        )
        s.add(
            NetworkActivity(
                ts=now,
                tx_count=200,
                gas_price_gwei=Decimal("25"),
                base_fee=Decimal("24"),
            )
        )
        s.commit()
        # Record a fresh Dune sync so the freshness check passes.
        sync_status.record_sync_ok("dune_flows")
        yield s


def test_health_ok(fresh_data):
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    names = [s["name"] for s in body["sources"]]
    assert "dune_flows" in names
    dune = next(s for s in body["sources"] if s["name"] == "dune_flows")
    assert dune["stale"] is False
    # Lag should be small — we just recorded.
    assert dune["lag_seconds"] < 10


def test_health_degraded_when_critical_stale(migrated_engine, fake_redis):
    """No recent price or block data → status=degraded, regardless of Dune."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PriceCandle).delete()
        s.query(NetworkActivity).delete()
        s.commit()
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


def test_dune_stale_when_old_sync_recorded(fresh_data, fake_redis):
    """Older-than-threshold sync timestamp → dune flagged stale. Non-critical,
    so overall status stays ok unless a critical source is also stale."""
    old = (datetime.now(UTC) - timedelta(hours=12)).isoformat()
    fake_redis.store["etherscope:sync_status:dune_flows"] = old
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    dune = next(s for s in body["sources"] if s["name"] == "dune_flows")
    assert dune["stale"] is True


def test_dune_never_synced_reports_stale(migrated_engine, fake_redis):
    """Fresh DB with no Dune sync yet → dune shows no data, stale=True.
    (Matches the old "no data yet" behavior from the newest-bucket check.)"""
    # fake_redis is empty.
    resp = TestClient(app).get("/api/health")
    body = resp.json()
    dune = next(s for s in body["sources"] if s["name"] == "dune_flows")
    assert dune["last_update"] is None
    assert dune["stale"] is True


def test_health_reports_smart_money_source(migrated_engine, fake_redis):
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["sources"]}
    assert "smart_money" in names
