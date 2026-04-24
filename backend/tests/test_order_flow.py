"""Unit + integration tests for DEX order-flow (v2)."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import OrderFlow
from app.main import app
from app.services.flow_sync import upsert_order_flow


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(OrderFlow).delete()
        s.commit()
        yield s


def test_upsert_inserts_buy_and_sell(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "buy", "usd_value": 5_000_000, "trade_count": 123},
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "sell", "usd_value": 3_000_000, "trade_count": 98},
    ]
    assert upsert_order_flow(session, rows) == 2
    assert session.query(OrderFlow).count() == 2


def test_upsert_ignores_unexpected_sides(session):
    """Dune SQL `HAVING side IS NOT NULL` should already exclude these, but
    the upsert is defensive against bad input."""
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "buy", "usd_value": 1_000_000, "trade_count": 10},
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "other", "usd_value": 999, "trade_count": 1},
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": None, "usd_value": 999, "trade_count": 1},
    ]
    assert upsert_order_flow(session, rows) == 1
    assert session.query(OrderFlow).count() == 1


def test_upsert_upserts_on_conflict(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "buy", "usd_value": 5_000_000, "trade_count": 123},
    ]
    upsert_order_flow(session, rows)
    # Re-run with updated numbers.
    rows2 = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "side": "buy", "usd_value": 8_000_000, "trade_count": 200},
    ]
    upsert_order_flow(session, rows2)
    r = session.query(OrderFlow).one()
    assert float(r.usd_value) == 8_000_000
    assert r.trade_count == 200


def test_api_returns_recent_buckets(session):
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for h in range(3):
        ts = now - timedelta(hours=h)
        session.add(OrderFlow(
            ts_bucket=ts, side="buy",
            usd_value=Decimal(str(1_000_000 * (h + 1))),
            trade_count=10 * (h + 1),
        ))
        session.add(OrderFlow(
            ts_bucket=ts, side="sell",
            usd_value=Decimal(str(500_000 * (h + 1))),
            trade_count=5 * (h + 1),
        ))
    session.commit()

    r = TestClient(app).get("/api/flows/order-flow?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 6
    # Ascending by ts_bucket so the frontend can chart without re-sorting.
    tss = [p["ts_bucket"] for p in body["points"]]
    assert tss == sorted(tss)


def test_api_empty(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(OrderFlow).delete()
        s.commit()
    r = TestClient(app).get("/api/flows/order-flow")
    assert r.status_code == 200
    assert r.json()["points"] == []
