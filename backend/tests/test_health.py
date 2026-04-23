from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import NetworkActivity, PriceCandle
from app.main import app


@pytest.fixture
def fresh_data(migrated_engine):
    """Seed critical sources (price + blocks) with fresh rows so status=ok."""
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
        yield s


def test_health_ok(fresh_data):
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert len(body["sources"]) == 4


def test_health_degraded_when_critical_stale(migrated_engine):
    """No recent price or block data → status=degraded."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PriceCandle).delete()
        s.query(NetworkActivity).delete()
        s.commit()
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
