"""Integration tests for leaderboard_sync: Dune rows → FIFO engine → Postgres."""
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.models import SmartMoneyLeaderboard
from app.services.leaderboard_sync import persist_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "dune_smart_money_sample.json"


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(SmartMoneyLeaderboard).delete()
        s.commit()
        yield s


def test_persist_snapshot_ranks_by_realized_pnl(session):
    rows = json.loads(FIXTURE.read_text())
    run_id = persist_snapshot(
        session,
        rows=rows,
        window_days=30,
        window_end_eth_price=Decimal("3500"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    assert run_id is not None
    records = (
        session.query(SmartMoneyLeaderboard)
        .order_by(SmartMoneyLeaderboard.rank)
        .all()
    )
    assert len(records) == 3
    # 0xaaa: +5000, 0xccc: +1500, 0xbbb: -1000
    assert records[0].wallet_address == "0xaaa"
    assert records[0].rank == 1
    assert float(records[0].realized_pnl_usd) == 5000.00
    assert records[1].wallet_address == "0xccc"
    assert records[2].wallet_address == "0xbbb"
    assert float(records[2].realized_pnl_usd) == -1000.00
    # All rows share the same run_id + snapshot_at.
    assert len({r.run_id for r in records}) == 1
    assert len({r.snapshot_at for r in records}) == 1
    # Label denormalization preserved.
    bbb = next(r for r in records if r.wallet_address == "0xbbb")
    assert bbb.label == "Jump Trading"


def test_persist_snapshot_truncates_to_top_50(session):
    # Build 75 synthetic wallets with decreasing PnL.
    rows = []
    for i in range(75):
        w = f"0x{i:040x}"
        rows.append({
            "trader": w, "block_time": "2026-04-01T00:00:00Z",
            "side": "buy", "weth_amount": "1",
            "amount_usd": str(3000),
            "label": None,
        })
        rows.append({
            "trader": w, "block_time": "2026-04-02T00:00:00Z",
            "side": "sell", "weth_amount": "1",
            # Decreasing profit as i increases: wallet 0 makes +74, wallet 74 makes +0.
            "amount_usd": str(3000 + (74 - i)),
            "label": None,
        })
    persist_snapshot(
        session, rows=rows, window_days=30,
        window_end_eth_price=Decimal("3000"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    rows_written = session.query(SmartMoneyLeaderboard).count()
    assert rows_written == 50
    top = session.query(SmartMoneyLeaderboard).filter_by(rank=1).one()
    assert top.wallet_address == f"0x{0:040x}"


def test_persist_snapshot_skips_on_empty_rows(session):
    run_id = persist_snapshot(
        session, rows=[], window_days=30,
        window_end_eth_price=Decimal("3500"),
        snapshot_at=datetime(2026, 4, 24, 3, 0, tzinfo=UTC),
    )
    assert run_id is None
    assert session.query(SmartMoneyLeaderboard).count() == 0
