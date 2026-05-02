"""Tests for the per-minute on-chain volume aggregator."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.models import RealtimeVolume
from app.realtime.volume_agg import MinuteAggregator


@pytest.fixture
def session_factory(migrated_engine):
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory() as s:
        s.query(RealtimeVolume).delete()
        s.commit()
    return factory


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 2, 12, minute, 30, tzinfo=UTC)


def test_add_accumulates_within_minute(session_factory):
    agg = MinuteAggregator(session_factory)
    agg.add("USDT", 1_000_000.0, _ts(0))
    agg.add("USDT", 500_000.0, _ts(0))
    agg.add("USDC", 250_000.0, _ts(0))
    # Nothing flushed yet — same minute.
    with session_factory() as s:
        assert s.query(RealtimeVolume).count() == 0


def test_minute_rollover_flushes(session_factory):
    agg = MinuteAggregator(session_factory)
    agg.add("USDT", 1_000_000.0, _ts(0))
    agg.add("USDT", 500_000.0, _ts(0))
    agg.add("USDC", 250_000.0, _ts(0))
    # Now move to minute 1 — previous minute's rows should land.
    agg.add("USDT", 100.0, _ts(1))
    with session_factory() as s:
        rows = s.execute(
            select(RealtimeVolume).where(RealtimeVolume.ts_minute == _ts(0).replace(second=0))
        ).scalars().all()
        by_asset = {r.asset: (r.transfer_count, float(r.usd_volume)) for r in rows}
        assert by_asset == {
            "USDT": (2, 1_500_000.0),
            "USDC": (1, 250_000.0),
        }


def test_explicit_flush_persists_pending(session_factory):
    """When the listener stops, calling flush() should persist any pending bucket."""
    agg = MinuteAggregator(session_factory)
    agg.add("USDT", 750_000.0, _ts(5))
    agg.flush()
    with session_factory() as s:
        rows = s.execute(select(RealtimeVolume)).scalars().all()
        assert len(rows) == 1
        assert rows[0].asset == "USDT"
        assert float(rows[0].usd_volume) == 750_000.0


def test_flush_no_op_when_empty(session_factory):
    agg = MinuteAggregator(session_factory)
    agg.flush()
    with session_factory() as s:
        assert s.query(RealtimeVolume).count() == 0


def test_idempotent_on_minute_overlap(session_factory):
    """If the same minute gets flushed twice (e.g. listener restart mid-flush),
    on_conflict_do_update means last write wins. Both writes should leave one row."""
    agg = MinuteAggregator(session_factory)
    agg.add("USDT", 1_000_000.0, _ts(10))
    agg.add("USDT", 500_000.0, _ts(11))  # rollover flushes minute-10
    with session_factory() as s:
        rows = s.execute(select(RealtimeVolume)).scalars().all()
        assert len(rows) == 1

    # Now feed the same minute-10 again from a fresh aggregator (simulates restart).
    agg2 = MinuteAggregator(session_factory)
    agg2.add("USDT", 2_000_000.0, _ts(10))
    agg2.add("USDT", 0.0, _ts(11))  # rollover
    with session_factory() as s:
        rows = s.execute(
            select(RealtimeVolume).where(RealtimeVolume.ts_minute == _ts(10).replace(second=0))
        ).scalars().all()
        assert len(rows) == 1
        # Last writer wins — count + value reflect the second aggregator's bucket.
        assert rows[0].transfer_count == 1
        assert float(rows[0].usd_volume) == 2_000_000.0
