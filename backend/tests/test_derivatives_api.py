from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import DerivativesSnapshot
from app.main import app


@pytest.fixture
def seeded(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    with Session() as s:
        s.query(DerivativesSnapshot).delete()
        # Two hours of data for two exchanges.
        for h in range(2):
            ts = now - timedelta(hours=h)
            s.add(DerivativesSnapshot(
                exchange="binance", symbol="ETHUSDT", ts=ts,
                oi_usd=Decimal("1000000000"),
                funding_rate=Decimal("0.0001"),
                mark_price=Decimal("2300"),
            ))
            s.add(DerivativesSnapshot(
                exchange="bybit", symbol="ETHUSDT", ts=ts,
                oi_usd=Decimal("500000000"),
                funding_rate=Decimal("-0.0002"),
                mark_price=Decimal("2299"),
            ))
        s.commit()
        yield s


def test_summary_endpoint(seeded):
    r = TestClient(app).get("/api/derivatives/summary")
    assert r.status_code == 200
    body = r.json()
    # Latest row per exchange
    assert len(body["latest"]) == 2
    ex = {row["exchange"]: row for row in body["latest"]}
    assert ex["binance"]["oi_usd"] == 1_000_000_000
    assert ex["bybit"]["funding_rate"] == -0.0002
    assert body["total_oi_usd"] == 1_500_000_000
    assert body["avg_funding_rate"] == pytest.approx((0.0001 - 0.0002) / 2)


def test_summary_empty(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(DerivativesSnapshot).delete()
        s.commit()
    r = TestClient(app).get("/api/derivatives/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] == []
    assert body["total_oi_usd"] is None


def test_series_endpoint(seeded):
    r = TestClient(app).get("/api/derivatives/series?hours=24")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 4  # 2 hours × 2 exchanges


def test_series_exchange_filter(seeded):
    r = TestClient(app).get("/api/derivatives/series?hours=24&exchange=binance")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 2
    assert {p["exchange"] for p in points} == {"binance"}
