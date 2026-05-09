"""Tests for /api/smart-money/direction.

Confirms the endpoint joins dex_swap × wallet_score correctly so only
above-floor wallets count toward the 24h totals, and that the daily
sparkline shape is stable (always 7 buckets, oldest-first).
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import DexSwap, WalletScore


SMART_WALLET = "0x0000000000000000000000000000000000000aaa"
NOISE_WALLET = "0x0000000000000000000000000000000000000bbb"


@pytest.fixture
def seeded(migrated_engine):
    """One above-floor wallet (`SMART_WALLET`, score $250k) buys + sells
    today; one below-floor wallet (`NOISE_WALLET`, score $5k) also trades
    — its volume must NOT contribute to the headline."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with Session() as s:
        s.query(WalletScore).delete()
        s.query(DexSwap).delete()

        s.add(
            WalletScore(
                wallet=SMART_WALLET,
                trades_30d=42,
                volume_usd_30d=Decimal("5000000"),
                realized_pnl_30d=Decimal("250000"),
                win_rate_30d=0.6,
                score=250_000.0,
                updated_at=now,
            )
        )
        s.add(
            WalletScore(
                wallet=NOISE_WALLET,
                trades_30d=10,
                volume_usd_30d=Decimal("100000"),
                realized_pnl_30d=Decimal("5000"),
                win_rate_30d=0.4,
                score=5_000.0,  # below the $100k floor
                updated_at=now,
            )
        )

        # Smart wallet: $400k bought + $100k sold within 24h → net +$300k
        s.add(DexSwap(
            tx_hash="0x" + "a" * 64, log_index=0, ts=now - timedelta(hours=2),
            wallet=SMART_WALLET, dex="uniswap_v3", side="buy",
            weth_amount=Decimal("100"), usd_value=Decimal("400000"),
        ))
        s.add(DexSwap(
            tx_hash="0x" + "b" * 64, log_index=0, ts=now - timedelta(hours=4),
            wallet=SMART_WALLET, dex="uniswap_v3", side="sell",
            weth_amount=Decimal("25"), usd_value=Decimal("100000"),
        ))
        # Noise wallet swaps a fortune — must be excluded from totals.
        s.add(DexSwap(
            tx_hash="0x" + "c" * 64, log_index=0, ts=now - timedelta(hours=1),
            wallet=NOISE_WALLET, dex="uniswap_v3", side="buy",
            weth_amount=Decimal("500"), usd_value=Decimal("2000000"),
        ))
        s.commit()
        yield s


def test_direction_24h_excludes_below_floor_wallets(seeded, auth_client):
    r = auth_client.get("/api/smart-money/direction")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bought_usd_24h"] == 400_000.0
    assert body["sold_usd_24h"] == 100_000.0
    assert body["net_usd_24h"] == 300_000.0
    assert body["smart_wallets_active_24h"] == 1
    assert body["min_score"] == 100_000.0


def test_direction_sparkline_has_seven_buckets(seeded, auth_client):
    """The daily series must always carry 7 oldest-first buckets, even
    when most days have no smart-money activity (zero-fill)."""
    r = auth_client.get("/api/smart-money/direction")
    body = r.json()
    sparkline = body["sparkline_7d"]
    assert len(sparkline) == 7
    # Oldest first: dates strictly increase.
    dates = [p["date"] for p in sparkline]
    assert dates == sorted(dates)
    # Today's bucket carries the seeded swaps.
    today = datetime.now(UTC).date().isoformat()
    today_bucket = next(p for p in sparkline if p["date"] == today)
    assert today_bucket["bought_usd"] == 400_000.0
    assert today_bucket["sold_usd"] == 100_000.0
    assert today_bucket["net_usd"] == 300_000.0


def test_direction_no_smart_wallets_returns_zeros(auth_client, migrated_engine):
    """Empty wallet_score table → endpoint succeeds and returns zeros
    (not 500). Useful for fresh dev DBs where the cron hasn't run yet."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletScore).delete()
        s.query(DexSwap).delete()
        s.commit()

    r = auth_client.get("/api/smart-money/direction")
    assert r.status_code == 200
    body = r.json()
    assert body["bought_usd_24h"] == 0.0
    assert body["sold_usd_24h"] == 0.0
    assert body["net_usd_24h"] == 0.0
    assert body["smart_wallets_active_24h"] == 0
    assert len(body["sparkline_7d"]) == 7
