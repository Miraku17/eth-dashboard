"""Hourly aggregator for Mantle DEX order flow.

Mirrors OrderFlowAggregator pattern: in-memory accumulation per
(dex, side), flush on hour rollover with additive ON CONFLICT so
graceful-shutdown partial flushes compose cleanly.

Crucially, this aggregator does NOT consult any price provider. It
stores raw MNT volume; USD valuation happens at /api/flows/mantle-
order-flow read time (see app.api.mantle_flows). This isolation
means a CoinGecko outage cannot drop swap data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import MantleOrderFlow
from app.realtime.mantle_swap_decoder import MantleSwap

SessionFactory = Callable[[], Session] | sessionmaker


class MantleOrderFlowAggregator:
    """Buffers (dex, side) → (count, mnt_total) for one hour, flushes to
    `mantle_order_flow` when the active hour changes (or on `flush()`).

    Usage::

        agg = MantleOrderFlowAggregator(session_factory)
        # Per decoded swap event from the Mantle listener:
        agg.add(swap)
        # On graceful shutdown (or each new block if you prefer eager flushing):
        agg.flush()

    The buffer reset on hour rollover happens BEFORE accumulating the new
    swap, so the rollover swap appears only in the new bucket.

    Calling `flush()` more than once is safe — the second call is a no-op
    because the buffer is cleared and `_current_hour` is set to None after
    the first successful flush.

    The ON CONFLICT semantics are additive (count + EXCLUDED.count,
    mnt_amount + EXCLUDED.mnt_amount), so independent processes flushing
    partial hours of the same bucket compose correctly without overwriting.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._current_hour: datetime | None = None
        # (dex, side) -> (count, mnt_total)
        self._buf: dict[tuple[str, str], tuple[int, float]] = {}

    def add(self, swap: MantleSwap) -> None:
        """Accept one decoded swap event and accumulate into the current hour's buffer.

        Silently drops events where:
        - side is not 'buy' or 'sell'
        - mnt_amount is zero or negative
        """
        if swap.side not in ("buy", "sell"):
            return
        if swap.mnt_amount <= 0:
            return
        hour = swap.ts.replace(minute=0, second=0, microsecond=0)
        if self._current_hour is None:
            self._current_hour = hour
        elif hour != self._current_hour:
            # Flush the completed hour BEFORE advancing to the new one.
            self._flush_current()
            self._current_hour = hour
            self._buf = {}
        count, total = self._buf.get((swap.dex, swap.side), (0, 0.0))
        self._buf[(swap.dex, swap.side)] = (count + 1, total + swap.mnt_amount)

    def flush(self) -> None:
        """Flush any buffered data and reset state.

        Safe to call multiple times — subsequent calls after the buffer is
        already empty are no-ops.
        """
        if self._current_hour is not None:
            self._flush_current()
            self._buf = {}
            self._current_hour = None

    def _flush_current(self) -> None:
        """Write the current hour's buffer to Postgres using additive ON CONFLICT."""
        if not self._buf or self._current_hour is None:
            return
        rows = []
        for (dex, side), (count, mnt_total) in self._buf.items():
            rows.append({
                "ts_bucket": self._current_hour,
                "dex": dex,
                "side": side,
                "count": count,
                "mnt_amount": mnt_total,
            })
        stmt = pg_insert(MantleOrderFlow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_bucket", "dex", "side"],
            set_={
                # ADDITIVE — graceful-shutdown partial flushes compose cleanly.
                # Two processes flushing different sub-hour windows of the same
                # bucket sum to the correct total rather than last-write-wins.
                "count": MantleOrderFlow.count + stmt.excluded.count,
                "mnt_amount": MantleOrderFlow.mnt_amount + stmt.excluded.mnt_amount,
            },
        )
        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
