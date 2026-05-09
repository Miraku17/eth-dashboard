"""Tests for the wallet profile endpoint.

Focused on the v5 wallet_score surfacing — verifies that when the daily
scoring cron has produced a row, the drawer payload carries it (and that
linked-wallet entries decorate inline). The balance/holdings paths are
exercised separately via `wallet_profile.py` unit tests.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import Transfer, WalletCluster, WalletScore


TARGET_ADDR = "0x0000000000000000000000000000000000000abc"
PEER_ADDR = "0x0000000000000000000000000000000000000def"


@pytest.fixture
def seeded_profile(migrated_engine):
    """Seeds a target wallet with a smart-money score and one linked peer
    that's also smart-money — so the drawer can verify both header tile
    and linked-wallet badge code paths in one round-trip.
    """
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    now = datetime.now(UTC).replace(microsecond=0)
    with Session() as s:
        s.query(WalletScore).delete()
        s.query(WalletCluster).delete()
        s.query(Transfer).delete()

        s.add(
            WalletScore(
                wallet=TARGET_ADDR,
                trades_30d=42,
                volume_usd_30d=Decimal("8500000"),
                realized_pnl_30d=Decimal("325000"),
                win_rate_30d=0.61,
                score=325_000.0,
                updated_at=now,
            )
        )
        s.add(
            WalletScore(
                wallet=PEER_ADDR,
                trades_30d=18,
                volume_usd_30d=Decimal("2200000"),
                realized_pnl_30d=Decimal("180000"),
                win_rate_30d=0.55,
                score=180_000.0,
                updated_at=now,
            )
        )
        # Cluster payload mirrors what the clustering engine writes: the
        # profile builder reads `linked_wallets` from this JSON blob and
        # turns it into LinkedWallet rows.
        s.add(
            WalletCluster(
                address=TARGET_ADDR,
                computed_at=now,
                payload={
                    "labels": [],
                    "first_seen": (now - timedelta(days=30)).isoformat(),
                    "last_seen": now.isoformat(),
                    "tx_count": 64,
                    "linked_wallets": [
                        {
                            "address": PEER_ADDR,
                            "label": None,
                            "confidence": "strong",
                            "reasons": ["shared_cex_deposit:Binance"],
                        }
                    ],
                    "gas_funder": None,
                    "cex_deposits": [],
                },
            )
        )
        s.commit()
        yield s


def test_profile_returns_wallet_score(seeded_profile, auth_client):
    """Target wallet's score round-trips through the response."""
    r = auth_client.get(f"/api/wallets/{TARGET_ADDR}/profile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == TARGET_ADDR
    score = body["wallet_score"]
    assert score is not None
    assert score["score"] == 325_000.0
    assert score["realized_pnl_30d"] == 325_000.0
    assert score["win_rate_30d"] == pytest.approx(0.61)
    assert score["trades_30d"] == 42
    assert score["volume_usd_30d"] == 8_500_000.0


def test_profile_decorates_linked_wallets_with_score(seeded_profile, auth_client):
    """Each linked wallet carries its own `score` so the drawer can badge
    smart-money peers inline without a second request."""
    r = auth_client.get(f"/api/wallets/{TARGET_ADDR}/profile")
    assert r.status_code == 200
    linked = r.json()["linked_wallets"]
    assert len(linked) == 1
    assert linked[0]["address"] == PEER_ADDR
    assert linked[0]["score"] == 180_000.0


def test_profile_without_score_returns_null(auth_client, migrated_engine):
    """When the scoring cron hasn't seen this wallet, `wallet_score` is
    omitted (null) — the frontend hides the tile."""
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(WalletScore).delete()
        s.query(WalletCluster).delete()
        s.commit()

    unscored = "0x0000000000000000000000000000000000000999"
    r = auth_client.get(f"/api/wallets/{unscored}/profile")
    assert r.status_code == 200
    assert r.json()["wallet_score"] is None
