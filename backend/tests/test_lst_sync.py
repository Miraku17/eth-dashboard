"""Tests for the lst_supply upsert path. Mirrors test_flow_sync conventions."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import LstSupply
from app.services.lst_sync import upsert_lst_supply


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(LstSupply).delete()
        s.commit()
        yield s


def test_upsert_lst_supply_round_trip(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH", "supply": 9_876_543.21},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "rETH",  "supply":   876_543.21},
    ]
    n = upsert_lst_supply(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(LstSupply).order_by(LstSupply.token)).scalars().all()
    assert {r.token for r in stored} == {"stETH", "rETH"}


def test_upsert_lst_supply_idempotent(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH", "supply": 9_876_543.21},
    ]
    upsert_lst_supply(session, rows)
    session.commit()
    rows[0]["supply"] = 9_900_000.0
    upsert_lst_supply(session, rows)
    session.commit()
    stored = session.execute(select(LstSupply)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].supply)) == Decimal("9900000.000000000000000000")


def test_upsert_lst_supply_multi_token_same_bucket(session):
    rows = [
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "stETH",   "supply": 9_876_543.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "rETH",    "supply": 876_543.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "cbETH",   "supply": 234_000.0},
        {"ts_bucket": "2026-05-01T12:00:00Z", "token": "sfrxETH", "supply": 250_000.0},
    ]
    assert upsert_lst_supply(session, rows) == 4
    session.commit()
    assert session.query(LstSupply).count() == 4
