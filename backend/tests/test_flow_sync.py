import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow
from app.services.flow_sync import (
    upsert_exchange_flows,
    upsert_onchain_volume,
    upsert_stablecoin_flows,
)


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(ExchangeFlow).delete()
        s.query(StablecoinFlow).delete()
        s.query(OnchainVolume).delete()
        s.commit()
        yield s


def test_upsert_exchange_flows(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "in",  "asset": "ETH", "usd_value": 12_000_000},
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "out", "asset": "ETH", "usd_value":  8_000_000},
    ]
    assert upsert_exchange_flows(session, rows) == 2

    rows2 = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "exchange": "Binance", "direction": "in", "asset": "ETH", "usd_value": 15_000_000},
    ]
    upsert_exchange_flows(session, rows2)
    r = session.execute(select(ExchangeFlow).where(ExchangeFlow.direction == "in")).scalar_one()
    assert float(r.usd_value) == 15_000_000


def test_upsert_stablecoin_flows(session):
    rows = [
        {"ts_bucket": "2026-04-23T10:00:00Z", "asset": "USDT", "direction": "in",  "usd_value": 340_000_000},
        {"ts_bucket": "2026-04-23T10:00:00Z", "asset": "USDC", "direction": "out", "usd_value":  80_000_000},
    ]
    assert upsert_stablecoin_flows(session, rows) == 2
    assert session.query(StablecoinFlow).count() == 2


def test_upsert_onchain_volume(session):
    rows = [
        {"ts_bucket": "2026-04-22T00:00:00Z", "asset": "ETH",  "tx_count": 1_234_567, "usd_value": 4_500_000_000},
        {"ts_bucket": "2026-04-22T00:00:00Z", "asset": "USDT", "tx_count":   900_000, "usd_value": 2_100_000_000},
    ]
    assert upsert_onchain_volume(session, rows) == 2
    total = sum(float(r.usd_value) for r in session.execute(select(OnchainVolume)).scalars())
    assert total == 6_600_000_000


def test_upsert_handles_empty_lists(session):
    assert upsert_exchange_flows(session, []) == 0
    assert upsert_stablecoin_flows(session, []) == 0
    assert upsert_onchain_volume(session, []) == 0


def test_upsert_exchange_flows_batches_large_input(session):
    """Regression: a single INSERT with too many rows trips Postgres's
    65,535-bound-param limit. The chunker keeps each statement safely small
    regardless of input size."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 15,000 rows × 5 cols = 75,000 params — over the 65,535 limit if we
    # tried to do it in one statement.
    rows = []
    for i in range(15_000):
        rows.append({
            "ts_bucket": (base + timedelta(minutes=i)).isoformat(),
            "exchange": "Binance",
            "direction": "in" if i % 2 == 0 else "out",
            "asset": "ETH",
            "usd_value": 1_000_000 + i,
        })
    assert upsert_exchange_flows(session, rows) == 15_000
    assert session.query(ExchangeFlow).count() == 15_000


def test_upsert_onchain_volume_batches_large_input(session):
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "ts_bucket": (base + timedelta(minutes=i)).isoformat(),
            "asset": f"TOK{i % 100}",
            "tx_count": i,
            "usd_value": 1_000_000 + i,
        }
        for i in range(10_000)
    ]
    assert upsert_onchain_volume(session, rows) == 10_000
    assert session.query(OnchainVolume).count() == 10_000
