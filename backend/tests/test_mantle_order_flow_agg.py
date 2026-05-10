"""Aggregator semantics tests. Use a real testcontainers Postgres
because the additive ON CONFLICT path is the most important property
to verify and mocking session execution would obscure it."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import MantleOrderFlow
from app.realtime.mantle_order_flow_agg import MantleOrderFlowAggregator
from app.realtime.mantle_swap_decoder import MantleSwap


@pytest.fixture
def test_session_factory(migrated_engine):
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory() as s:
        s.query(MantleOrderFlow).delete()
        s.commit()
    return factory


@pytest.fixture
def agg(test_session_factory):
    return MantleOrderFlowAggregator(test_session_factory)


def _swap(side: str, amount: float, ts: datetime, dex: str = "agni") -> MantleSwap:
    return MantleSwap(dex=dex, side=side, mnt_amount=amount, ts=ts)


def _read_all(test_session_factory) -> list[MantleOrderFlow]:
    with test_session_factory() as s:
        return list(s.scalars(select(MantleOrderFlow).order_by(
            MantleOrderFlow.ts_bucket, MantleOrderFlow.dex, MantleOrderFlow.side
        )))


def test_two_buys_same_hour_collapse_to_single_row(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)
    agg.add(_swap("buy", 5.0, h.replace(minute=12)))
    agg.add(_swap("buy", 3.0, h.replace(minute=58)))
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 1
    assert rows[0].side == "buy"
    assert float(rows[0].mnt_amount) == pytest.approx(8.0)
    assert rows[0].count == 2


def test_hour_rollover_writes_previous_bucket(agg, test_session_factory):
    h1 = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    h2 = datetime(2026, 5, 10, 15, 5, tzinfo=timezone.utc)
    agg.add(_swap("buy", 4.0, h1))
    agg.add(_swap("sell", 2.0, h2))   # different hour → flush prev
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 2
    by_hour = {r.ts_bucket: r for r in rows}
    h1_bucket = h1.replace(minute=0, second=0, microsecond=0)
    h2_bucket = h2.replace(minute=0, second=0, microsecond=0)
    assert float(by_hour[h1_bucket].mnt_amount) == pytest.approx(4.0)
    assert by_hour[h1_bucket].side == "buy"
    assert float(by_hour[h2_bucket].mnt_amount) == pytest.approx(2.0)
    assert by_hour[h2_bucket].side == "sell"


def test_partial_flush_idempotent_via_additive_on_conflict(test_session_factory):
    """Simulate a graceful restart mid-hour: flush twice with the same
    in-memory buffer state. The on-conflict path should yield doubled
    totals because two flushes of identical state IS double-counting —
    BUT the realistic restart scenario is that the second flush carries
    DIFFERENT (subsequent) swaps, so what we're really testing is that
    the SQL is additive rather than overwriting."""
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)

    # First "process": 1 buy, then crash.
    agg = MantleOrderFlowAggregator(test_session_factory)
    agg.add(_swap("buy", 5.0, h))
    agg.flush()

    # Second "process" (restart): another buy in the same hour.
    agg2 = MantleOrderFlowAggregator(test_session_factory)
    agg2.add(_swap("buy", 3.0, h.replace(minute=45)))
    agg2.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 1
    assert float(rows[0].mnt_amount) == pytest.approx(8.0)
    assert rows[0].count == 2


def test_zero_amount_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", 0.0, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_negative_amount_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", -1.5, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_unknown_side_is_dropped(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("hodl", 5.0, h))
    agg.flush()
    assert _read_all(test_session_factory) == []


def test_buy_and_sell_in_same_hour_produce_two_rows(agg, test_session_factory):
    h = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    agg.add(_swap("buy", 5.0, h))
    agg.add(_swap("sell", 2.0, h.replace(minute=45)))
    agg.flush()

    rows = _read_all(test_session_factory)
    assert len(rows) == 2
    by_side = {r.side: r for r in rows}
    assert float(by_side["buy"].mnt_amount) == pytest.approx(5.0)
    assert float(by_side["sell"].mnt_amount) == pytest.approx(2.0)
