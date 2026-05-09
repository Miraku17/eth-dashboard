from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import DerivativesSnapshot, PerpLiquidation


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


def test_summary_endpoint(seeded, auth_client):
    r = auth_client.get("/api/derivatives/summary")
    assert r.status_code == 200
    body = r.json()
    # Latest row per exchange
    assert len(body["latest"]) == 2
    ex = {row["exchange"]: row for row in body["latest"]}
    assert ex["binance"]["oi_usd"] == 1_000_000_000
    assert ex["bybit"]["funding_rate"] == -0.0002
    assert body["total_oi_usd"] == 1_500_000_000
    assert body["avg_funding_rate"] == pytest.approx((0.0001 - 0.0002) / 2)


def test_summary_empty(migrated_engine, auth_client):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(DerivativesSnapshot).delete()
        s.commit()
    r = auth_client.get("/api/derivatives/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] == []
    assert body["total_oi_usd"] is None


def test_series_endpoint(seeded, auth_client):
    r = auth_client.get("/api/derivatives/series?hours=24")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 4  # 2 hours × 2 exchanges


def test_series_exchange_filter(seeded, auth_client):
    r = auth_client.get("/api/derivatives/series?hours=24&exchange=binance")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 2
    assert {p["exchange"] for p in points} == {"binance"}


def _seed_liquidation(session, ts, side="long", notional=Decimal("50000")):
    session.add(PerpLiquidation(
        ts=ts, venue="binance", symbol="ETHUSDT", side=side,
        price=Decimal("2500"), qty=notional / Decimal("2500"),
        notional_usd=notional,
    ))


def test_liquidations_listener_fresh(migrated_engine, auth_client):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PerpLiquidation).delete()
        _seed_liquidation(s, datetime.now(UTC) - timedelta(minutes=5))
        s.commit()

    r = auth_client.get("/api/derivatives/liquidations?hours=24")
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["listener_stale"] is False
    assert summary["last_event_ts"] is not None


def test_liquidations_listener_stale(migrated_engine, auth_client):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PerpLiquidation).delete()
        # Last event a year ago — way past the 6h stale threshold.
        _seed_liquidation(s, datetime.now(UTC) - timedelta(days=365))
        s.commit()

    r = auth_client.get("/api/derivatives/liquidations?hours=24")
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["listener_stale"] is True
    # The chart window is 24h so the year-old event must NOT appear in buckets.
    assert r.json()["buckets"] == []


def test_liquidations_listener_empty_table(migrated_engine, auth_client):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(PerpLiquidation).delete()
        s.commit()

    r = auth_client.get("/api/derivatives/liquidations?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["listener_stale"] is True
    assert body["summary"]["last_event_ts"] is None
    assert body["buckets"] == []
