"""Hourly trade-size bucket aggregator (v4 — replaces Dune volume_buckets).

Piggy-backs on the same SwapEvent stream the OrderFlowAggregator consumes;
the only difference is the aggregation key — instead of (dex, side) we
key on a USD-size bucket:

    retail  : usd <  $10k
    mid     : usd <  $100k
    large   : usd <  $1M
    whale   : usd >= $1M

Pattern matches OrderFlowAggregator: in-memory per (ts_bucket, bucket),
flush on hour rollover with additive on_conflict so partial flushes
compose correctly.

Pricing happens at add-time (caller passes pre-computed USD) because the
bucket assignment depends on USD value — we can't bucket-then-price the
way OrderFlowAggregator does.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import VolumeBucket

SessionFactory = Callable[[], Session] | sessionmaker

# Same boundaries the existing Dune SQL used. Documented in CLAUDE.md.
_RETAIL_MAX = 10_000.0
_MID_MAX = 100_000.0
_LARGE_MAX = 1_000_000.0


def _bucket_for(usd: float) -> str:
    if usd < _RETAIL_MAX:
        return "retail"
    if usd < _MID_MAX:
        return "mid"
    if usd < _LARGE_MAX:
        return "large"
    return "whale"


class VolumeBucketAggregator:
    """Buffers (bucket) -> (count, usd_total) for one hour, flushes to
    `volume_buckets` when the active hour changes."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._current_hour: datetime | None = None
        self._buf: dict[str, tuple[int, float]] = {}

    def add(self, usd_value: float, ts: datetime) -> None:
        if usd_value <= 0:
            return
        bucket = _bucket_for(usd_value)
        hour = ts.replace(minute=0, second=0, microsecond=0)
        if self._current_hour is None:
            self._current_hour = hour
        elif hour != self._current_hour:
            self._flush_current()
            self._current_hour = hour
            self._buf = {}
        count, total = self._buf.get(bucket, (0, 0.0))
        self._buf[bucket] = (count + 1, total + usd_value)

    def flush(self) -> None:
        if self._current_hour is not None:
            self._flush_current()
            self._buf = {}
            self._current_hour = None

    def _flush_current(self) -> None:
        if not self._buf or self._current_hour is None:
            return
        rows = [
            {
                "ts_bucket": self._current_hour,
                "bucket": bucket,
                "usd_value": usd_total,
                "trade_count": count,
            }
            for bucket, (count, usd_total) in self._buf.items()
        ]
        stmt = pg_insert(VolumeBucket).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_bucket", "bucket"],
            set_={
                # Additive — partial flushes (graceful restart mid-hour)
                # compose cleanly with subsequent flushes for the same hour.
                "usd_value": VolumeBucket.usd_value + stmt.excluded.usd_value,
                "trade_count": VolumeBucket.trade_count + stmt.excluded.trade_count,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
