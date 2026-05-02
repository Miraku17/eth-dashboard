"""Tests for the staking_flows upsert path. Mirrors test_flow_sync conventions."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import StakingFlow
from app.services.flow_sync import upsert_staking_flows


@pytest.fixture
def session(migrated_engine):
    Session = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with Session() as s:
        s.query(StakingFlow).delete()
        s.commit()
        yield s


def test_upsert_staking_flows_round_trip(session):
    rows = [
        {
            "ts_bucket": "2026-05-01T12:00:00Z",
            "kind": "deposit",
            "amount_eth": 320.0,
            "amount_usd": 1_120_000.0,
        },
        {
            "ts_bucket": "2026-05-01T12:00:00Z",
            "kind": "withdrawal_full",
            "amount_eth": 64.0,
            "amount_usd": 224_000.0,
        },
    ]
    n = upsert_staking_flows(session, rows)
    session.commit()
    assert n == 2
    stored = session.execute(select(StakingFlow).order_by(StakingFlow.kind)).scalars().all()
    assert {row.kind for row in stored} == {"deposit", "withdrawal_full"}
    deposit_row = next(r for r in stored if r.kind == "deposit")
    assert Decimal(str(deposit_row.amount_eth)) == Decimal("320.000000000000000000")


def test_upsert_staking_flows_filters_unknown_kind(session):
    rows = [
        {
            "ts_bucket": "2026-05-01T12:00:00Z",
            "kind": "deposit",
            "amount_eth": 32.0,
            "amount_usd": 112_000.0,
        },
        {
            "ts_bucket": "2026-05-01T12:00:00Z",
            "kind": "garbage",  # defensive: should be skipped
            "amount_eth": 1.0,
            "amount_usd": 4000.0,
        },
    ]
    n = upsert_staking_flows(session, rows)
    session.commit()
    assert n == 1


def test_upsert_staking_flows_idempotent(session):
    rows = [
        {
            "ts_bucket": "2026-05-01T12:00:00Z",
            "kind": "deposit",
            "amount_eth": 32.0,
            "amount_usd": 112_000.0,
        },
    ]
    upsert_staking_flows(session, rows)
    session.commit()
    rows[0]["amount_eth"] = 64.0
    rows[0]["amount_usd"] = 224_000.0
    upsert_staking_flows(session, rows)
    session.commit()
    stored = session.execute(select(StakingFlow)).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].amount_eth)) == Decimal("64.000000000000000000")
