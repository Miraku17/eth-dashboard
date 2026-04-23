from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.models import Transfer
from app.main import app


@pytest.fixture
def seeded_transfers(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with Session() as s:
        s.query(Transfer).delete()
        s.add(
            Transfer(
                tx_hash="0xaaa",
                log_index=0,
                block_number=100,
                ts=now - timedelta(minutes=10),
                from_addr="0x0000000000000000000000000000000000000001",
                to_addr="0x28c6c06298d514db089934071355e5743bf21d60",  # Binance 14
                asset="ETH",
                amount=Decimal("1000"),
                usd_value=Decimal("3000000"),
            )
        )
        s.add(
            Transfer(
                tx_hash="0xbbb",
                log_index=1,
                block_number=101,
                ts=now - timedelta(hours=2),
                from_addr="0x71660c4005ba85c37ccec55d0c4493e66fe775d3",  # Coinbase
                to_addr="0x0000000000000000000000000000000000000002",
                asset="USDC",
                amount=Decimal("2500000"),
                usd_value=Decimal("2500000"),
            )
        )
        s.commit()
        yield s


def test_whales_transfers_endpoint(seeded_transfers):
    client = TestClient(app)
    r = client.get("/api/whales/transfers?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert len(body["transfers"]) == 2
    # newest first
    assert body["transfers"][0]["tx_hash"] == "0xaaa"
    assert body["transfers"][0]["to_label"] == "Binance 14"
    assert body["transfers"][1]["from_label"] == "Coinbase 1"


def test_whales_transfers_asset_filter(seeded_transfers):
    client = TestClient(app)
    r = client.get("/api/whales/transfers?asset=usdc")
    assert r.status_code == 200
    body = r.json()
    assert len(body["transfers"]) == 1
    assert body["transfers"][0]["asset"] == "USDC"
