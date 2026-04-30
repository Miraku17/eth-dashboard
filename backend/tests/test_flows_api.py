from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import ExchangeFlow, OnchainVolume, StablecoinFlow


@pytest.fixture
def seeded(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    ts = datetime(2026, 4, 23, 10, 0, tzinfo=UTC)
    with Session() as s:
        s.query(ExchangeFlow).delete()
        s.query(StablecoinFlow).delete()
        s.query(OnchainVolume).delete()
        s.add(ExchangeFlow(exchange="Binance", direction="in", asset="ETH", ts_bucket=ts, usd_value=Decimal("12000000")))
        s.add(StablecoinFlow(asset="USDT", direction="in", ts_bucket=ts, usd_value=Decimal("340000000")))
        s.add(OnchainVolume(asset="ETH", ts_bucket=ts, tx_count=1_234_567, usd_value=Decimal("4500000000")))
        s.commit()
        yield s


def test_exchange_endpoint(seeded, auth_client):
    r = auth_client.get("/api/flows/exchange")
    assert r.status_code == 200
    data = r.json()
    assert len(data["points"]) == 1
    assert data["points"][0]["exchange"] == "Binance"


def test_stablecoins_endpoint(seeded, auth_client):
    r = auth_client.get("/api/flows/stablecoins")
    assert r.status_code == 200
    assert r.json()["points"][0]["asset"] == "USDT"


def test_onchain_volume_endpoint(seeded, auth_client):
    r = auth_client.get("/api/flows/onchain-volume")
    assert r.status_code == 200
    assert r.json()["points"][0]["tx_count"] == 1_234_567
