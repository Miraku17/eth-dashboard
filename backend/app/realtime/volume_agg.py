"""Per-minute on-chain volume aggregator.

Lives in-process inside the realtime listener. The listener calls `add()`
for every Stable transfer it observes (regardless of whale threshold);
when the minute boundary rolls over we batch-upsert the previous minute's
totals to the `realtime_volume` table.

The aggregator owns its own session per flush so the listener doesn't
have to thread a Session through. Idempotent: two flushes of the same
minute → last-write-wins via PG upsert.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import RealtimeVolume

# Type alias — the aggregator accepts either a sessionmaker or a zero-arg
# callable returning a Session. Both are common patterns in the project.
SessionFactory = Callable[[], Session] | sessionmaker


class MinuteAggregator:
    """Buffers one minute's per-asset transfer counts + USD volume in memory,
    flushing to Postgres when the active minute changes."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._current_minute: datetime | None = None
        # asset -> (count, usd_total)
        self._buf: dict[str, tuple[int, float]] = {}

    def add(self, asset: str, usd_value: float, ts: datetime) -> None:
        """Add a single transfer to the active minute. If `ts` lands in a
        new minute, flush the previous one first."""
        minute = ts.replace(second=0, microsecond=0)
        if self._current_minute is None:
            self._current_minute = minute
        elif minute != self._current_minute:
            self._flush_current()
            self._current_minute = minute
            self._buf = {}
        count, total = self._buf.get(asset, (0, 0.0))
        self._buf[asset] = (count + 1, total + usd_value)

    def flush(self) -> None:
        """Persist any pending bucket. Called on listener shutdown / explicit drain."""
        if self._current_minute is not None:
            self._flush_current()
            self._buf = {}
            self._current_minute = None

    def _flush_current(self) -> None:
        if not self._buf or self._current_minute is None:
            return
        rows = [
            {
                "ts_minute": self._current_minute,
                "asset": asset,
                "transfer_count": count,
                "usd_volume": total,
            }
            for asset, (count, total) in self._buf.items()
        ]
        stmt = pg_insert(RealtimeVolume).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_minute", "asset"],
            set_={
                "transfer_count": stmt.excluded.transfer_count,
                "usd_volume": stmt.excluded.usd_volume,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
