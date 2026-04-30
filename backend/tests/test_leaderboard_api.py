"""API tests for /api/leaderboard/smart-money."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import SmartMoneyLeaderboard


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(SmartMoneyLeaderboard).delete()
        s.commit()
        yield s


def _seed(session, *, run_id, snapshot_at, entries):
    for rank, (wallet, pnl) in enumerate(entries, start=1):
        session.add(SmartMoneyLeaderboard(
            run_id=run_id,
            snapshot_at=snapshot_at,
            window_days=30,
            rank=rank,
            wallet_address=wallet,
            label=None,
            realized_pnl_usd=Decimal(str(pnl)),
            unrealized_pnl_usd=None,
            win_rate=Decimal("0.5000"),
            trade_count=2,
            volume_usd=Decimal("100000.00"),
            weth_bought=Decimal("10"),
            weth_sold=Decimal("10"),
        ))
    session.commit()


def test_returns_latest_snapshot_only(session, auth_client):
    old_run = uuid.uuid4()
    new_run = uuid.uuid4()
    old_ts = datetime(2026, 4, 23, 3, 0, tzinfo=UTC)
    new_ts = datetime(2026, 4, 24, 3, 0, tzinfo=UTC)
    _seed(session, run_id=old_run, snapshot_at=old_ts,
          entries=[("0xold1", 100.00), ("0xold2", 50.00)])
    _seed(session, run_id=new_run, snapshot_at=new_ts,
          entries=[("0xnew1", 500.00)])

    r = auth_client.get("/api/leaderboard/smart-money")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_at"].startswith("2026-04-24")
    assert body["window_days"] == 30
    assert len(body["entries"]) == 1
    assert body["entries"][0]["wallet"] == "0xnew1"
    assert body["entries"][0]["rank"] == 1
    assert body["entries"][0]["realized_pnl_usd"] == 500.0


def test_empty_when_no_snapshots(session, auth_client):
    r = auth_client.get("/api/leaderboard/smart-money")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_at"] is None
    assert body["entries"] == []


def test_limit_clamps(session, auth_client):
    run = uuid.uuid4()
    ts = datetime(2026, 4, 24, 3, 0, tzinfo=UTC)
    _seed(session, run_id=run, snapshot_at=ts,
          entries=[(f"0x{i:040x}", 100.00 - i) for i in range(20)])

    r = auth_client.get("/api/leaderboard/smart-money?limit=5")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 5

    # Max is 50
    r = auth_client.get("/api/leaderboard/smart-money?limit=9999")
    assert r.status_code == 422  # pydantic validation error
