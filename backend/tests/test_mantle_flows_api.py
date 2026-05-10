"""End-to-end test: seed mantle_order_flow rows, hit the endpoint,
assert response shape + USD aggregation + price-fallback path."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.models import MantleOrderFlow


# ---- local fixture -------------------------------------------------------

import pytest


@pytest.fixture
def test_session_factory(migrated_engine):
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory() as s:
        s.query(MantleOrderFlow).delete()
        s.commit()
    return factory


# ---- helpers --------------------------------------------------------------


def _seed(session, ts: datetime, dex: str, side: str, count: int, mnt_amount: float) -> None:
    session.execute(text("""
        INSERT INTO mantle_order_flow (ts_bucket, dex, side, count, mnt_amount)
        VALUES (:t, :d, :s, :c, :m)
    """), {"t": ts, "d": dex, "s": side, "c": count, "m": mnt_amount})
    session.commit()


# ---- tests ----------------------------------------------------------------


def test_returns_rows_in_window_with_usd_value(test_session_factory, auth_client):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with test_session_factory() as s:
        _seed(s, now,                         "agni", "buy",  10, 100.0)
        _seed(s, now,                         "agni", "sell",  6,  50.0)
        _seed(s, now - timedelta(hours=48),   "agni", "buy",   1,   1.0)  # outside 24h window

    with patch("app.api.mantle_flows.get_mnt_usd", return_value=0.80):
        r = auth_client.get("/api/flows/mantle-order-flow?hours=24")
    assert r.status_code == 200
    body = r.json()

    assert len(body["rows"]) == 2
    by_side = {row["side"]: row for row in body["rows"]}
    assert by_side["buy"]["mnt_amount"] == 100.0
    assert by_side["buy"]["usd_value"]  == 80.0
    assert by_side["sell"]["mnt_amount"] == 50.0
    assert by_side["sell"]["usd_value"]  == 40.0

    summary = body["summary"]
    assert summary["buy_usd"]  == 80.0
    assert summary["sell_usd"] == 40.0
    assert summary["net_usd"]  == 40.0
    assert summary["active_dexes"] == ["agni"]
    assert summary["mnt_usd"]  == 0.80
    assert summary["price_unavailable"] is False


def test_price_unavailable_returns_null_usd(test_session_factory, auth_client):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with test_session_factory() as s:
        _seed(s, now, "agni", "buy", 1, 5.0)

    with patch("app.api.mantle_flows.get_mnt_usd", return_value=None):
        r = auth_client.get("/api/flows/mantle-order-flow?hours=24")
    body = r.json()
    assert body["rows"][0]["usd_value"] is None
    assert body["summary"]["buy_usd"] is None
    assert body["summary"]["price_unavailable"] is True


def test_empty_table_returns_empty_rows(test_session_factory, auth_client):
    with patch("app.api.mantle_flows.get_mnt_usd", return_value=0.80):
        r = auth_client.get("/api/flows/mantle-order-flow?hours=24")
    body = r.json()
    assert body["rows"] == []
    assert body["summary"]["active_dexes"] == []
    assert body["summary"]["buy_usd"] == 0.0
    assert body["summary"]["sell_usd"] == 0.0
