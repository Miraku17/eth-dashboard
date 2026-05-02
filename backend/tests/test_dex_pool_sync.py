"""Tests for the dex_pool_tvl upsert path."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import DexPoolTvl
from app.services.dex_pool_sync import upsert_dex_pool_tvl


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(DexPoolTvl).delete()
        s.commit()
        yield s


def test_upsert_dex_pool_tvl_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool1", "dex": "uniswap-v3",
         "symbol": "USDC-WETH", "tvl_usd": 312_000_000.0},
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool2", "dex": "curve-dex",
         "symbol": "3pool", "tvl_usd": 64_000_000.0},
    ]
    n = upsert_dex_pool_tvl(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(DexPoolTvl).order_by(DexPoolTvl.tvl_usd.desc())).scalars().all()
    assert stored[0].pool_id == "0xpool1"
    assert stored[0].dex == "uniswap-v3"


def test_upsert_dex_pool_tvl_idempotent(session):
    rows = [{"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": "0xpool1", "dex": "uniswap-v3",
             "symbol": "USDC-WETH", "tvl_usd": 300_000_000.0}]
    upsert_dex_pool_tvl(session, rows)
    session.commit()
    rows[0]["tvl_usd"] = 350_000_000.0
    upsert_dex_pool_tvl(session, rows)
    session.commit()
    stored = session.execute(select(DexPoolTvl)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].tvl_usd)) == Decimal("350000000.000000")


def test_upsert_dex_pool_tvl_multi_pool_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-02T16:00:00Z", "pool_id": f"0xpool{i}", "dex": "uniswap-v3",
         "symbol": f"PAIR{i}", "tvl_usd": 1e6 * (10 - i)} for i in range(1, 6)
    ]
    assert upsert_dex_pool_tvl(session, rows) == 5
