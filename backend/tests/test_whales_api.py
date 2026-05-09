from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import Transfer, WalletScore


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


def test_whales_transfers_endpoint(seeded_transfers, auth_client):
    r = auth_client.get("/api/whales/transfers?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert len(body["transfers"]) == 2
    # newest first
    assert body["transfers"][0]["tx_hash"] == "0xaaa"
    assert body["transfers"][0]["to_label"] == "Binance 14"
    assert body["transfers"][1]["from_label"] == "Coinbase 1"


def test_whales_transfers_asset_filter(seeded_transfers, auth_client):
    r = auth_client.get("/api/whales/transfers?asset=usdc")
    assert r.status_code == 200
    body = r.json()
    assert len(body["transfers"]) == 1
    assert body["transfers"][0]["asset"] == "USDC"


@pytest.fixture
def seeded_smart_wallet(seeded_transfers, migrated_engine):
    """Marks the sender of `0xaaa` as smart-money so smart_only filtering
    has a hit; leaves `0xbbb` parties unscored to verify exclusion."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletScore).delete()
        s.add(
            WalletScore(
                wallet="0x0000000000000000000000000000000000000001",
                trades_30d=42,
                volume_usd_30d=Decimal("5000000"),
                realized_pnl_30d=Decimal("250000"),
                win_rate_30d=0.6,
                score=250_000.0,
                updated_at=datetime.now(UTC),
            )
        )
        s.commit()
    yield


def test_whales_transfers_smart_only_filter(seeded_smart_wallet, auth_client):
    """smart_only=true returns only the transfer touching a wallet whose
    score crosses the smart-money floor; the other transfer is excluded
    even though it's within the time window."""
    r = auth_client.get("/api/whales/transfers?smart_only=true&hours=24")
    assert r.status_code == 200
    body = r.json()
    assert len(body["transfers"]) == 1
    assert body["transfers"][0]["tx_hash"] == "0xaaa"
    # Enrichment still attaches scores (existing behaviour, unaffected).
    assert body["transfers"][0]["from_score"] == 250_000.0


def test_whales_transfers_smart_only_excludes_below_floor(
    seeded_transfers, migrated_engine, auth_client
):
    """A wallet scored below SMART_FLOOR_USD must not be matched."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletScore).delete()
        s.add(
            WalletScore(
                wallet="0x0000000000000000000000000000000000000001",
                trades_30d=10,
                volume_usd_30d=Decimal("50000"),
                realized_pnl_30d=Decimal("5000"),
                win_rate_30d=0.5,
                score=5_000.0,  # under the $100k floor
                updated_at=datetime.now(UTC),
            )
        )
        s.commit()
    r = auth_client.get("/api/whales/transfers?smart_only=true&hours=24")
    assert r.status_code == 200
    assert len(r.json()["transfers"]) == 0
