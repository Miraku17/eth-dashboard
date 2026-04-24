from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import NetworkActivity
from app.main import app


@pytest.fixture
def seeded_network(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2)
    with Session() as s:
        s.query(NetworkActivity).delete()
        for i in range(10):
            s.add(
                NetworkActivity(
                    ts=base + timedelta(seconds=12 * i),
                    tx_count=200 + i,
                    gas_price_gwei=Decimal("25.5"),
                    base_fee=Decimal("24.5"),
                )
            )
        s.commit()
        yield s


def test_network_summary(seeded_network):
    client = TestClient(app)
    r = client.get("/api/network/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["latest_ts"] is not None
    assert body["tx_count"] == 209  # last one seeded
    assert body["gas_price_gwei"] == 25.5
    assert body["base_fee_gwei"] == 24.5
    # 10 rows spaced 12s → avg_block ≈ 12s
    assert body["avg_block_seconds"] == pytest.approx(12.0, abs=0.1)
    assert body["avg_tx_per_block"] == pytest.approx(204.5)


def test_network_summary_empty(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(NetworkActivity).delete()
        s.commit()
    r = TestClient(app).get("/api/network/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["latest_ts"] is None
    assert body["gas_price_gwei"] is None


def test_network_series(seeded_network):
    client = TestClient(app)
    r = client.get("/api/network/series?hours=1")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 10
    # Ascending by ts
    tss = [p["ts"] for p in points]
    assert tss == sorted(tss)


def test_health_reports_sources(seeded_network):
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    names = {s["name"] for s in body["sources"]}
    assert names == {"binance_1m", "dune_flows", "alchemy_blocks", "whale_transfers", "smart_money"}
    blocks = next(s for s in body["sources"] if s["name"] == "alchemy_blocks")
    assert blocks["stale"] is False
    assert blocks["lag_seconds"] < 600
