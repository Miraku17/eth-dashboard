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


from unittest.mock import patch


def test_candles_endpoint_caches_response(seeded_session, auth_client):
    """Second call within TTL should NOT re-execute the SQL query."""
    # First call — populates cache
    r1 = auth_client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    assert r1.status_code == 200

    # Patch the SQL execute on the session bound to the request to count calls.
    # The endpoint is sync, so we wrap it via a monkeypatched executor on the engine.
    from app.core.db import get_session

    call_count = {"n": 0}
    real_get_session = get_session

    def counting_get_session():
        for s in real_get_session():
            orig_execute = s.execute

            def counting_execute(*a, **kw):
                call_count["n"] += 1
                return orig_execute(*a, **kw)

            s.execute = counting_execute  # type: ignore[method-assign]
            yield s

    from app.main import app
    app.dependency_overrides[get_session] = counting_get_session
    try:
        r2 = auth_client.get("/api/price/candles", params={"timeframe": "1h", "limit": 5})
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert call_count["n"] == 0, "second call should be served from Redis without DB queries"
