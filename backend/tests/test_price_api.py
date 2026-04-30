from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import PriceCandle


@pytest.fixture
def seeded_session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    base = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    with Session() as s:
        s.query(PriceCandle).delete()
        for i in range(10):
            s.add(PriceCandle(
                symbol="ETHUSDT", timeframe="1h",
                ts=base + timedelta(hours=i),
                open=Decimal("3000"), high=Decimal("3010"),
                low=Decimal("2990"), close=Decimal("3005"),
                volume=Decimal("100"),
            ))
        s.commit()
        yield s


def test_candles_endpoint_returns_ordered_candles(seeded_session, auth_client):
    resp = auth_client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "ETHUSDT"
    assert data["timeframe"] == "1h"
    assert len(data["candles"]) == 5
    times = [c["time"] for c in data["candles"]]
    assert times == sorted(times), "candles must be returned in ascending time order"


def test_candles_endpoint_rejects_invalid_timeframe(seeded_session, auth_client):
    resp = auth_client.get("/api/price/candles", params={"timeframe": "2h", "limit": 5})
    assert resp.status_code == 422


def test_candles_endpoint_default_timeframe_is_1h(seeded_session, auth_client):
    resp = auth_client.get("/api/price/candles")
    assert resp.status_code == 200
    assert resp.json()["timeframe"] == "1h"
