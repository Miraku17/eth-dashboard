"""Integration tests for /api/copy-trading endpoints."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import OnchainPerpEvent, PerpWalletScore, PerpWatchlist


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(OnchainPerpEvent).delete()
        s.query(PerpWalletScore).delete()
        s.query(PerpWatchlist).delete()
        s.commit()
        yield s


def _seed_score(session, wallet: str, **overrides) -> None:
    defaults = dict(
        wallet=wallet, trades_90d=50, win_rate_90d=Decimal("0.7"),
        win_rate_long_90d=Decimal("0.75"), win_rate_short_90d=Decimal("0.6"),
        realized_pnl_90d=Decimal("50000"), avg_hold_secs=900,
        avg_position_usd=Decimal("40000"), avg_leverage=Decimal("8"),
    )
    defaults.update(overrides)
    session.add(PerpWalletScore(**defaults))
    session.commit()


def test_config_returns_constants(session, auth_client):
    r = auth_client.get("/api/copy-trading/config")
    assert r.status_code == 200
    data = r.json()
    assert data["lookback_days"] == 90
    assert data["min_trades"] == 30
    assert data["min_win_rate"] == 0.60
    assert data["min_pnl_usd"] == 10000
    assert data["default_watch_notional_usd"] == 25000


def test_leaderboard_applies_filters(session, auth_client):
    _seed_score(session, "0x" + "a" * 40, realized_pnl_90d=Decimal("80000"))
    # Below trades threshold:
    _seed_score(session, "0x" + "b" * 40, trades_90d=10)
    # Below win-rate threshold:
    _seed_score(session, "0x" + "c" * 40, win_rate_90d=Decimal("0.4"))
    r = auth_client.get("/api/copy-trading/leaderboard")
    assert r.status_code == 200
    wallets = [row["wallet"] for row in r.json()]
    assert "0x" + "a" * 40 in wallets
    assert "0x" + "b" * 40 not in wallets
    assert "0x" + "c" * 40 not in wallets


def test_watchlist_crud(session, auth_client):
    addr = "0x" + "d" * 40
    # add
    r = auth_client.post("/api/copy-trading/watchlist", json={"wallet": addr, "label": "alice"})
    assert r.status_code == 201
    assert r.json()["min_notional_usd"] == 25000.0
    # duplicate
    r = auth_client.post("/api/copy-trading/watchlist", json={"wallet": addr})
    assert r.status_code == 409
    # patch
    r = auth_client.patch(f"/api/copy-trading/watchlist/{addr}", json={"min_notional_usd": 50000})
    assert r.status_code == 200
    assert r.json()["min_notional_usd"] == 50000.0
    # list
    r = auth_client.get("/api/copy-trading/watchlist")
    assert any(row["wallet"] == addr for row in r.json())
    # delete
    r = auth_client.delete(f"/api/copy-trading/watchlist/{addr}")
    assert r.status_code == 204
    r = auth_client.get("/api/copy-trading/watchlist")
    assert not any(row["wallet"] == addr for row in r.json())


def test_wallet_detail_returns_histogram(session, auth_client):
    addr = "0x" + "e" * 40
    _seed_score(session, addr)
    base_ts = datetime.now(UTC) - timedelta(days=1)
    session.add_all([
        OnchainPerpEvent(
            ts=base_ts, venue="gmx_v2", account=addr, market="ETH-USD",
            event_kind="open", side="long",
            size_usd=Decimal("10000"), size_after_usd=Decimal("10000"),
            collateral_usd=Decimal("1000"), leverage=Decimal("10"),
            price_usd=Decimal("3000"), pnl_usd=None,
            tx_hash="0x" + "1" * 64, log_index=0,
        ),
        OnchainPerpEvent(
            ts=base_ts + timedelta(minutes=10), venue="gmx_v2", account=addr, market="ETH-USD",
            event_kind="close", side="long",
            size_usd=Decimal("10000"), size_after_usd=Decimal("0"),
            collateral_usd=Decimal("1000"), leverage=Decimal("10"),
            price_usd=Decimal("3100"), pnl_usd=Decimal("333"),
            tx_hash="0x" + "2" * 64, log_index=0,
        ),
    ])
    session.commit()
    r = auth_client.get(f"/api/copy-trading/wallets/{addr}")
    assert r.status_code == 200
    data = r.json()
    assert data["score"]["wallet"] == addr
    # 10-minute hold → m5_15 bucket
    assert data["hold_time_histogram"]["m5_15"] == 1
    assert len(data["last_trades"]) == 2
