"""Tests for the protocol_tvl upsert path. Uses migrated_engine testcontainer."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import ProtocolTvl
from app.services.defi_tvl_sync import upsert_protocol_tvl


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(ProtocolTvl).delete()
        s.commit()
        yield s


def test_upsert_protocol_tvl_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDC", "tvl_usd": 4_320_000_000.0},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDT", "tvl_usd": 3_100_000_000.0},
    ]
    n = upsert_protocol_tvl(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(ProtocolTvl).order_by(ProtocolTvl.asset)).scalars().all()
    assert {r.asset for r in stored} == {"USDC", "USDT"}


def test_upsert_protocol_tvl_idempotent(session):
    rows = [{"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3", "asset": "USDC", "tvl_usd": 4_000_000_000.0}]
    upsert_protocol_tvl(session, rows)
    session.commit()
    rows[0]["tvl_usd"] = 4_500_000_000.0
    upsert_protocol_tvl(session, rows)
    session.commit()
    stored = session.execute(select(ProtocolTvl)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].tvl_usd)) == Decimal("4500000000.000000")


def test_upsert_protocol_tvl_multi_protocol_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "aave-v3",     "asset": "USDC", "tvl_usd": 4e9},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "morpho",      "asset": "USDC", "tvl_usd": 1e9},
        {"ts_bucket": "2026-05-02T12:00:00Z", "protocol": "compound-v3", "asset": "USDC", "tvl_usd": 0.6e9},
    ]
    assert upsert_protocol_tvl(session, rows) == 3
    session.commit()
    assert session.query(ProtocolTvl).count() == 3
